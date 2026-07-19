"""San Francisco Symphony group feed (aggregator source).

The Symphony is a performing *group*, not a venue: its season plays Davies
Symphony Hall mostly, plus the Legion of Honor chamber series, SoundBox,
and off-site one-offs (Stern Grove, Frost Amphitheater, library community
shows). It therefore ingests as an **aggregator source** — each event names
the hall it actually happens in, venue resolution routes it to a seeded
venue row or a quarantined auto-created one, and the ensemble itself rides
every bill as a support performer so the performer watchlist follows the
group across halls (any-performer matching).

Source: sfsymphony.org is a Kentico site whose calendar grid is rendered
client-side from a **public Algolia index** (``prod_sfs_calendar``). The app
id + search-only API key ship embedded in the calendar page's inline
``var settings = {...}`` block, and Algolia's REST endpoint returns one JSON
hit per performance — ``performanceDate`` is already a naive Pacific-local
ISO datetime, exactly the contract shape. Querying Algolia directly also
sidesteps the **Queue-it waiting room** that fronts sfsymphony.org itself on
on-sale days (plain fetches of the page get a 2KB queue interstitial, which
is why this feed must never fall back to scraping the site HTML).

**Credential posture.** The Algolia app id / search key / index name below
are the site's own public browse credentials, served to every visitor in the
page source. If they rotate, the query fails loudly (403) — re-extract them
from view-source of ``https://www.sfsymphony.org/Calendar`` (the inline
``settings`` JSON in ``<main>``).

**Venue-field quirks** (observed 2026-07): ``SoundBox Space`` is the
experimental room inside Davies (folded into Davies until it earns its own
row); ``Youth Orchestra`` is the org mistakenly in the venue field (their YO
concerts play Davies); ``Display Name`` is an unfilled placeholder. Hits
with no usable hall land in a quarantined "San Francisco Symphony Offsite"
bucket — hidden from the main UI, still surfaced by the watchlist bypass.

Runnable standalone: ``python -m foghorn.aggregators.sf_symphony`` prints
the events as JSON and exits. No DB writes here — that's the ingest layer.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from typing import Any

import httpx

from foghorn.aggregators.models import AggregatedEvent

SOURCE_ID = "sf_symphony"
GROUP_NAME = "San Francisco Symphony"

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

# Quarantined bucket for hits whose hall can't be determined.
OFFSITE_VENUE = "San Francisco Symphony Offsite"
# Source venue strings that are rooms-within/organizational quirks, not
# independently seedable halls (see module docstring).
_VENUE_NORMALIZATION = {
    "SoundBox Space": "Davies Symphony Hall",
    "Youth Orchestra": "Davies Symphony Hall",
}
_VENUE_PLACEHOLDERS = frozenset({"", "Display Name", "TBA", "TBD"})

_TAG_RE = re.compile(r"<[^>]+>")
_ISO_LOCAL = "%Y-%m-%dT%H:%M:%S"


def _clean_title(raw: str) -> str:
    """Strip the ``<em>`` markup Algolia titles carry, unescape entities, and
    collapse whitespace."""
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub("", raw))).strip()


def _venue_name(hit: dict[str, Any]) -> str:
    raw = str(hit.get("venue") or "").strip()
    raw = _VENUE_NORMALIZATION.get(raw, raw)
    return OFFSITE_VENUE if raw in _VENUE_PLACEHOLDERS else raw


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
) -> list[AggregatedEvent]:
    """Algolia hits → ``AggregatedEvent``s in ``[today, today + window_days]``.
    Pure / fixture-testable. Skips ``excludeFromCalendar`` hits and anything
    without a parseable title + ``performanceDate``."""
    window_end = today + dt.timedelta(days=window_days)
    events: list[AggregatedEvent] = []
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
        events.append(
            AggregatedEvent(
                venue_name_raw=_venue_name(hit),
                headliner_raw=title,
                support_raw=[GROUP_NAME],
                start_local=start_local,
                ticket_url=event_url,
                source_url=event_url or CALENDAR_URL,
            )
        )
    events.sort(key=lambda event: event.start_local)
    return events


def scrape() -> list[AggregatedEvent]:
    """Fetch and parse the live season for the next ~180 days."""
    today = dt.date.today()
    return parse_hits(fetch_hits(today), today)


def main() -> None:
    events = scrape()
    print(
        json.dumps(
            [event.model_dump(mode="json") for event in events],
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
