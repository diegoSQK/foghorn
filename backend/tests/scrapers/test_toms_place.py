"""Tests for the Tom's Place (static page) scraper, driven from the real
page: onsite entries kept with the page-stated 7:30 default, offsite
presentations (address lines — SFPL, Gray Area, The Lab) skipped, and
multi-day festival ranges skipped."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from foghorn.scrapers import toms_place

FIXTURE = Path(__file__).parent.parent / "fixtures" / "toms_place_2026_07.html"


def test_onsite_entries_only_with_default_time() -> None:
    shows = toms_place.parse_page(FIXTURE.read_text(), dt.date(2026, 7, 18))
    titles = [s.headliner_raw for s in shows]
    assert "NEWT POOL (Cheryl Leonard + Wobbly)" in titles
    # Offsite presentations (SFPL panel, Gray Area gala, The Lab festival)
    # are other venues' shows — all skipped.
    assert not any("SFEMF" in t for t in titles)
    assert all(s.start_local.time() == dt.time(19, 30) for s in shows)


def test_window() -> None:
    assert toms_place.parse_page(FIXTURE.read_text(), dt.date(2027, 7, 1)) == []
