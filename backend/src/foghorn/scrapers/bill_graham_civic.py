"""Bill Graham Civic Auditorium scraper.

Source: the venue's own WordPress site. Bill Graham (99 Grove St, Civic Center,
~7,000 capacity, an Another Planet Entertainment room) server-renders its full
upcoming-shows list on one ``/calendar/`` page using the APE listing template,
so plain ``httpx`` + ``beautifulsoup4`` suffice — no pagination, no JS.

**Use ``/calendar/``, not ``/events/``.** The latter still serves a
pandemic-era "Postponed Shows" page: explanatory copy about rescheduling and
no current listings. It looks like a working calendar that returns nothing.

This room runs a **newer generation** of the APE theme than the Fox and the
Greek — ``article.event`` blocks, ``div.bottomline`` support, an
``a.more-info`` event link, and a sortable ``p.event__start-date`` content
attribute. Both generations are read by ``_ape_listing``, which is where that
difference is described; this module stays the thin wrapper the helper's
docstring asks for.

Quirks the shared parser already handles: rescheduled and cancelled shows stay
listed with a topline banner (cancelled ones are dropped, rescheduled ones
kept — the date shown is the new one), the room also books comedy and
conventions, and no prices appear anywhere on the template.

Runnable standalone: ``python -m foghorn.scrapers.bill_graham_civic`` prints
the scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import json

import httpx

from foghorn.models import ScrapedShow
from foghorn.scrapers._ape_listing import parse_listing_html

VENUE_SLUG = "bill_graham_civic"

CALENDAR_URL = "https://billgrahamcivic.com/calendar/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 120
REQUEST_TIMEOUT = 30.0


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch the calendar page. Kept separate from parsing so tests drive
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
    """Fetch and parse the live calendar for the next ~120 days."""
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
