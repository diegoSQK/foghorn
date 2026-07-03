"""California Jazz Conservatory (The Jazzschool) scraper.

Source: the school's public concerts site. CJC (2087 Addison St, Berkeley)
publishes its public concert calendar — separate from its class/workshop
catalog — at ``concerts.jazzschool.org`` (``cjc.edu`` → ``jazzschool.org``;
``/concerts/`` redirects to the subdomain). The listing page is server-rendered
WordPress: one ``a.tiles__item`` per upcoming concert with the title, a
``base-date`` ("Jul 08, 2026"), and the per-event page URL — but no time.

Times live on the per-event pages (``page-single-event__date``: "July 08, 2026
<br/> 7:00 PM - 10:00 PM"), so ``scrape()`` fetches the listing once, then one
small page per in-window concert (~15 today). Ticketing is a VBO Tickets
widget injected client-side into the event page, so there's no static ticket
href or price to capture — ``ticket_url``/``price_text`` stay ``None`` and the
event page itself (``source_url``) is where tickets are bought. Doors are
sometimes announced in the event prose ("Doors 7pm") and are captured when
present. Events whose page carries no parseable start time are skipped rather
than invented.

Because this is the concert calendar, classes/workshops never appear here. The
venue does list a few clearly-non-music events (jazz *movie* nights); those are
dropped. Talk-adjacent series (Brown Bag Jazz Hangs, vinyl-listening lounges,
jams, open mics) are kept per the "when ambiguous, keep" rule.

Runnable standalone: ``python -m foghorn.scrapers.california_jazz_conservatory``
prints the scraped shows as JSON and exits. No DB writes here — that's the
ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Mapping
from typing import NamedTuple

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "california_jazz_conservatory"

CALENDAR_URL = "https://concerts.jazzschool.org/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# Listing tile date, e.g. "Jul 08, 2026".
_TILE_DATE_FMT = "%b %d, %Y"
# Event-page date line, e.g. "July 11, 2026 8:00 PM - 9:30 PM".
_PAGE_DATE_RE = re.compile(r"([A-Za-z]+\s+\d{1,2},\s+\d{4})")
_PAGE_TIME_RE = re.compile(r"(\d{1,2}(?::\d{2})?\s*[AP]\.?M\.?)", re.IGNORECASE)
# Doors line in the event prose, e.g. "Doors 7pm" / "Doors at 6:30 PM".
_DOORS_RE = re.compile(
    r"doors\s*(?:@|at)?\s*(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?)", re.IGNORECASE
)

# The concerts calendar is nearly all live music; only film screenings are a
# clear non-music signal today ("FREE! Jazz Movie Night – …"). Jams, open mics,
# listening lounges, and Brown Bag talks are kept (ambiguous → keep).
_NON_MUSIC_SIGNALS = ("movie night", "movie", "film screening", "film night")


class EventStub(NamedTuple):
    """One listing tile: what we know before fetching the event page."""

    title: str
    date: dt.date
    url: str


def fetch_html(url: str) -> str:
    """Fetch one page (the listing or a per-event page). Kept separate from
    parsing so tests drive the parsers from fixtures without the network."""
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
    return any(signal in lowered for signal in _NON_MUSIC_SIGNALS)


def _parse_time(time_text: str) -> dt.time:
    """Parse "7pm" / "7:00 PM" / "12:30pm" into a ``time``."""
    normalized = time_text.replace(" ", "").replace(".", "").upper()  # "7:00PM"
    fmt = "%I:%M%p" if ":" in normalized else "%I%p"
    return dt.datetime.strptime(normalized, fmt).time()


def parse_listing(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[EventStub]:
    """Return one ``EventStub`` per upcoming-concert tile whose date falls in
    ``[today, today + window_days]``, dropping clearly-non-music titles.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable. Filtering here — before the per-event
    fetches in ``scrape`` — avoids fetching pages we'd discard anyway.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    stubs: list[EventStub] = []
    for tile in soup.select("div.js--events-items a.tiles__item"):
        url = _attr(tile, "href")
        name_tag = tile.select_one(".tiles__name")
        date_tag = tile.select_one(".base-date")
        if not url or name_tag is None or date_tag is None:
            continue
        title = _clean(name_tag.get_text(" ", strip=True))
        if not title or _is_non_music(title):
            continue
        try:
            date = dt.datetime.strptime(
                _clean(date_tag.get_text(" ", strip=True)), _TILE_DATE_FMT
            ).date()
        except ValueError:
            continue
        if not (today <= date <= window_end):
            continue
        stubs.append(EventStub(title=title, date=date, url=url))
    return stubs


def parse_event_page(html: str) -> tuple[dt.date | None, dt.time | None, dt.time | None]:
    """Extract ``(date, start_time, doors_time)`` from a per-event page.

    Date and start come from the ``page-single-event__date`` block ("July 11,
    2026 <br/> 8:00 PM - 9:30 PM" — the first time is the start; the second is
    the advertised end, which foghorn doesn't model). Doors come from the event
    prose when announced. Any missing piece is ``None``.
    """
    soup = BeautifulSoup(html, "html.parser")
    date_block = soup.select_one(".page-single-event__date")
    date: dt.date | None = None
    start_time: dt.time | None = None
    if date_block is not None:
        text = _clean(date_block.get_text(" ", strip=True))
        date_match = _PAGE_DATE_RE.search(text)
        if date_match:
            date = dt.datetime.strptime(
                re.sub(r"\s+", " ", date_match.group(1)), "%B %d, %Y"
            ).date()
        time_match = _PAGE_TIME_RE.search(text)
        if time_match:
            start_time = _parse_time(time_match.group(1))

    doors_time: dt.time | None = None
    prose = soup.select_one(".page-single-event .base-text")
    if prose is not None:
        doors_match = _DOORS_RE.search(prose.get_text(" ", strip=True))
        if doors_match:
            doors_time = _parse_time(doors_match.group(1))
    return date, start_time, doors_time


def build_shows(stubs: list[EventStub], pages: Mapping[str, str]) -> list[ScrapedShow]:
    """Combine listing stubs with their fetched event pages (URL → HTML) into
    ``ScrapedShow``s. Pure / fixture-testable.

    The event page's own date wins over the tile date when both parse (it's
    the authoritative record); a stub whose page is missing or carries no
    parseable start time is skipped — we don't invent times.
    """
    shows: list[ScrapedShow] = []
    for stub in stubs:
        page = pages.get(stub.url)
        if page is None:
            continue
        page_date, start_time, doors_time = parse_event_page(page)
        if start_time is None:
            continue
        date = page_date or stub.date
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=stub.title,
                support_raw=[],
                start_local=dt.datetime.combine(date, start_time),
                doors_local=(
                    dt.datetime.combine(date, doors_time) if doors_time is not None else None
                ),
                ticket_url=None,
                price_text=None,
                source_url=stub.url,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch the live listing plus one page per in-window concert (~15)."""
    stubs = parse_listing(fetch_html(CALENDAR_URL), dt.date.today())
    pages = {url: fetch_html(url) for url in {stub.url for stub in stubs}}
    return build_shows(stubs, pages)


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
