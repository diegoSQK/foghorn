"""Tests for the Bimbo's 365 Club HTML parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today``
so the 90-day window (and the year inference for the template's year-less
month + day-of-month split dates) doesn't depend on the clock. The fixture
(``fixtures/bimbos_365_2026_07.html``) is a trimmed snapshot of the live
``/shows/`` list exercising the edge cases — a multi-act bill whose sold-out
button still links to TicketWeb, a bill with its Buy Tickets button trimmed,
a show near the window edge, and two out-of-window fall shows.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import bimbos_365

FIXTURE = Path(__file__).parent.parent / "fixtures" / "bimbos_365_2026_07.html"
TODAY = dt.date(2026, 7, 3)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return bimbos_365.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-08-06T20:00:00", "Balu Brigada"),
        (
            "2026-08-14T20:00:00",
            "Lady Camden's The Peach Pit Cabaret with Suzie Toot & Special Guests",
        ),
        ("2026-09-11T20:00:00", "Super Diamond"),
    ]


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # October 12 and December 16 are past the 90-day window ending Oct 1.
    assert not any(s.headliner_raw.startswith("MARO") for s in parsed)
    assert not any(s.headliner_raw == "Pokey LaFarge" for s in parsed)


def test_window_size_is_respected() -> None:
    # A 200-day window lets the October and December shows in too.
    shows = bimbos_365.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=200
    )
    assert [s.headliner_raw for s in shows][-2:] == [
        "MARO – (MOVED FROM THE CASTRO)",
        "Pokey LaFarge",
    ]
    pokey = next(s for s in shows if s.headliner_raw == "Pokey LaFarge")
    assert pokey.start_local == dt.datetime(2026, 12, 16, 20, 0)
    assert pokey.support_raw == ["Cicada Rhythm"]


def test_support_acts_split_from_headliner(parsed: list[ScrapedShow]) -> None:
    balu = next(s for s in parsed if s.headliner_raw == "Balu Brigada")
    assert balu.support_raw == ["Mild Universe"]
    diamond = next(s for s in parsed if s.headliner_raw == "Super Diamond")
    assert diamond.support_raw == ["Starman SF"]


def test_doors_time_captured_from_row(parsed: list[ScrapedShow]) -> None:
    balu = next(s for s in parsed if s.headliner_raw == "Balu Brigada")
    assert balu.doors_local == dt.datetime(2026, 8, 6, 19, 0)


def test_ticket_url_captured_even_when_sold_out(parsed: list[ScrapedShow]) -> None:
    balu = next(s for s in parsed if s.headliner_raw == "Balu Brigada")
    assert balu.ticket_url == (
        "https://www.ticketweb.com/event/balu-brigada-bimbos-365-club-tickets/14205614"
    )


def test_ticket_url_none_when_absent(parsed: list[ScrapedShow]) -> None:
    lady = next(s for s in parsed if s.headliner_raw.startswith("Lady Camden"))
    assert lady.ticket_url is None


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    balu = next(s for s in parsed if s.headliner_raw == "Balu Brigada")
    assert balu.source_url == "https://bimbos365club.com/tm-event/balu-brigada/"


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    # No popup dialogs and no row prices on this deployment.
    for show in parsed:
        assert show.venue_slug == "bimbos_365"
        assert show.price_text is None
        assert show.event_type is None
        assert show.genre is None
    lady = next(s for s in parsed if s.headliner_raw.startswith("Lady Camden"))
    assert lady.support_raw == []
