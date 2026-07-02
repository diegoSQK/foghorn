"""Cafe du Nord scraper.

Source: the venue's own WordPress site. Cafe du Nord (2174 Market St, Castro)
renders ``/calendar/`` server-side with the same TicketWeb "tw-" calendar
template as The Independent — shared parsing lives in ``_ticketweb_calendar``.
Plain ``httpx`` + ``beautifulsoup4`` suffice; no JS execution needed.

Deployment quirks:

- **Pagination.** 20 events per page with a "Next »" link (4 pages as of
  July 2026); ``scrape`` walks the pages and merges.
- **Popup dialogs.** Each page also embeds hidden ``tw-event-dialog`` popups
  for *every* event (all pages' worth), carrying the full date with year,
  doors time, and price — the shared parser joins them to the list rows by
  per-event URL.
- **Duplicate rows.** The first rows repeat inside an email-signup popup;
  deduped by the shared parser, and again here across pages.
- **Two rooms, one calendar.** Shows at the attached Swedish American Hall
  (upstairs, same 2170-2174 Market St building) are billed on this calendar
  too and are kept under this slug.
- **"Private Event"** placeholder rows are dropped by the shared parser.

Runnable standalone: ``python -m foghorn.scrapers.cafe_du_nord`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import json

import httpx

from foghorn.models import ScrapedShow
from foghorn.scrapers._ticketweb_calendar import find_next_page_url, parse_calendar_html

VENUE_SLUG = "cafe_du_nord"

CALENDAR_URL = "https://cafedunord.com/calendar/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0
# Safety valve for the pagination walk; the calendar is ~4 pages.
MAX_PAGES = 10


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch one calendar page. Kept separate from parsing so tests drive
    ``parse_html`` from a fixture without touching the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def fetch_pages(start_url: str = CALENDAR_URL, max_pages: int = MAX_PAGES) -> list[str]:
    """Fetch the calendar and follow its "Next »" links, returning each page's
    HTML in order."""
    pages: list[str] = []
    url: str | None = start_url
    seen: set[str] = set()
    while url is not None and url not in seen and len(pages) < max_pages:
        seen.add(url)
        html = fetch_html(url)
        pages.append(html)
        url = find_next_page_url(html)
    return pages


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per listed show on one calendar page, dated
    within ``[today, today + window_days]``, sorted by ``start_local``."""
    return parse_calendar_html(
        html,
        venue_slug=VENUE_SLUG,
        today=today,
        window_days=window_days,
        fallback_source_url=CALENDAR_URL,
    )


def scrape() -> list[ScrapedShow]:
    """Fetch and parse all calendar pages for the next ~90 days."""
    today = dt.date.today()
    merged: dict[tuple[str, dt.datetime], ScrapedShow] = {}
    for html in fetch_pages():
        for show in parse_html(html, today):
            merged.setdefault((show.source_url, show.start_local), show)
    return sorted(merged.values(), key=lambda show: show.start_local)


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
