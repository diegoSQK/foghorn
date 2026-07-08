# SPIKE — not production.
"""POC for the Ticketmaster Discovery API spike.

Fetches upcoming events for The Fillmore (SF) and The Regency Ballroom (SF) —
the two Live Nation/Goldenvoice rooms that block scraping — and prints them as
ScrapedShow-shaped JSON. Demonstrates the field mapping described in
docs/spikes/ticketmaster-discovery/RECOMMENDATION.md.

NOT production code: no DB side effects, no real ScrapedShow construction, no
registration in REGISTERED_SCRAPERS. Written without a live key (untested-live);
first action after key signup is to run it and eyeball output vs. the TM venue
pages.

Run:  TM_API_KEY=... python backend/scripts/spike_ticketmaster_discovery.py
Key:  free, instant — https://developer-acct.ticketmaster.com/user/register
Deps: httpx (already a backend runtime dep).
"""
from __future__ import annotations

import json
import os
import sys

import httpx

BASE = "https://app.ticketmaster.com/discovery/v2/events.json"
# Discovery venue IDs found via public livenation.com venue URLs (see memo §6).
VENUES = {
    "KovZpZAE6eeA": "the_fillmore",  # legacy TM page 229424
    "KovZpZAEet6A": "regency_ballroom",  # legacy TM page 229653
}


def fetch_events(api_key: str, venue_id: str) -> list[dict]:
    resp = httpx.get(
        BASE,
        params={
            "apikey": api_key,
            "venueId": venue_id,
            "sort": "date,asc",
            "size": 100,  # both rooms list <100 upcoming; no pagination needed
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return (resp.json().get("_embedded") or {}).get("events") or []


def to_scraped_show(raw: dict, venue_slug: str) -> dict | None:
    """Map one Discovery event to a ScrapedShow-shaped dict (None = skip)."""
    dates = raw.get("dates") or {}
    status = ((dates.get("status") or {}).get("code") or "").lower()
    if status in ("cancelled", "canceled"):
        return None  # scrapers can't always see these; the API flags them
    start = dates.get("start") or {}
    local_date, local_time = start.get("localDate"), start.get("localTime")
    if not local_date or not local_time or start.get("timeTBA"):
        return None  # TBA/TBD — no naive start_local possible yet
    attractions = (raw.get("_embedded") or {}).get("attractions") or []
    names = [a["name"] for a in attractions if a.get("name")]
    headliner = names[0] if names else (raw.get("name") or "").strip()
    if not headliner:
        return None
    genre = None
    for c in raw.get("classifications") or []:
        if c.get("primary") and (c.get("genre") or {}).get("name"):
            genre = c["genre"]["name"]  # passthrough; normalized at ingest
            break
    price_text = None
    for pr in raw.get("priceRanges") or []:
        lo, hi = pr.get("min"), pr.get("max")
        if lo is not None and hi is not None:
            price_text = f"${lo:.0f}" if lo == hi else f"${lo:.0f}–${hi:.0f}"
            break
    return {
        "venue_slug": venue_slug,
        "headliner_raw": headliner,
        "support_raw": names[1:],  # attractions[] is the bill, in billing order
        "start_local": f"{local_date}T{local_time}",  # naive; tz applied at ingest
        "doors_local": None,  # Discovery publishes showtime only (memo §1)
        "ticket_url": raw.get("url"),
        "price_text": price_text,
        "source_url": raw.get("url"),
        "event_type": None,
        "genre": genre,
    }


def main() -> int:
    api_key = os.environ.get("TM_API_KEY", "").strip()
    if not api_key:
        print(
            "TM_API_KEY is not set. Get a free key (instant, no approval) at\n"
            "https://developer-acct.ticketmaster.com/user/register then run:\n"
            "  TM_API_KEY=<consumer key> python backend/scripts/spike_ticketmaster_discovery.py",
            file=sys.stderr,
        )
        return 2
    shows: list[dict] = []
    for venue_id, slug in VENUES.items():
        try:
            events = fetch_events(api_key, venue_id)
        except httpx.HTTPError as exc:
            print(f"fetch failed for {slug} ({venue_id}): {exc}", file=sys.stderr)
            return 1
        mapped = [s for e in events if (s := to_scraped_show(e, slug))]
        print(f"# {slug}: {len(events)} events, {len(mapped)} mapped", file=sys.stderr)
        shows.extend(mapped)
    print(json.dumps(shows, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
