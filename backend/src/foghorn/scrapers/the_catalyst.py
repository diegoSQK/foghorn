"""The Catalyst scraper.

Source: the club's WordPress site at ``catalystclub.com/events/`` — the
Rockhouse Partners (Etix) events theme, fully server-rendered. Each show is
a ``div.rhpSingleEvent`` card: an ``eventDateList`` date ("Fri, Aug 07", no
year), the title ``h2``, a "Doors: 8:30 pm Show: 9 pm" time line, a fee-in
price ("$34.12 to $45.95"), a per-event ``a.url`` detail link, and an Etix
buy link. Covers both rooms (main floor and Atrium) under one slug.

Quirks: the page renders every card twice (list + grid variants of the
same widget; the grid copies drop time/price), so cards are deduped on
``(source_url, start_local)`` keeping the richer first pass. Dates carry no
year — inferred by rolling ``today``'s year forward when the month/day has
already passed (the list only shows upcoming events). Sister-venue promos
are interleaved and flagged in the title ("Sports **At Felton Music
Hall**"); any ``**At …**`` marker drops the card, while other starred
notes ("**Rescheduled from 6/27**") are just stripped from the title.

Runnable standalone: ``python -m foghorn.scrapers.the_catalyst`` prints
the scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup

from foghorn.models import ScrapedShow

VENUE_SLUG = "the_catalyst"

EVENTS_URL = "https://catalystclub.com/events/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# "Fri, Jul 24" — weekday, month abbreviation, day; no year.
_DATE_RE = re.compile(r"([A-Za-z]+)\s+(\d{1,2})\s*$")
_MONTHS: dict[str, int] = {
    **{calendar.month_name[i].lower(): i for i in range(1, 13)},
    **{calendar.month_abbr[i].lower(): i for i in range(1, 13)},
    "sept": 9,
}
_SHOW_RE = re.compile(r"\bShow:?\s*(\d{1,2})(?::(\d{2}))?\s*([ap])m", re.IGNORECASE)
_DOORS_RE = re.compile(r"\bDoors:?\s*(\d{1,2})(?::(\d{2}))?\s*([ap])m", re.IGNORECASE)
# Starred title notes: "**At Felton Music Hall**" (a sister-venue promo —
# drop the card), "**Rescheduled from 6/27**" (strip, keep the card).
_STARRED_NOTE_RE = re.compile(r"\*\*\s*([^*]+?)\s*\*\*")

# Clearly-not-a-concert titles; ambiguous stays in.
_NON_MUSIC_RE = re.compile(
    r"\bprivate event\b|\bwatch party\b|\bcomedy\b|\bwrestling\b", re.IGNORECASE
)


def fetch_html(url: str = EVENTS_URL) -> str:
    """Fetch the events page. Kept separate from parsing so tests drive
    ``parse_html`` from a fixture without touching the network."""
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


def _resolve_date(raw: str, today: dt.date) -> dt.date | None:
    """ "Fri, Jul 24" → a real date, assuming ``today``'s year and rolling
    forward one when the month/day has already passed — the list only ever
    shows upcoming events."""
    match = _DATE_RE.search(_clean(raw))
    if match is None:
        return None
    month = _MONTHS.get(match.group(1).lower())
    if month is None:
        return None
    day = int(match.group(2))
    try:
        candidate = dt.date(today.year, month, day)
    except ValueError:
        return None
    if candidate < today:
        try:
            candidate = dt.date(today.year + 1, month, day)
        except ValueError:
            return None
    return candidate


def _time_from(match: re.Match[str] | None) -> dt.time | None:
    if match is None:
        return None
    hour = int(match.group(1)) % 12
    if match.group(3).lower() == "p":
        hour += 12
    minute = int(match.group(2) or 0)
    return dt.time(hour, minute) if minute <= 59 else None


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per card dated within ``[today, today +
    window_days]``, sorted by ``start_local``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable — and because the year inference
    for the year-less "Fri, Jul 24" dates hinges on it."""
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: dict[tuple[str, dt.datetime], ScrapedShow] = {}
    for card in soup.select("div.rhpSingleEvent"):
        title_el = card.select_one("h2")
        if title_el is None:
            continue
        title = _clean(title_el.get_text(" ", strip=True))
        notes = _STARRED_NOTE_RE.findall(title)
        if any(note.lower().startswith("at ") for note in notes):
            continue  # sister-venue promo (e.g. "**At Felton Music Hall**")
        title = _clean(_STARRED_NOTE_RE.sub(" ", title))
        if not title or _NON_MUSIC_RE.search(title):
            continue

        date_el = card.select_one(".eventDateList")
        start_date = (
            _resolve_date(date_el.get_text(" ", strip=True), today) if date_el is not None else None
        )
        if start_date is None or not (today <= start_date <= window_end):
            continue

        time_el = card.select_one(".rhp-event__time-text--list")
        time_text = time_el.get_text(" ", strip=True) if time_el is not None else ""
        start_time = _time_from(_SHOW_RE.search(time_text))
        doors_time = _time_from(_DOORS_RE.search(time_text))
        if start_time is None:
            continue  # grid duplicates carry no time; never fabricate one

        link = card.select_one("a.url")
        href = link.get("href") if link is not None else None
        source_url = href if isinstance(href, str) and href else EVENTS_URL

        cta = card.select_one(".rhp-event-cta a")
        cta_href = cta.get("href") if cta is not None else None
        ticket_url = cta_href if isinstance(cta_href, str) and cta_href else None

        price_el = card.select_one(".rhp-event__cost-text--list")
        price_text = _clean(price_el.get_text(" ", strip=True)) if price_el else None

        show = ScrapedShow(
            venue_slug=VENUE_SLUG,
            headliner_raw=title,
            support_raw=[],
            start_local=dt.datetime.combine(start_date, start_time),
            doors_local=(dt.datetime.combine(start_date, doors_time) if doors_time else None),
            ticket_url=ticket_url,
            price_text=price_text or None,
            source_url=source_url,
        )
        shows.setdefault((show.source_url, show.start_local), show)

    return sorted(shows.values(), key=lambda show: show.start_local)


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live events list for the next ~90 days."""
    return parse_html(fetch_html(), dt.date.today())


def main() -> None:
    print(
        json.dumps(
            [show.model_dump(mode="json") for show in scrape()],
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
