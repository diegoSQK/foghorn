"""Boom Boom Room scraper.

Source: the venue's own WordPress site. Boom Boom Room (the Fillmore funk/blues
club at 1601 Fillmore St) runs the **Rockhouse Partners / Etix** "rhp-events"
plugin, whose ``/events/`` list view is fully server-rendered: every announced
upcoming show appears as a ``div.rhpSingleEvent`` block grouped under
"Month YYYY" separator spans, carrying the title, a "Wed, Jul 01" date line, a
"Doors: 7 pm // Show: 9 pm" time line, the per-event page URL, and the Etix
"Buy Tickets" link. One ``httpx`` GET + ``beautifulsoup4`` covers the whole
calendar.

Cleaner sources were hunted and ruled out: no Tribe REST API (``/wp-json/tribe/
events/v1/events`` 404s), the ``rhp_events`` post type isn't exposed via
``/wp-json/wp/v2``, no public ``.ics`` feed, and event JSON-LD exists only on
the per-event pages (one fetch per show, and it lacks the doors time the list
view provides).

The venue posts non-music nights (comedy showcase, live-band karaoke) on the
same calendar; those are dropped by title keyword. Bills are free-text titles
("KATDELIC ... w/ SONAMÓ"), so no headliner/support split is attempted — the
"w/" convention also names event features ("Day Party SAT w/ *MUZIEK*"), making
any split guesswork.

Runnable standalone: ``python -m foghorn.scrapers.boom_boom_room`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "boom_boom_room"

CALENDAR_URL = "https://boomboomroom.com/events/"
# Fallback provenance when an event block's own page link is missing; normally
# each show's source_url is its own /event/ page.
SOURCE_URL = CALENDAR_URL
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# "7 pm", "9:15 pm", "12 pm" — hour, optional minutes, meridiem.
_TIME = r"(\d{1,2}(?::\d{2})?)\s*([ap])\.?\s*m\.?"
_SHOW_RE = re.compile(r"show:?\s*" + _TIME, re.IGNORECASE)
_DOORS_RE = re.compile(r"doors:?\s*" + _TIME, re.IGNORECASE)
_BARE_TIME_RE = re.compile(_TIME, re.IGNORECASE)
# Month separators read "July 2026".
_SEPARATOR_RE = re.compile(r"([A-Za-z]+)\s+(\d{4})")

# The calendar mixes in non-music nights; drop titles carrying a strong
# non-music signal. Ambiguous entries (DJ nights, day parties) are kept.
_NON_MUSIC_SIGNALS = (
    "comedy",
    "karaoke",
    "trivia",
    "bingo",
    "open mic",
    "private event",
    "private party",
)


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch the events listing page. Kept separate from parsing so tests drive
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
    lowered = title.lower()
    if lowered.startswith("closed"):
        return True
    return any(signal in lowered for signal in _NON_MUSIC_SIGNALS)


def _parse_time(hour_text: str, meridiem: str) -> dt.time:
    """Combine regex groups like ("9:15", "p") into a time."""
    normalized = hour_text.replace(" ", "") + meridiem.upper() + "M"  # "9:15PM"
    fmt = "%I:%M%p" if ":" in normalized else "%I%p"
    return dt.datetime.strptime(normalized, fmt).time()


def _parse_times(text: str) -> tuple[dt.time | None, dt.time | None]:
    """Return (show start, doors) from a "Doors: 7 pm // Show: 9 pm" line.
    Either label may be absent; an unlabeled time is treated as the start."""
    show_match = _SHOW_RE.search(text)
    doors_match = _DOORS_RE.search(text)
    show = _parse_time(*show_match.groups()) if show_match else None
    doors = _parse_time(*doors_match.groups()) if doors_match else None
    if show is None and doors is None:
        bare = _BARE_TIME_RE.search(text)
        if bare:
            show = _parse_time(*bare.groups())
    return show, doors


def _parse_event_date(
    date_text: str, separator: tuple[int, int] | None, today: dt.date
) -> dt.date | None:
    """Turn a "Wed, Jul 01" line into a date. The year comes from the current
    "July 2026" month separator; if no separator matches (or its month
    disagrees), infer the earliest year that doesn't put the show in the past —
    the events page never lists past shows."""
    match = re.search(r"([A-Za-z]{3,})\s+(\d{1,2})", date_text.split(",")[-1])
    if match is None:
        return None
    try:
        parsed = dt.datetime.strptime(f"{match.group(1)[:3]} {match.group(2)}", "%b %d")
    except ValueError:
        return None
    month, day = parsed.month, parsed.day
    if separator is not None and separator[1] == month:
        year = separator[0]
    else:
        year = today.year if (month, day) >= (today.month, today.day) else today.year + 1
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def _parse_separator(text: str) -> tuple[int, int] | None:
    """Parse a "July 2026" separator into (year, month)."""
    match = _SEPARATOR_RE.search(text)
    if match is None:
        return None
    try:
        month = dt.datetime.strptime(match.group(1)[:3], "%b").month
    except ValueError:
        return None
    return int(match.group(2)), month


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per musical ``rhpSingleEvent`` block whose
    date falls in ``[today, today + window_days]``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    separator: tuple[int, int] | None = None
    # Separators and event blocks interleave; select() preserves document
    # order, so each event sees the month header above it.
    for node in soup.select("span.rhp-events-list-separator-month, div.rhpSingleEvent"):
        classes: list[str] | str = node.get("class") or []
        if "rhp-events-list-separator-month" in classes:
            separator = _parse_separator(node.get_text(" ", strip=True)) or separator
            continue

        title_link = node.select_one("a#eventTitle")
        if title_link is None:
            continue
        headliner = _clean(title_link.get_text(" ", strip=True))
        if not headliner or _is_non_music(headliner):
            continue

        date_el = node.select_one("#eventDate")
        if date_el is None:
            continue
        show_date = _parse_event_date(date_el.get_text(" ", strip=True), separator, today)
        if show_date is None or not (today <= show_date <= window_end):
            continue

        time_el = node.select_one(".rhp-event__time-text--list")
        start_time, doors_time = (
            _parse_times(time_el.get_text(" ", strip=True)) if time_el is not None else (None, None)
        )
        if start_time is None:
            continue

        ticket_link = node.select_one(".rhp-event-cta a")
        ticket_href = _attr(ticket_link, "href") if ticket_link is not None else None

        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=[],
                start_local=dt.datetime.combine(show_date, start_time),
                doors_local=(
                    dt.datetime.combine(show_date, doors_time) if doors_time is not None else None
                ),
                ticket_url=ticket_href or None,
                price_text=None,
                source_url=_attr(title_link, "href") or SOURCE_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live events page for the next ~90 days."""
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
