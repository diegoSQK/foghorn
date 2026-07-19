"""Little Lou's BBQ scraper.

Source: the Campbell BBQ joint's WordPress site — ``/calender/`` (the
misspelling is the real path) embeds a Google Calendar iframe, but the
sidebar's *Simple Calendar* widget renders the same feed server-side:
one ``li.simcal-event`` per show with the act in ``.simcal-event-title``
and full ISO local datetimes (offset included) in the start/end spans'
``content`` attributes, so start *and* stated end both come through.
The widget only renders the current period (a handful of rows), so
volume is small per scrape. The Thursday "Pro Blues Jam" is tagged
``event_type="jam"`` explicitly; all-day rows (no clocked start) and
private-party rows are skipped.

Runnable standalone: ``python -m foghorn.scrapers.little_lous_bbq``
prints the scraped shows as JSON and exits. No DB writes here — that's
the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "little_lous_bbq"

CALENDAR_URL = "https://littlelousbbq.com/calender/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

_JAM_RE = re.compile(r"\bjam\b", re.IGNORECASE)
# Closures and buyouts, not shows.
_NON_MUSIC_RE = re.compile(r"private (?:party|event)|\bclosed\b", re.IGNORECASE)


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


def _local_datetime(event: Tag, selector: str) -> dt.datetime | None:
    """The ISO local datetime in a span's ``content`` attribute
    ("2026-07-22T18:00:00-07:00"), returned naive — the offset is the
    venue's own and is applied at ingest."""
    span = event.select_one(selector)
    if span is None:
        return None
    content = span.get("content")
    if not isinstance(content, str):
        return None
    try:
        return dt.datetime.fromisoformat(content).replace(tzinfo=None)
    except ValueError:
        return None


def parse_html(
    page_html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Calendar page → one ``ScrapedShow`` per Simple Calendar event row in
    ``[today, today + window_days]``. ``today`` is injected so the window
    is deterministic and fixture-testable. Pure."""
    soup = BeautifulSoup(page_html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    for event in soup.select("li.simcal-event"):
        title_node = event.select_one(".simcal-event-title")
        if title_node is None:
            continue
        title = " ".join(title_node.get_text().split())
        if not title or _NON_MUSIC_RE.search(title):
            continue
        # The -time span only exists for clocked events; all-day rows carry
        # a bare date and are skipped rather than given a fabricated time.
        start = _local_datetime(event, ".simcal-event-start-time")
        if start is None:
            continue
        if not (today <= start.date() <= window_end):
            continue
        end = _local_datetime(event, ".simcal-event-end-time")
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=title,
                support_raw=[],
                start_local=start,
                end_local=end,
                doors_local=None,
                ticket_url=None,
                price_text=None,
                source_url=CALENDAR_URL,
                event_type="jam" if _JAM_RE.search(title) else None,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live calendar for the next ~90 days."""
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
