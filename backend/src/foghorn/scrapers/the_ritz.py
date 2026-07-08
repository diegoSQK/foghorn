"""The Ritz (San Jose) scraper.

Source: the venue's own WordPress site. The Ritz (a downtown San Jose
nightclub / live-music venue at 400 S. First St) runs the **IronBand** theme,
whose homepage calendar is an empty ``<ul id="post-list" class="concerts-list">``
filled by an AJAX "More Gigs" loader. ``POST /`` with ``ajax=1`` returns the
whole upcoming gig list as a server-rendered HTML fragment — one ``li.gig``
per event with an ISO-8601 ``<time datetime="…">`` (venue-local with offset;
the seconds are save-time noise), the bill in a ``span.location`` ("BELMONT +
MAJOR LEAGUE + SPITE HOUSE"), and a TicketWeb "TICKETS" link. (This is the
IronBand markup, not the shared "tw-" TicketWeb calendar template — see
``_ticketweb_calendar.py`` — so it gets its own parser.) The list currently
fits in one response with no follow-up "More" button; there are no per-event
pages, so ``source_url`` is the calendar itself.

**Bill splitting.** Bills use "+" separators with occasionally sloppy spacing
("FUMING MOUTH+ WEEPING"); a "+" touching at least one space splits the bill
into headliner + support. Doors/price only appear as free-form prose inside
each row's expandable blurb (which also gets years wrong), so they're left
``None`` rather than guessed.

Runnable standalone: ``python -m foghorn.scrapers.the_ritz`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup

from foghorn.models import ScrapedShow

VENUE_SLUG = "the_ritz"

BASE_URL = "https://theritzsanjose.com"
# The homepage *is* the calendar page ("Calendar" in the nav links here); it
# doubles as the seed calendar_url and every show's source_url.
CALENDAR_URL = f"{BASE_URL}/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# A nightclub's DJ/dance parties are music programming and stay in; only
# clearly non-music bookings are dropped (conservative, per house convention).
_NON_MUSIC_SIGNALS = ("karaoke", "trivia", "comedy", "bingo", "private event", "watch party")

# "+" adjacent to at least one space splits a bill; a fully embedded "+"
# (e.g. an act named "A+B") does not.
_BILL_SPLIT_RE = re.compile(r"\s+\+\s*|\s*\+\s+")


def fetch_gigs_html(url: str = CALENDAR_URL) -> str:
    """POST the theme's gig-list AJAX request. Kept separate from parsing so
    tests drive ``parse_html`` from a fixture without touching the network."""
    response = httpx.post(
        url,
        data={"ajax": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _clean(text: str) -> str:
    return " ".join(text.split())


def _is_non_music(title: str) -> bool:
    lowered = title.lower()
    return any(signal in lowered for signal in _NON_MUSIC_SIGNALS)


def _split_bill(title: str) -> tuple[str, list[str]]:
    parts = [part.strip() for part in _BILL_SPLIT_RE.split(title) if part.strip()]
    if len(parts) <= 1:
        return title, []
    return parts[0], parts[1:]


def _start_local(raw: str) -> dt.datetime | None:
    """"2026-07-09T21:00:26-07:00" → naive venue-local 2026-07-09 21:00. The
    offset is the venue's own; drop it (ingest re-applies the venue tz) along
    with the seconds, which are post-save-time noise."""
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None, second=0, microsecond=0)


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per ``li.gig`` whose date falls in
    ``[today, today + window_days]``, sorted by start time.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: dict[tuple[str, dt.datetime], ScrapedShow] = {}
    for li in soup.select("li.gig"):
        title_el = li.select_one("span.location")
        time_el = li.select_one("time.datetime")
        if title_el is None or time_el is None:
            continue
        title = _clean(title_el.get_text(" ", strip=True))
        if not title or _is_non_music(title):
            continue
        datetime_attr = time_el.get("datetime")
        start_local = _start_local(datetime_attr) if isinstance(datetime_attr, str) else None
        if start_local is None or not (today <= start_local.date() <= window_end):
            continue

        ticket_el = li.select_one("div.buttons a.button[href]")
        ticket_href = ticket_el.get("href") if ticket_el is not None else None

        headliner, support = _split_bill(title)
        show = ScrapedShow(
            venue_slug=VENUE_SLUG,
            headliner_raw=headliner,
            support_raw=support,
            start_local=start_local,
            doors_local=None,
            ticket_url=ticket_href if isinstance(ticket_href, str) else None,
            price_text=None,
            source_url=CALENDAR_URL,
        )
        shows.setdefault((show.headliner_raw, show.start_local), show)

    return sorted(shows.values(), key=lambda show: show.start_local)


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live gig list for the next ~90 days."""
    return parse_html(fetch_gigs_html(), dt.date.today())


def main() -> None:
    shows = scrape()
    print(
        json.dumps(
            [show.model_dump(mode="json") for show in shows],
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
