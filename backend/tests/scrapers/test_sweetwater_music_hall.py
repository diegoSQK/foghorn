"""Tests for the Sweetwater Music Hall Rockhouse-Partners-listing parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture
(``fixtures/sweetwater_music_hall_2026_07.html``) is a trimmed snapshot of the
live ``/events/?view=list`` wrappers exercising the edge cases — a standard
doors+show evening show with an etix link, a free matinee with no ticket link,
two shows on the same date (matinee + evening, to pin the sort), an open mic
with a show time but no doors line, an 11:30 am doors time, a show landing
exactly on the window's last day, and a next-January show outside the window.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import sweetwater_music_hall

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sweetwater_music_hall_2026_07.html"
TODAY = dt.date(2026, 7, 7)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return sweetwater_music_hall.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-08T20:00:00", "Jesse Ray Smith with Alex Jordan & Graham Norwood Duo"),
        (
            "2026-07-12T12:00:00",
            "Free show! Che Prasad and the Shark Alley Hobos “Shiva Me Timbers”",
        ),
        ("2026-07-12T20:00:00", "Aki Kumar with The Sampaguitas"),
        ("2026-07-14T19:00:00", "Open Mic Night with Joe Endoso"),
        ("2026-07-17T20:00:00", "Margo Price – Wild At Heart Tour with Jeremy Ivey"),
        ("2026-07-26T12:00:00", "Marin Bluegrass Sessions July"),
        ("2026-10-05T20:00:00", "Mike Dawes–SOLD OUT"),
    ]


def test_doors_and_showtime(parsed: list[ScrapedShow]) -> None:
    # "Doors: 7 pm Show: 8 pm" — show is start, doors kept separately.
    jesse = parsed[0]
    assert jesse.start_local == dt.datetime(2026, 7, 8, 20, 0)
    assert jesse.doors_local == dt.datetime(2026, 7, 8, 19, 0)


def test_show_only_time_has_no_doors(parsed: list[ScrapedShow]) -> None:
    # The open mic carries only "Show: 7 pm" — no doors line at all.
    open_mic = next(s for s in parsed if s.headliner_raw.startswith("Open Mic"))
    assert open_mic.start_local == dt.datetime(2026, 7, 14, 19, 0)
    assert open_mic.doors_local is None


def test_half_hour_am_doors(parsed: list[ScrapedShow]) -> None:
    # "Doors: 11:30 am Show: 12 pm" — morning times with minutes parse too.
    bluegrass = next(s for s in parsed if "Bluegrass" in s.headliner_raw)
    assert bluegrass.start_local == dt.datetime(2026, 7, 26, 12, 0)
    assert bluegrass.doors_local == dt.datetime(2026, 7, 26, 11, 30)


def test_ticket_url_present_and_absent(parsed: list[ScrapedShow]) -> None:
    jesse = parsed[0]
    assert jesse.ticket_url is not None
    assert jesse.ticket_url.startswith("https://www.etix.com/ticket/p/59764137/")
    # Free shows and open mics have no etix link.
    free_show = next(s for s in parsed if s.headliner_raw.startswith("Free show!"))
    assert free_show.ticket_url is None


def test_source_url_is_event_page(parsed: list[ScrapedShow]) -> None:
    jesse = parsed[0]
    assert jesse.source_url == (
        "https://sweetwatermusichall.org/event/"
        "jesse-ray-smith-with-alex-jordan-graham-norwood-duo/"
        "sweetwater-music-hall/mill-valley-california/"
    )


def test_same_day_matinee_sorts_before_evening(parsed: list[ScrapedShow]) -> None:
    july_12 = [s for s in parsed if s.start_local.date() == dt.date(2026, 7, 12)]
    assert [s.start_local.hour for s in july_12] == [12, 20]


def test_window_boundary_day_included(parsed: list[ScrapedShow]) -> None:
    # Mike Dawes lands on 2026-10-05 — exactly today + 90 days, inclusive.
    assert any(s.headliner_raw.startswith("Mike Dawes") for s in parsed)


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # Don Carlos (Fri, Jan 22, 2027) is outside the 90-day window; the listing
    # prints full years, so no rollover inference is involved.
    assert not any(s.headliner_raw == "Don Carlos" for s in parsed)
    wide = sweetwater_music_hall.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=250
    )
    don = next(s for s in wide if s.headliner_raw == "Don Carlos")
    assert don.start_local == dt.datetime(2027, 1, 22, 20, 0)


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "sweetwater_music_hall"
    assert show.support_raw == []  # the listing doesn't pre-split the bill
    assert show.price_text is None  # the listing doesn't publish prices
    assert show.genre is None  # nor per-event genres
    assert show.event_type is None  # ingest infers; the source doesn't say
