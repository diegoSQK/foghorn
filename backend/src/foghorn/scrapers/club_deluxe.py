"""Club Deluxe scraper.

Source: the venue's own WordPress site. Club Deluxe (a nightly jazz/swing bar at
1511 Haight St) publishes ``/calendar/`` rendered by the "Simple Calendar"
(simcal) Google Calendar plugin as a server-side list of day ``<dt>`` labels and
``<li class="simcal-event">`` items. Each item carries the event's epoch start
in ``data-start`` and a title like ``"Tony Peebles Quartet $15"`` — the cover
charge rides in the title; there is no ticketing platform and no per-event page.

Plain ``httpx`` + ``beautifulsoup4`` suffice — the current ~2-month window is in
the initial HTML (month paging is AJAX, not needed for a 90-day horizon since
the venue posts about two months out). Quirks handled here: ``CLOSED`` day
markers, all-day banner events (simcal gives them a ``:59``-second
``data-start``, e.g. the "OSL" festival note), and late shows re-listed under
the following day with the *same* ``data-start`` (deduped).

Runnable standalone: ``python -m foghorn.scrapers.club_deluxe`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from foghorn.models import ScrapedShow

VENUE_SLUG = "club_deluxe"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

CALENDAR_URL = "https://thedeluxesf.com/calendar/"
# No per-event pages exist; every show's provenance is the calendar page.
SOURCE_URL = CALENDAR_URL
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# Trailing cover charge in the title: "Cosmo Alleycats $15" → ("$15").
_PRICE_RE = re.compile(r"\s*(\$\d+(?:\.\d{2})?)\s*$")

# Day-status markers the calendar mixes in with shows; never a performer.
_NON_SHOW_TITLES = frozenset({"closed"})


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


def _clean(text: str) -> str:
    return " ".join(text.split())


def _split_price(title: str) -> tuple[str, str | None]:
    """Split "Miles Turk $15" into ("Miles Turk", "$15"). Titles without a
    trailing dollar amount come back with ``None`` price."""
    match = _PRICE_RE.search(title)
    if match is None:
        return title, None
    return title[: match.start()].rstrip(), match.group(1)


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per simcal event whose local date falls in
    ``[today, today + window_days]``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable. ``data-start`` is an epoch instant; it
    is rendered in the venue's tz and stored naive per the scraper contract.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    seen: set[tuple[dt.datetime, str]] = set()
    for li in soup.select("li.simcal-event"):
        title_span = li.select_one("span.simcal-event-title")
        raw_start = li.get("data-start")
        if title_span is None or not isinstance(raw_start, str):
            continue
        title = _clean(title_span.get_text(" ", strip=True))
        if not title or title.lower() in _NON_SHOW_TITLES:
            continue

        instant = dt.datetime.fromtimestamp(int(raw_start), tz=VENUE_TZ)
        # All-day banner events (venue notes like "OSL") get a :59-second
        # midnight-ish data-start from simcal; they aren't shows.
        if instant.second != 0:
            continue
        start_local = instant.replace(tzinfo=None)
        if not (today <= start_local.date() <= window_end):
            continue

        # A late set is re-listed under the next day's <dt> with an identical
        # data-start; keep the first occurrence only.
        key = (start_local, title)
        if key in seen:
            continue
        seen.add(key)

        headliner, price_text = _split_price(title)
        if not headliner:
            continue
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=[],
                start_local=start_local,
                doors_local=None,
                ticket_url=None,
                price_text=price_text,
                source_url=SOURCE_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live calendar page for the next ~90 days."""
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
