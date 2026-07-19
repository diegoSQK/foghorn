"""Noontime Concerts scraper.

Source: the presenter's WordPress (Divi) site at ``noontimeconcerts.org`` —
the weekly free Tuesday 12:30pm chamber series at Old St. Mary's Cathedral
(660 California St, SF), running since 1989. The site exposes a public
``concerts`` CPT at ``/wp-json/wp/v2/concerts``, but that payload carries
**no performance date at all**: ``acf`` and ``meta`` are empty, there is no
content field, and the WP ``date`` is the post's publish date, not the
concert's. So the scraper walks the server-rendered **Concert Calendar**
page (``/upcoming-concerts/``) instead, which renders one
``div.concert-card`` per upcoming concert with the real date in a
``data-date="MM/DD/YYYY"`` attribute plus ``data-title`` and a detail-page
link. (The ``/concert-library/`` archive uses the same card markup for
~660 past concerts — the upcoming page is the only forward-looking
surface.) One fetch, deterministic dates.

**Series-constant start time.** Neither the cards nor the detail pages
state a clock time; the series itself is the schedule — "Tuesdays at
12:30" per the site — so 12:30 is applied to every Tuesday card.

**Non-Tuesday cards are skipped.** The series also presents one Sunday
concert a month (Apr–Nov) at the San Francisco Mint — a different room
across town with no stated time, so attributing those cards to Old St.
Mary's would be wrong-venue data. If the Mint Sundays ever matter, they
want their own venue row.

**Seasonal caveat.** The weekly cadence pauses over midsummer; a sparse
July/August page (two cards at build time) is normal, not a scraper
failure.

Runnable standalone: ``python -m foghorn.scrapers.noontime_concerts``
prints the scraped shows as JSON and exits. No DB writes here — that's
the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json

import httpx
from bs4 import BeautifulSoup

from foghorn.models import ScrapedShow

VENUE_SLUG = "noontime_concerts"

# The server-rendered Concert Calendar (upcoming concerts only). Also the
# venue's seed calendar_url.
CALENDAR_URL = "https://noontimeconcerts.org/upcoming-concerts/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# The series' stated start — "Tuesdays at 12:30" — applied to every card
# (the cards carry dates only, no clock times).
_SERIES_START = dt.time(12, 30)
_TUESDAY = 1  # datetime.weekday()
_CARD_DATE_FMT = "%m/%d/%Y"


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch the Concert Calendar page. Kept separate from parsing so tests
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


def _parse_card_date(value: object) -> dt.date | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.strptime(value.strip(), _CARD_DATE_FMT).date()
    except ValueError:
        return None


def parse_html(
    page_html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Concert Calendar page → one ``ScrapedShow`` per Tuesday concert card
    whose ``data-date`` falls in ``[today, today + window_days]``. Cards
    with a missing/malformed date drop; non-Tuesday cards (the Mint Sunday
    series — different room, no stated time) are skipped per the module
    docstring. ``today`` is injected (not read from the clock) so the
    parser is deterministic and fixture-testable. Pure."""
    soup = BeautifulSoup(page_html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    seen: set[tuple[str, dt.date]] = set()
    for card in soup.select("div.concert-card"):
        date = _parse_card_date(card.get("data-date"))
        if date is None or date.weekday() != _TUESDAY:
            continue
        if not (today <= date <= window_end):
            continue
        title = _clean(str(card.get("data-title") or ""))
        if not title:
            title_el = card.select_one(".concert-title")
            title = _clean(title_el.get_text(" ", strip=True)) if title_el else ""
        if not title:
            continue
        key = (title, date)
        if key in seen:
            continue
        seen.add(key)
        link = card.select_one('a[href*="/concerts/"]')
        # Strip the "?from=upcoming" tracking query for a stable source_url.
        source_url = (
            str(link["href"]).split("?", 1)[0] if link is not None else CALENDAR_URL
        )
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=title,
                support_raw=[],
                start_local=dt.datetime.combine(date, _SERIES_START),
                doors_local=None,  # not stated — the church opens at concert time
                ticket_url=None,  # free series; no ticketing
                price_text=None,  # admission is donation-based but unstated per card
                source_url=source_url,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live Concert Calendar for the next ~90 days."""
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
