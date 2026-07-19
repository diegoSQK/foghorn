"""San Francisco Symphony scraper.

Source: sfsymphony.org is a Kentico site whose calendar grid is rendered
client-side from a **public Algolia index** (``prod_sfs_calendar``). The app
id + search-only API key ship embedded in the calendar page's inline
``var settings = {...}`` block, and Algolia's REST endpoint returns one JSON
hit per performance — ``performanceDate`` is already a naive Pacific-local
ISO datetime, exactly the contract shape. Querying Algolia directly also
sidesteps the **Queue-it waiting room** that fronts sfsymphony.org itself on
on-sale days (plain fetches of the page get a 2KB queue interstitial, which
is why this scraper must never fall back to scraping the site HTML).

**Credential posture.** The Algolia app id / search key / index name below
are the site's own public browse credentials, served to every visitor in the
page source. If they rotate, the query fails loudly (403) — re-extract them
from view-source of ``https://www.sfsymphony.org/Calendar`` (the inline
``settings`` JSON in ``<main>``).

**Filter posture.** Hits with ``excludeFromCalendar`` are dropped; both
``calendarDataType`` values are kept (``TessituraItem`` = ticketed
performances, ``KenticoItem`` = free community performances and specials —
real events with unreliable ``venue`` strings). Like Cal Performances, the
SFS is a presenter row: occasional off-site dates (Stern Grove, Frost
Amphitheater) ride under the same venue rather than spawning per-hall rows.

Runnable standalone: ``python -m foghorn.scrapers.sf_symphony`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from typing import Any

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "sf_symphony"

BASE_URL = "https://www.sfsymphony.org"
CALENDAR_URL = f"{BASE_URL}/Calendar"
# Public search-only credentials embedded in the calendar page (see module
# docstring for the re-extraction path if these rotate).
ALGOLIA_APP_ID = "3ZVEWSXVK4"
ALGOLIA_SEARCH_KEY = "e6c0617a0995d310c9dd600df5af93c2"
ALGOLIA_INDEX = "prod_sfs_calendar"
ALGOLIA_QUERY_URL = (
    f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"
)
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
# Classical programs sell and get planned months out; a season-scale window
# beats the 90-day default used for club calendars.
SCRAPE_WINDOW_DAYS = 180
REQUEST_TIMEOUT = 30.0
# The index caps hitsPerPage at 1000; the full season is currently ~300 rows,
# so one request covers it. If a season ever exceeds this, page via `page=`.
HITS_PER_PAGE = 1000

_TAG_RE = re.compile(r"<[^>]+>")
_ISO_LOCAL = "%Y-%m-%dT%H:%M:%S"


def _clean_title(raw: str) -> str:
    """Strip the ``<em>`` markup Algolia titles carry, unescape entities, and
    collapse whitespace."""
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub("", raw))).strip()


def fetch_hits(today: dt.date, client: httpx.Client | None = None) -> list[dict[str, Any]]:
    """One Algolia query for every performance from ``today`` onward. The
    strict upper window is applied in ``parse_hits`` (injected clock)."""
    since_epoch = int(
        dt.datetime.combine(today, dt.time.min, tzinfo=dt.UTC).timestamp()
    )
    own_client = client is None
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
        )
    try:
        response = client.post(
            ALGOLIA_QUERY_URL,
            headers={
                "x-algolia-application-id": ALGOLIA_APP_ID,
                "x-algolia-api-key": ALGOLIA_SEARCH_KEY,
            },
            json={
                "params": f"hitsPerPage={HITS_PER_PAGE}&query="
                f"&numericFilters=startDate>={since_epoch}"
            },
        )
        response.raise_for_status()
        hits = response.json().get("hits", [])
        return hits if isinstance(hits, list) else []
    finally:
        if own_client:
            client.close()


def parse_hits(
    hits: list[dict[str, Any]],
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[ScrapedShow]:
    """Algolia hits → ``ScrapedShow``s in ``[today, today + window_days]``.
    Pure / fixture-testable. Skips ``excludeFromCalendar`` hits and anything
    without a parseable title + ``performanceDate``."""
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    for hit in hits:
        if hit.get("excludeFromCalendar"):
            continue
        title = _clean_title(str(hit.get("title") or ""))
        date_raw = hit.get("performanceDate")
        if not title or not isinstance(date_raw, str):
            continue
        try:
            start_local = dt.datetime.strptime(date_raw, _ISO_LOCAL)
        except ValueError:
            continue
        if not (today <= start_local.date() <= window_end):
            continue
        kentico_path = str(hit.get("kenticoUrl") or "")
        event_url = (
            f"{BASE_URL}{kentico_path}" if kentico_path.startswith("/") else None
        )
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=title,
                support_raw=[],
                start_local=start_local,
                doors_local=None,
                ticket_url=event_url,
                price_text=None,
                source_url=event_url or CALENDAR_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live season for the next ~180 days."""
    today = dt.date.today()
    return parse_hits(fetch_hits(today), today)


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
