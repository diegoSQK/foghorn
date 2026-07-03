"""Tests for the Piedmont Piano Company Squarespace-JSON parser.

The fixture is a trimmed snapshot of the live ``/calendar?format=json``
collection — ten real concerts (evening + matinee start times, an ampersand
title, a curly-apostrophe title) plus a far-future copy for the window test.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import piedmont_piano

FIXTURE = Path(__file__).parent.parent / "fixtures" / "piedmont_piano_2026_07.json"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return piedmont_piano.parse_events(payload, today=TODAY)


def test_concerts_parsed_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got[:4] == [
        ("2026-07-02T17:30:00", "Amendola Vs. Blades"),
        ("2026-07-12T17:00:00", "Charles Chen Quartet"),
        ("2026-07-18T17:30:00", "Luther S. Allison Trio"),
        ("2026-07-25T17:30:00", "Dick Whittington, 90th Birthday"),
    ]
    assert len(got) == 10


def test_entities_and_typography_unescaped(parsed: list[ScrapedShow]) -> None:
    names = {s.headliner_raw for s in parsed}
    assert "Aimee Nolte & Mike Scott" in names  # &amp; in the raw JSON
    assert "Bill O’Connell Trio" in names  # curly apostrophe preserved


def test_out_of_window_excluded(parsed: list[ScrapedShow]) -> None:
    assert not any(s.headliner_raw == "Out Of Window Ensemble" for s in parsed)


def test_window_size_is_respected(parsed: list[ScrapedShow]) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    week = piedmont_piano.parse_events(payload, today=TODAY, window_days=7)
    assert [s.headliner_raw for s in week] == ["Amendola Vs. Blades"]


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    assert all(
        s.source_url.startswith("https://piedmontpiano.com/calendar/") for s in parsed
    )


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "piedmont_piano"
    assert show.support_raw == []
    assert show.doors_local is None
