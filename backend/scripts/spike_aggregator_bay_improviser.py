# SPIKE — not production.
"""Discovery probe for issue #29 (aggregator evaluation).

Hits Bay Improviser's public calendar (https://www.bayimproviser.com) over a
date range and dumps the first ~10 parsed events as JSON to stdout. Proves the
"Recommend" verdict in docs/spikes/aggregator-evaluation/bay-improviser.md is
actually reachable from the foghorn backend runtime.

NOT production code: not registered in REGISTERED_SCRAPERS, no DB side effects,
no normalization into ScrapedShow. It parses each event's embedded Google
Calendar (`gCal`) link, whose query string already carries title / start-end /
location — a self-contained structured surface that rides on the HTML.

Run:  python backend/scripts/spike_aggregator_bay_improviser.py
Deps: httpx + beautifulsoup4 (already backend runtime deps).
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

BASE = "https://www.bayimproviser.com"
PACIFIC = ZoneInfo("America/Los_Angeles")
# Polite, honest UA + one request — matches the "respectful, low-volume" posture
# the memo recommends for this volunteer-run community site.
UA = "foghorn-spike/0.0 (github.com/diegoSQK/foghorn issue #29; aggregator evaluation)"


def fetch_calendar(window_days: int = 21) -> str:
    today = datetime.now(PACIFIC).date()
    end = today + timedelta(days=window_days)
    url = f"{BASE}/calendar.aspx"
    params = {"s": today.strftime("%m/%d/%Y"), "e": end.strftime("%m/%d/%Y")}
    resp = httpx.get(url, params=params, headers={"User-Agent": UA}, timeout=30.0)
    resp.raise_for_status()
    return resp.text


def _parse_gcal_dates(raw: str) -> tuple[str | None, str | None]:
    """`dates=20260530T023000Z/20260530T043000Z` -> (start_local, end_local).

    Google Calendar timestamps are UTC; the memo flags that ingest must convert
    UTC -> America/Los_Angeles, so we demonstrate that here.
    """
    if "/" not in raw:
        return None, None
    out: list[str | None] = []
    for part in raw.split("/", 1):
        try:
            if part.endswith("Z"):
                dt = datetime.strptime(part, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                out.append(dt.astimezone(PACIFIC).strftime("%Y-%m-%d %H:%M"))
            else:  # all-day / date-only
                out.append(datetime.strptime(part[:8], "%Y%m%d").strftime("%Y-%m-%d"))
        except ValueError:
            out.append(None)
    return out[0], out[1]


def parse_events(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "google.com/calendar" not in href and "calendar.google.com" not in href:
            continue
        qs = parse_qs(urlparse(href).query)
        text = (qs.get("text") or [""])[0].strip()
        if not text or text in seen:
            continue
        seen.add(text)
        start_local, end_local = _parse_gcal_dates((qs.get("dates") or [""])[0])
        events.append(
            {
                "title_raw": text,  # free-text blob, NOT a clean headliner (see memo §5)
                "start_local": start_local,
                "end_local": end_local,
                "location_raw": (qs.get("location") or [""])[0].strip() or None,
            }
        )
    return events


def main() -> int:
    try:
        html = fetch_calendar()
    except httpx.HTTPError as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1
    events = parse_events(html)
    print(json.dumps(events[:10], indent=2, ensure_ascii=False))
    print(f"\n# parsed {len(events)} events total (showing first 10)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
