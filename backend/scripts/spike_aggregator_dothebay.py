# SPIKE — not production.
"""Discovery probe for issue #29 (aggregator evaluation).

Hits DoTheBay's undocumented public events JSON endpoint and dumps the first ~10
music events as JSON to stdout. Demonstrates the data shape described in
docs/spikes/aggregator-evaluation/dothebay.md.

ToS NOTE — READ BEFORE PROMOTING THIS: dothebay.com's Terms of Service bar
"scrap[ing], harvest[ing], or misus[ing] content or data" and restrict use to
"personal, non-commercial use only." This script is a ONE-SHOT discovery probe
for the spike only. Do NOT register it in REGISTERED_SCRAPERS or build an ingest
pipeline on it without a permission / licensed-feed arrangement with DoStuff
Media / Noise Pop. The memo's verdict is "Maybe, leaning Skip" for exactly this
reason — the blocker is legal posture, not engineering.

NOT production code: no DB side effects, no normalization into ScrapedShow.

Run:  python backend/scripts/spike_aggregator_dothebay.py
Deps: httpx (already a backend runtime dep). No HTML parsing needed.
"""
from __future__ import annotations

import json
import sys

import httpx

# The DoStuff AJAX backend. `/events/today.json` returns today's listings;
# `?page=N` paginates (25/page). One polite request is enough for a probe.
URL = "https://dothebay.com/events/today.json"
UA = "foghorn-spike/0.0 (github.com/diegoSQK/foghorn issue #29; aggregator evaluation)"


def fetch() -> dict:
    resp = httpx.get(URL, headers={"User-Agent": UA}, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def to_event(raw: dict) -> dict:
    venue = raw.get("venue") or {}
    permalink = raw.get("permalink") or ""
    return {
        "title_raw": raw.get("title"),
        # IMPORTANT (see memo §1): use `tz_adjusted_begin_date` (correct Pacific),
        # NOT `begin_time`, which carries a spurious -06:00 Chicago offset.
        "start_local": raw.get("tz_adjusted_begin_date"),
        "venue": venue.get("title"),
        "venue_id": venue.get("id"),  # stable numeric id — the clean venue anchor
        "ticket_url": raw.get("buy_url"),
        "price_text": raw.get("ticket_info"),
        "source_url": f"https://dothebay.com{permalink}" if permalink else None,
        # `artists` is populated for big rooms, empty for small jazz rooms (see memo §5)
        "artists": [a.get("title") for a in (raw.get("artists") or [])],
    }


def main() -> int:
    try:
        payload = fetch()
    except httpx.HTTPError as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1
    events = payload.get("events") or []
    music = [e for e in events if (e.get("category") or "").lower() == "music"]
    print(json.dumps([to_event(e) for e in music[:10]], indent=2, ensure_ascii=False))
    print(
        f"\n# {len(music)} music of {len(events)} events on this page "
        f"(total_pages={(payload.get('paging') or {}).get('total_pages')})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
