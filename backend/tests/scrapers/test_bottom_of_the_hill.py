"""Tests for the Bottom of the Hill HTML parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture
(``fixtures/bottom_of_the_hill_2026_07.html``) is a trimmed snapshot of the
live hand-maintained ``calendar.html`` exercising the edge cases — a show with
no advance-ticket link, two shows on one day (the second anchored
``20260725A``), a matinee with different doors/music times, a multi-act bill
split into headliner + support, non-ASCII band names ("Dümsurf"), the
fragmented time/cover spans the site is notorious for, and a far-future event
excluded by the window.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import bottom_of_the_hill

FIXTURE = Path(__file__).parent.parent / "fixtures" / "bottom_of_the_hill_2026_07.html"
TODAY = dt.date(2026, 7, 1)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return bottom_of_the_hill.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-01T20:30:00", "Black Furies"),
        ("2026-07-02T20:30:00", "Atomic Tide"),
        ("2026-07-05T16:00:00", "Destroyer"),  # matinee — 4pm music
        ("2026-07-25T13:00:00", "MCM and the Monster"),  # same day, early show
        ("2026-07-25T20:30:00", "The Body"),  # same day, late show
    ]


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # November 21 is ~143 days past the pinned today (> 90-day window).
    assert not any(s.headliner_raw == "M.D.C." for s in parsed)


def test_window_size_is_respected() -> None:
    # A 7-day window from today catches only the first three shows.
    shows = bottom_of_the_hill.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=7
    )
    assert [s.headliner_raw for s in shows] == ["Black Furies", "Atomic Tide", "Destroyer"]


def test_bill_splits_headliner_and_support(parsed: list[ScrapedShow]) -> None:
    # The site lists top billing first; the rest of the bill is support.
    black_furies = next(s for s in parsed if s.headliner_raw == "Black Furies")
    assert black_furies.support_raw == ["Party Force", "Class of '77"]
    destroyer = next(s for s in parsed if s.headliner_raw == "Destroyer")
    assert destroyer.support_raw == ["Modern Monsters", "Dümsurf"]  # non-ASCII intact


def test_doors_and_music_times_split(parsed: list[ScrapedShow]) -> None:
    # "3:00PM doors -- music at 4:00PM": doors is the first time, start the second.
    destroyer = next(s for s in parsed if s.headliner_raw == "Destroyer")
    assert destroyer.start_local == dt.datetime(2026, 7, 5, 16, 0)
    assert destroyer.doors_local == dt.datetime(2026, 7, 5, 15, 0)


def test_ticket_url_captured_when_present(parsed: list[ScrapedShow]) -> None:
    atomic = next(s for s in parsed if s.headliner_raw == "Atomic Tide")
    assert atomic.ticket_url == "http://www.bottomofthehill.com/stubmatic/event20260702.html"


def test_ticket_url_none_when_absent(parsed: list[ScrapedShow]) -> None:
    # The July 1 row has no stubmatic advance-tickets link.
    black_furies = next(s for s in parsed if s.headliner_raw == "Black Furies")
    assert black_furies.ticket_url is None


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    the_body = next(s for s in parsed if s.headliner_raw == "The Body")
    assert the_body.source_url == "http://www.bottomofthehill.com/20260725.html"
    # The same-day second show keeps its distinct suffixed detail page.
    mcm = next(s for s in parsed if s.headliner_raw == "MCM and the Monster")
    assert mcm.source_url == "http://www.bottomofthehill.com/20260725A.html"


def test_price_text_reassembled_from_fragments(parsed: list[ScrapedShow]) -> None:
    # "$", "13", "in advance / $15 at the door" live in separate spans.
    black_furies = next(s for s in parsed if s.headliner_raw == "Black Furies")
    assert black_furies.price_text == "$13 in advance / $15 at the door"
    the_body = next(s for s in parsed if s.headliner_raw == "The Body")
    assert the_body.price_text == "$20"


def test_venue_slug(parsed: list[ScrapedShow]) -> None:
    assert all(s.venue_slug == "bottom_of_the_hill" for s in parsed)
