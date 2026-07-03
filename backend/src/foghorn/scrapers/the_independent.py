"""The Independent scraper.

Source: the venue's own WordPress site. The Independent (628 Divisadero St,
NoPa) renders its full upcoming-shows list server-side on the homepage using
the TicketWeb "tw-" calendar template — every show is a ``div.tw-section``
block with date, headliner, support line, show time, per-event page link, and
TicketWeb purchase link. The whole list (~80 shows, months ahead) is on one
page with no pagination and no JS execution needed, so plain ``httpx`` +
``beautifulsoup4`` suffice. The shared template parsing lives in
``_ticketweb_calendar`` (Cafe du Nord runs the same theme).

Quirks: list dates carry no year ("7.2"), so the shared parser infers it from
``today``; this deployment has no popup dialogs, so doors and price are never
available from the list page.

Runnable standalone: ``python -m foghorn.scrapers.the_independent`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import json

import httpx

from foghorn.models import ScrapedShow
from foghorn.scrapers._ticketweb_calendar import parse_calendar_html

VENUE_SLUG = "the_independent"

CALENDAR_URL = "https://www.theindependentsf.com/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch the homepage show list. Kept separate from parsing so tests drive
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
    return parse_calendar_html(
        html,
        venue_slug=VENUE_SLUG,
        today=today,
        window_days=window_days,
        fallback_source_url=CALENDAR_URL,
    )


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live show list for the next ~90 days."""
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
