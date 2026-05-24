"""Tests for the Bird & Beckett iCal parser.

Fixture-driven and deterministic: ``parse_ics`` takes an injected ``today`` so
the recurrence window doesn't depend on the clock. The fixture
(``fixtures/bird_and_beckett_sample.ics``) is a curated subset exercising the
edge cases — TZID vs UTC times, a non-music event, an all-day entry, a weekly
recurring residency, an accented name, and an out-of-window event.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import bird_and_beckett

FIXTURE = Path(__file__).parent.parent / "fixtures" / "bird_and_beckett_sample.ics"
TODAY = dt.date(2026, 6, 1)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return bird_and_beckett.parse_ics(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-06-05T19:30:00", "David Parker Sextet"),  # one-time TZID
        ("2026-06-06T20:00:00", "Klaxon Mutant All-Stars"),  # UTC -> PT
        ("2026-06-07T17:00:00", "Sunday Happy Hour - The Vince Lateano Trio"),
        ("2026-06-10T20:00:00", "Café Tacvba"),  # accent preserved in display
        ("2026-06-14T17:00:00", "Sunday Happy Hour - The Vince Lateano Trio"),
        ("2026-06-21T17:00:00", "Sunday Happy Hour - The Vince Lateano Trio"),
        ("2026-06-28T17:00:00", "Sunday Happy Hour - The Vince Lateano Trio"),
    ]


def test_excludes_non_music(parsed: list[ScrapedShow]) -> None:
    assert not any("Poets!" in s.headliner_raw for s in parsed)


def test_excludes_all_day(parsed: list[ScrapedShow]) -> None:
    assert not any("Glen Park Festival" in s.headliner_raw for s in parsed)


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    assert not any(s.headliner_raw == "Future Act" for s in parsed)


def test_recurring_series_expanded(parsed: list[ScrapedShow]) -> None:
    lateano = [s for s in parsed if "Lateano" in s.headliner_raw]
    assert len(lateano) == 4  # weekly COUNT=4


def test_utc_event_converted_to_local(parsed: list[ScrapedShow]) -> None:
    klaxon = next(s for s in parsed if s.headliner_raw == "Klaxon Mutant All-Stars")
    # DTSTART:20260607T030000Z == 8pm PDT on June 6; start_local is naive PT.
    assert klaxon.start_local == dt.datetime(2026, 6, 6, 20, 0)


def test_window_size_is_respected() -> None:
    # A 5-day window from today should only catch the June 5 one-time event.
    shows = bird_and_beckett.parse_ics(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=5
    )
    assert [s.headliner_raw for s in shows] == ["David Parker Sextet"]


def test_optional_fields_are_none(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.support_raw == []
    assert show.doors_local is None
    assert show.ticket_url is None
    assert show.price_text is None
    assert show.source_url == bird_and_beckett.SOURCE_URL
    assert show.venue_slug == "bird_and_beckett"
