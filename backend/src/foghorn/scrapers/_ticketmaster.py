"""Shared Ticketmaster Discovery API parsing for TM-ticketed venues.

The sanctioned first-party door to Live Nation/Goldenvoice rooms whose sites
block scraping (see docs/spikes/ticketmaster-discovery/RECOMMENDATION.md for
the ToS analysis and venue-ID discovery). Needs ``TM_API_KEY`` in the
environment or gitignored ``backend/.env`` (free self-serve key) — a
missing key raises so the scrape-health surface shows the venue as errored
rather than silently empty.

Field mapping: ``_embedded.attractions[]`` is the bill in billing order
(headliner first); ``dates.start.localDate/localTime`` are already
venue-local (naive, per the ScrapedShow contract); ``classifications`` give
a per-event genre string for the override layer; ``priceRanges`` → price
text; cancelled/postponed status codes are dropped.
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Any

import httpx

from foghorn.localenv import load_local_env
from foghorn.models import ScrapedShow

EVENTS_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0
PAGE_SIZE = 100  # both rooms list well under this per 90 days

_DROP_STATUS = {"cancelled", "canceled", "postponed", "rescheduled"}


def _api_key() -> str:
    load_local_env()  # gitignored backend/.env may carry it
    key = os.environ.get("TM_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "TM_API_KEY not set (add it to gitignored backend/.env) — "
            "Ticketmaster venues can't scrape without it"
        )
    return key


def fetch_events(venue_id: str, today: dt.date | None = None) -> dict[str, Any]:
    """One Discovery API page of upcoming events for ``venue_id`` (both rooms
    fit in a single page for the 90-day window)."""
    start = today or dt.date.today()
    end = start + dt.timedelta(days=SCRAPE_WINDOW_DAYS)
    response = httpx.get(
        EVENTS_URL,
        params={
            "apikey": _api_key(),
            "venueId": venue_id,
            "size": PAGE_SIZE,
            "sort": "date,asc",
            "startDateTime": f"{start.isoformat()}T00:00:00Z",
            "endDateTime": f"{end.isoformat()}T23:59:59Z",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    assert isinstance(data, dict)
    return data


def _price_text(event: dict[str, Any]) -> str | None:
    ranges = event.get("priceRanges")
    if not isinstance(ranges, list) or not ranges:
        return None
    lows = [r.get("min") for r in ranges if isinstance(r.get("min"), int | float)]
    highs = [r.get("max") for r in ranges if isinstance(r.get("max"), int | float)]
    if not lows or not highs:
        return None
    low, high = min(lows), max(highs)
    if low == high:
        return f"${low:.2f}"
    return f"${low:.2f}–${high:.2f}"


# Discovery's top-level segment. Only "Arts & Theatre" is dropped, and at these
# venues it is entirely stand-up comedy — Chelsea Handler, John Mulaney, Daniel
# Sloss and the like, which a music calendar shouldn't carry. Deliberately
# narrow: "Undefined" and "Miscellaneous" are kept, because TM leaves plenty of
# real gigs unclassified (a sixth of the Regency's listings), and dropping
# those would lose shows to win a tidier taxonomy.
_NON_MUSIC_SEGMENTS = frozenset({"arts & theatre"})


def _is_non_music(event: dict[str, Any]) -> bool:
    for cls in event.get("classifications") or []:
        if not isinstance(cls, dict):
            continue
        segment = ((cls.get("segment") or {}).get("name") or "").strip().lower()
        return segment in _NON_MUSIC_SEGMENTS
    return False


def _genre(event: dict[str, Any]) -> str | None:
    for cls in event.get("classifications") or []:
        if not isinstance(cls, dict):
            continue
        parts = [
            (cls.get(level) or {}).get("name")
            for level in ("genre", "subGenre", "segment")
        ]
        text = " / ".join(p for p in parts if p and p != "Undefined")
        if text:
            return text
    return None


def parse_events(
    payload: dict[str, Any],
    venue_slug: str,
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[ScrapedShow]:
    """Map a Discovery payload to ``ScrapedShow``s in the window. Pure /
    fixture-testable. Events without a local date+time (TBA) or with a
    cancelled/postponed status are skipped."""
    embedded = payload.get("_embedded")
    events = embedded.get("events") if isinstance(embedded, dict) else None
    if not isinstance(events, list):
        return []
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if _is_non_music(event):
            continue
        dates = event.get("dates") or {}
        status = ((dates.get("status") or {}).get("code") or "").lower()
        if status in _DROP_STATUS:
            continue
        start = dates.get("start") or {}
        local_date, local_time = start.get("localDate"), start.get("localTime")
        if not (isinstance(local_date, str) and isinstance(local_time, str)):
            continue  # TBA — never invent a time
        try:
            start_local = dt.datetime.fromisoformat(f"{local_date}T{local_time}")
        except ValueError:
            continue
        if not (today <= start_local.date() <= window_end):
            continue

        attractions = (event.get("_embedded") or {}).get("attractions") or []
        names = [
            a.get("name", "").strip()
            for a in attractions
            if isinstance(a, dict) and a.get("name")
        ]
        headliner = names[0] if names else str(event.get("name", "")).strip()
        if not headliner:
            continue
        url = event.get("url") if isinstance(event.get("url"), str) else None

        shows.append(
            ScrapedShow(
                venue_slug=venue_slug,
                headliner_raw=headliner,
                support_raw=names[1:],
                start_local=start_local,
                doors_local=None,  # not exposed by the Discovery API
                ticket_url=url,
                price_text=_price_text(event),
                source_url=url or EVENTS_URL,
                genre=_genre(event),
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows
