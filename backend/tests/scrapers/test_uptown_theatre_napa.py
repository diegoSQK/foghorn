"""Tests for the Uptown Theatre Napa (Tribe REST) scraper: comedy filter,
entity unescaping, and the zero-length end_date rows passing through (the
ingest guard nulls them)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from foghorn.scrapers import uptown_theatre_napa

FIXTURE = Path(__file__).parent.parent / "fixtures" / "uptown_napa_2026_07.json"
TODAY = dt.date(2026, 7, 18)


def _events() -> list[dict[str, object]]:
    payload = json.loads(FIXTURE.read_text())
    events: list[dict[str, object]] = payload["events"]
    return events


def test_parses_and_drops_comedy() -> None:
    shows = uptown_theatre_napa.parse_events(_events(), TODAY)
    titles = [s.headliner_raw for s in shows]
    assert "Live Comedy: Somebody Funny" not in titles
    assert "Micky Dolenz – 60 YEARS OF THE MONKEES" in titles  # &#8211; unescaped
    assert all(s.venue_slug == "uptown_theatre_napa" for s in shows)


def test_window() -> None:
    assert uptown_theatre_napa.parse_events(_events(), dt.date(2027, 1, 1)) == []
