"""Tests for the Little Lou's BBQ parser, driven from the page's
server-rendered Simple Calendar widget: naive local start/end from the ISO
``content`` attributes, the Pro Blues Jam ``event_type`` tag, and window
enforcement."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from foghorn.scrapers import little_lous_bbq

FIXTURE = Path(__file__).parent.parent / "fixtures" / "little_lous_bbq_2026_07.html"
TODAY = dt.date(2026, 7, 19)


def test_parses_events_with_stated_ends() -> None:
    shows = little_lous_bbq.parse_html(FIXTURE.read_text(encoding="utf-8"), TODAY)
    assert [
        (s.headliner_raw, s.start_local.isoformat(), s.end_local and s.end_local.isoformat())
        for s in shows
    ] == [
        ("Whistle Creek", "2026-07-22T18:00:00", "2026-07-22T21:00:00"),
        ("Pro Blues Jam", "2026-07-23T18:00:00", "2026-07-23T21:00:00"),
        ("Grace and The Grit", "2026-07-24T19:30:00", "2026-07-24T22:30:00"),
        ("Luke Piro Band", "2026-07-25T19:30:00", "2026-07-25T22:30:00"),
    ]


def test_blues_jam_is_typed_jam() -> None:
    shows = little_lous_bbq.parse_html(FIXTURE.read_text(encoding="utf-8"), TODAY)
    assert [(s.headliner_raw, s.event_type) for s in shows if s.event_type == "jam"] == [
        ("Pro Blues Jam", "jam")
    ]


def test_window() -> None:
    shows = little_lous_bbq.parse_html(
        FIXTURE.read_text(encoding="utf-8"), dt.date(2026, 7, 24)
    )
    assert [s.headliner_raw for s in shows] == ["Grace and The Grit", "Luke Piro Band"]
