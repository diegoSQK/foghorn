"""Center for New Music scraper.

Source: the venue's own WordPress site. The Center for New Music (55 Taylor
St, a Tenderloin storefront venue for new/creative music) renders its calendar
server-side at ``/event/`` — one Bootstrap card per upcoming event carrying the
date line ("Thursday, July 2, 2026 — 8:00 PM"), the ``/event/<slug>/``
permalink + title, the "Tickets: …" price line, and a "Buy Online" link when
tickets are sold online. The archive query returns *all* upcoming events on a
single page (``/page/2/`` re-serves the same cards), so no pagination.

The ``/event/feed/`` RSS feed was considered and rejected: items are ordered
by *publish* date, include already-past events, and — decisively — carry no
event date/time anywhere in the payload. The Tribe REST API 404s (the events
are a bespoke custom post type, not The Events Calendar). Per-event pages add
nothing the listing lacks, so none are fetched.

Filtering: C4NM's bookings are the creative fringe — experimental/sound-art
performances are kept even when ambiguous. Only clearly-non-music programming
(workshops, classes, lectures, meetups/member meetings, screenings) is
dropped, by word-boundary title match. An event whose date line has no
parseable start time is skipped *loudly* (a warning on stderr) — we never
invent a time.

Plain ``httpx`` + ``beautifulsoup4`` suffice — no JS execution needed.

Runnable standalone: ``python -m foghorn.scrapers.center_for_new_music``
prints the scraped shows as JSON and exits. No DB writes here — that's the
ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "center_for_new_music"

CALENDAR_URL = "https://centerfornewmusic.com/event/"
# Fallback provenance when a card's permalink is missing; normally each show's
# source_url is its own /event/<slug>/ page.
SOURCE_URL = CALENDAR_URL
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# "Thursday, July 2, 2026 — 8:00 PM" (em dash on the live site; en dash and
# hyphen tolerated). The weekday anchors the match; the time group is optional
# so a bare date is recognized — and then skipped loudly — rather than
# mistaken for "no date line at all".
_DATE_RE = re.compile(
    r"[A-Za-z]+day,\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})"
    r"(?:\s*[—–-]\s*(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?))?",
    re.IGNORECASE,
)

# Clearly-non-music programming, matched on word boundaries against the
# lowercased title (``\bclass\b`` won't fire on "classical"). C4NM books the
# experimental fringe, so ambiguous sound-art/noise/performance titles are
# kept — this list only names the venue's recurring non-performance formats:
# workshops/classes, the monthly Composer Meetup, member meetings, and
# talk/screening events.
_NON_MUSIC_RE = re.compile(
    r"\b(?:workshop|master\s?class|class(?:es)?|lecture|meet-?up|"
    r"member(?:s'?)?\s+meeting|annual\s+meeting|open\s+house|"
    r"film\s+screening|movie\s+night|panel\s+discussion)\b"
)


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch the calendar listing page. Kept separate from parsing so tests
    drive ``parse_html`` from a fixture without touching the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _clean(text: str) -> str:
    return " ".join(text.split())


def _attr(tag: Tag, name: str) -> str | None:
    """Read a single-valued attribute as a clean ``str``. bs4 types attributes
    as ``str | list[str] | None`` (multi-valued attrs like ``class``); ``href``
    is always single, but we coerce defensively to stay type-safe."""
    value = tag.get(name)
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return str(value[0])
    return None


def _is_non_music(title: str) -> bool:
    return _NON_MUSIC_RE.search(title.lower()) is not None


def _parse_start(date_text: str, time_text: str) -> dt.datetime:
    """Combine "July 2, 2026" + "8:00 PM" into a naive local datetime. The
    venue tz is applied at ingest, not here."""
    date_part = dt.datetime.strptime(date_text, "%B %d, %Y").date()
    normalized = time_text.replace(" ", "").replace(".", "").upper()  # "8:00PM"
    fmt = "%I:%M%p" if ":" in normalized else "%I%p"
    time_part = dt.datetime.strptime(normalized, fmt).time()
    return dt.datetime.combine(date_part, time_part)


def _price_text(card: Tag) -> str | None:
    """The card footer's left column reads "Tickets: $15 General Admission,
    $10 Members & Students"; return it without the "Tickets:" label."""
    cell = card.select_one(".card-footer .col-6")
    if cell is None:
        return None
    text = re.sub(r"^Tickets:\s*", "", _clean(cell.get_text(" ", strip=True)))
    return text or None


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per calendar card whose date falls in
    ``[today, today + window_days]``, dropping clearly-non-music titles and
    loudly skipping cards without a parseable start time.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    for card in soup.select("main div.card"):
        title_tag = card.select_one(".card-body h4.card-title")
        if title_tag is None:
            continue
        headliner = _clean(title_tag.get_text(" ", strip=True))
        if not headliner or _is_non_music(headliner):
            continue

        date_tag = card.select_one(".event-date")
        date_text = _clean(date_tag.get_text(" ", strip=True)) if date_tag else ""
        match = _DATE_RE.search(date_text)
        if match is None or match.group(2) is None:
            # A bare date (or no date line) never becomes a show — we don't
            # invent times. Loud so the skip is visible in scrape output.
            print(
                f"{VENUE_SLUG}: skipping {headliner!r} — "
                f"no parseable start time in {date_text!r}",
                file=sys.stderr,
            )
            continue
        start_local = _parse_start(match.group(1), match.group(2))
        if not (today <= start_local.date() <= window_end):
            continue

        permalink = title_tag.find_parent("a")
        event_href = _attr(permalink, "href") if permalink is not None else None
        ticket_link = card.select_one(".card-footer a[href]")
        ticket_href = _attr(ticket_link, "href") if ticket_link is not None else None

        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=[],
                start_local=start_local,
                doors_local=None,
                ticket_url=ticket_href,
                price_text=_price_text(card),
                source_url=event_href or SOURCE_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live calendar page for the next ~90 days."""
    return parse_html(fetch_html(), dt.date.today())


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
