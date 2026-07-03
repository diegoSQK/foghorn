"""Tests for the Ivy Room Venuepilot parser.

Fixture-driven and deterministic: ``parse_events`` takes an injected ``today``
so the 90-day window doesn't depend on the clock. The fixture
(``fixtures/ivy_room_2026_07.json``) is a trimmed snapshot of the live
Venuepilot GraphQL ``paginatedEvents`` collection exercising the edge cases —
two shows on one day, a "+"-packed bill, a "TBD" support placeholder, a free
happy-hour entry with no price/ticket URL, a postponed show, and an October
event excluded by the window.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import ivy_room

FIXTURE = Path(__file__).parent.parent / "fixtures" / "ivy_room_2026_07.json"
TODAY = dt.date(2026, 7, 2)


def _events() -> list[dict[str, object]]:
    data: list[dict[str, object]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return ivy_room.parse_events(_events(), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-02T21:00:00", "THE APPLICATORS"),
        ("2026-07-03T20:00:00", "MOOSKA"),
        ("2026-07-04T20:00:00", "Who Asked for This?"),
        ("2026-07-06T16:00:00", "Happy Hour - No Fuss, just good times!"),
        ("2026-07-12T15:00:00", "MAURICE TANI"),  # same day, earlier matinee
        ("2026-07-12T20:00:00", "The Return of King of Kings Reggae"),
    ]


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # October 3 is ~93 days past the pinned today (> 90-day window).
    assert not any(s.start_local.date() == dt.date(2026, 10, 3) for s in parsed)


def test_excludes_postponed(parsed: list[ScrapedShow]) -> None:
    # The August 1 RIKI show carries status "SHOW POSTPONED" — dropped.
    assert not any("RIKI" in s.headliner_raw for s in parsed)


def test_window_size_is_respected() -> None:
    # A 7-day window from today catches only the July 2–6 shows.
    shows = ivy_room.parse_events(_events(), today=TODAY, window_days=7)
    assert [s.headliner_raw for s in shows] == [
        "THE APPLICATORS",
        "MOOSKA",
        "Who Asked for This?",
        "Happy Hour - No Fuss, just good times!",
    ]


def test_bill_split_into_headliner_and_support(parsed: list[ScrapedShow]) -> None:
    applicators = next(s for s in parsed if s.headliner_raw == "THE APPLICATORS")
    assert applicators.support_raw == ["SYMPATHY FLOWERS", "DAMAGE PARTY"]


def test_tbd_support_placeholder_dropped(parsed: list[ScrapedShow]) -> None:
    # "Who Asked for This? + Used to Be Valentines + TBD" — TBD isn't an act.
    who = next(s for s in parsed if s.headliner_raw == "Who Asked for This?")
    assert who.support_raw == ["Used to Be Valentines"]


def test_doors_and_start_times(parsed: list[ScrapedShow]) -> None:
    applicators = next(s for s in parsed if s.headliner_raw == "THE APPLICATORS")
    assert applicators.start_local == dt.datetime(2026, 7, 2, 21, 0)
    assert applicators.doors_local == dt.datetime(2026, 7, 2, 20, 0)


def test_price_range_formatting(parsed: list[ScrapedShow]) -> None:
    mooska = next(s for s in parsed if s.headliner_raw == "MOOSKA")
    assert mooska.price_text == "$15–$18"
    # priceMin 0.0 means "no floor set", not a free tier — only the max shows.
    applicators = next(s for s in parsed if s.headliner_raw == "THE APPLICATORS")
    assert applicators.price_text == "$15"


def test_ticket_url_and_source_url_when_present(parsed: list[ScrapedShow]) -> None:
    applicators = next(s for s in parsed if s.headliner_raw == "THE APPLICATORS")
    expected = (
        "https://t.venuepilot.com/e/"
        "the-applicators-sympathy-flowers-damage-party-2026-07-02-ivy-room-albany-565e77"
    )
    assert applicators.ticket_url == expected
    assert applicators.source_url == expected  # per-event page doubles as provenance


def test_unticketed_event_defaults(parsed: list[ScrapedShow]) -> None:
    happy = next(s for s in parsed if s.headliner_raw.startswith("Happy Hour"))
    assert happy.venue_slug == "ivy_room"
    assert happy.support_raw == []
    assert happy.ticket_url is None
    assert happy.price_text is None
    assert happy.source_url == ivy_room.CALENDAR_URL
