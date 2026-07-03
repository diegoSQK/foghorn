"""Tests for the Rickshaw Stop SeeTickets-card parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture
(``fixtures/rickshaw_stop_2026_07.html``) is a trimmed snapshot of the live
``/calendar/`` list cards exercising the edge cases — a co-billed multi-act
headliners line, a real supporting-talent list, a "support tba" placeholder, a
next-calendar-year card (dates carry no year), a bare "SOLD OUT" placeholder
card with no times, and a Stand-Up (non-music) card. It also carries the AJAX
nonce script and pagination strip the pager helpers read.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import rickshaw_stop

FIXTURE = Path(__file__).parent.parent / "fixtures" / "rickshaw_stop_2026_07.html"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return rickshaw_stop.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-02T20:00:00", "Silverset"),
        ("2026-07-16T20:45:00", "Bed Bug Guru"),
        ("2026-07-17T21:00:00", "AKRIILA"),
    ]


def test_cobilled_headliners_split_top_billing_first(parsed: list[ScrapedShow]) -> None:
    # p.headliners "Silverset, Paper Straw, Lizzie Waters": first is headliner.
    silverset = next(s for s in parsed if s.headliner_raw == "Silverset")
    assert silverset.support_raw == ["Paper Straw", "Lizzie Waters"]


def test_supporting_talent_parsed(parsed: list[ScrapedShow]) -> None:
    # "Supporting Talent: Welcome Strawberry, Blous3" — label stripped, split.
    bed_bug = next(s for s in parsed if s.headliner_raw == "Bed Bug Guru")
    assert bed_bug.support_raw == ["Welcome Strawberry", "Blous3"]


def test_support_tba_is_empty(parsed: list[ScrapedShow]) -> None:
    akriila = next(s for s in parsed if s.headliner_raw == "AKRIILA")
    assert akriila.support_raw == []


def test_doors_and_showtime(parsed: list[ScrapedShow]) -> None:
    # "Doors at 7:30PM / Show at 8:00PM" — show is start, doors kept separately.
    silverset = next(s for s in parsed if s.headliner_raw == "Silverset")
    assert silverset.start_local == dt.datetime(2026, 7, 2, 20, 0)
    assert silverset.doors_local == dt.datetime(2026, 7, 2, 19, 30)


def test_price_and_ticket_and_source(parsed: list[ScrapedShow]) -> None:
    silverset = next(s for s in parsed if s.headliner_raw == "Silverset")
    expected_url = (
        "https://wl.seetickets.us/event/silverset-paper-straw-lizzie-waters/"
        "692943?afflky=RickshawStop"
    )
    assert silverset.price_text == "$15.00-$20.00"
    # The per-event SeeTickets page is both provenance and the ticket link.
    assert silverset.ticket_url == expected_url
    assert silverset.source_url == expected_url


def test_excludes_out_of_window_with_year_rollover(parsed: list[ScrapedShow]) -> None:
    # "Fri Feb 19" resolves forward to 2027-02-19 (~232 days out): excluded at
    # the default window and still excluded at 200 days.
    assert not any(s.headliner_raw == "Small Brown Bike" for s in parsed)
    wide = rickshaw_stop.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=200
    )
    assert not any(s.headliner_raw == "Small Brown Bike" for s in wide)


def test_year_rollover_resolves_forward() -> None:
    # At 400 days the Feb card is in-window and lands in the *next* year.
    wide = rickshaw_stop.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=400
    )
    small_brown_bike = next(s for s in wide if s.headliner_raw == "Small Brown Bike")
    assert small_brown_bike.start_local == dt.datetime(2027, 2, 19, 21, 0)
    assert small_brown_bike.support_raw == ["Suzzallo"]


def test_non_music_genre_dropped() -> None:
    # KYLE GORDON is tagged Stand-Up; Oct 25 is inside a 200-day window, so its
    # absence is the genre filter, not the date filter.
    wide = rickshaw_stop.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=200
    )
    assert not any(s.headliner_raw == "KYLE GORDON" for s in wide)


def test_placeholder_card_without_times_skipped() -> None:
    # The bare "SOLD OUT - Thank You!" tile has no doors/show times: skipped
    # even when its date (Apr 2027) falls inside a 400-day window.
    wide = rickshaw_stop.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=400
    )
    assert not any("SOLD OUT" in s.headliner_raw for s in wide)


def test_pager_helpers_read_nonce_and_total_pages() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    assert rickshaw_stop._extract_nonce(html) == "20c8a2f544"
    assert rickshaw_stop._extract_total_pages(html) == 3


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "rickshaw_stop"
    assert show.doors_local is not None  # doors are given on real cards
    assert show.price_text is not None
