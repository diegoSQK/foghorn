"""Tests for the Chez Hanny (static homepage) scraper, driven from the
real page: name/date/time/price tuples, header-word stripping on the
first entry, and window enforcement."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from foghorn.scrapers import chez_hanny

FIXTURE = Path(__file__).parent.parent / "fixtures" / "chez_hanny_2026_07.html"


def test_parses_all_listed_shows() -> None:
    shows = chez_hanny.parse_page(FIXTURE.read_text(), dt.date(2026, 7, 18))
    assert [(s.headliner_raw, s.start_local, s.price_text) for s in shows] == [
        ("Aaron Bennett Trio", dt.datetime(2026, 7, 19, 16, 0), "$25"),
        ("Ron Vincent Quartet", dt.datetime(2026, 8, 16, 16, 0), "$25"),
        ("Frank Martin Trio", dt.datetime(2026, 8, 30, 16, 0), "$25"),
        ("Alon Nechushtan Quintet", dt.datetime(2026, 9, 13, 16, 0), "$25"),
    ]


def test_window() -> None:
    shows = chez_hanny.parse_page(FIXTURE.read_text(), dt.date(2026, 9, 1))
    assert [s.headliner_raw for s in shows] == ["Alon Nechushtan Quintet"]
