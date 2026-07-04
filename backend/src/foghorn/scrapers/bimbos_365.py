"""Bimbo's 365 Club scraper.

Source: the venue's own WordPress site. Bimbo's 365 Club (1025 Columbus Ave,
North Beach) renders its upcoming-shows list server-side at ``/shows/``
(``/calendar/`` redirects there) using the same TicketWeb "tw-" calendar
template as The Independent and Cafe du Nord — shared parsing lives in
``_ticketweb_calendar``. Plain ``httpx`` + ``beautifulsoup4`` suffice; no JS
execution needed.

Deployment quirks:

- **Split date spans.** Rows render the day-of-month bare in ``tw-event-date``
  with the month name in a sibling ``tw-event-month`` span ("August" / "6",
  no year); the shared parser joins them and infers the year from ``today``.
- **Single page today**, but the theme's "Next »" pagination is followed
  anyway in case the list ever grows past one page.
- **No popup dialogs and no row prices**, so ``price_text`` is never
  available from the list page. Doors times are on the rows.
- Sold-out shows keep their TicketWeb link (the button just reads
  "Sold Out"), so ``ticket_url`` is still captured for them.

Runnable standalone: ``python -m foghorn.scrapers.bimbos_365`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import json

import httpx

from foghorn.models import ScrapedShow
from foghorn.scrapers._ticketweb_calendar import find_next_page_url, parse_calendar_html

VENUE_SLUG = "bimbos_365"

CALENDAR_URL = "https://bimbos365club.com/shows/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0
# Safety valve for the pagination walk; the list is one page today.
MAX_PAGES = 10


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch one shows page. Kept separate from parsing so tests drive
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
    """Fetch the shows list and follow any "Next »" links, returning each
    page's HTML in order."""
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
    """Return one ``ScrapedShow`` per listed show on one page, dated within
    ``[today, today + window_days]``, sorted by ``start_local``."""
    return parse_calendar_html(
        html,
        venue_slug=VENUE_SLUG,
        today=today,
        window_days=window_days,
        fallback_source_url=CALENDAR_URL,
    )


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live show list for the next ~90 days."""
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
