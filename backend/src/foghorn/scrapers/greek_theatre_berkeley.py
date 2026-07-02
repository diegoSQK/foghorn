"""Greek Theatre Berkeley scraper.

Source: the venue's own WordPress site. The Greek (2001 Gayley Rd on the UC
Berkeley campus, an Another Planet Entertainment amphitheatre) server-renders
its full upcoming-shows list on one ``/event-listing/`` page using the APE
listing template — every show is a ``div.mix.detail-information`` block with
headliner, optional topline/support lines, a microdata start datetime, doors
time, per-event page link, and a Ticketmaster purchase link. ~23 shows, months
ahead, no pagination and no JS execution needed, so plain ``httpx`` +
``beautifulsoup4`` suffice. The shared template parsing lives in
``_ape_listing`` (Fox Theater Oakland runs the same theme).

Quirks: sold-out shows swap the "Buy Tickets" button for a "Sold Out!" one
that still links Ticketmaster — the shared parser keeps it as ``ticket_url``.
No prices appear on the listing.

Runnable standalone: ``python -m foghorn.scrapers.greek_theatre_berkeley``
prints the scraped shows as JSON and exits. No DB writes here — that's the
ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json

import httpx

from foghorn.models import ScrapedShow
from foghorn.scrapers._ape_listing import parse_listing_html

VENUE_SLUG = "greek_theatre_berkeley"

CALENDAR_URL = "https://thegreekberkeley.com/event-listing/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch the event-listing page. Kept separate from parsing so tests drive
    ``parse_html`` from a fixture without touching the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per listed show dated within
    ``[today, today + window_days]``, sorted by ``start_local``."""
    return parse_listing_html(
        html,
        venue_slug=VENUE_SLUG,
        today=today,
        window_days=window_days,
        fallback_source_url=CALENDAR_URL,
    )


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live listing for the next ~90 days."""
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
