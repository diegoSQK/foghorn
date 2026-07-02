"""Tests for the Greek Theatre Berkeley HTML parser (APE listing template).

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture
(``fixtures/greek_theatre_berkeley_2026_07.html``) is a trimmed snapshot of the
live ``/event-listing/`` page exercising the edge cases — an ``&`` entity in
the headliner, a multi-support line split on ``<br>``, a prose support line
kept verbatim, a sold-out show whose "Sold Out!" button still links
Ticketmaster, a show with no support element, and a far-future event excluded
by the window.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import greek_theatre_berkeley

FIXTURE = Path(__file__).parent.parent / "fixtures" / "greek_theatre_berkeley_2026_07.html"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return greek_theatre_berkeley.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-17T19:30:00", "Bob Moses & Cannons"),  # decoded &amp; entity
        ("2026-07-19T18:00:00", "Young the Giant"),
        ("2026-08-01T17:00:00", "Dark Star Orchestra"),
        ("2026-08-15T19:00:00", "Thee Sacred Souls"),
        ("2026-08-25T20:00:00", "David Byrne"),
    ]


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # Vulfpeck (Oct 16) is ~106 days past the pinned today (> 90-day window).
    assert not any(s.headliner_raw == "Vulfpeck" for s in parsed)


def test_window_size_is_respected() -> None:
    # A 7-day window from today catches nothing (first show is July 17).
    shows = greek_theatre_berkeley.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=7
    )
    assert shows == []


def test_support_split_on_br(parsed: list[ScrapedShow]) -> None:
    ytg = next(s for s in parsed if s.headliner_raw == "Young the Giant")
    assert ytg.support_raw == ["Cold War Kids", "Beach Weather"]


def test_prose_support_line_kept_verbatim(parsed: list[ScrapedShow]) -> None:
    # A single support line naming multiple artists in prose is one act entry —
    # splitting it would mangle the billing.
    dso = next(s for s in parsed if s.headliner_raw == "Dark Star Orchestra")
    assert dso.support_raw == [
        "Peter Rowan with Sam Grisman Project playing music from Old & In The Way and more!"
    ]


def test_support_empty_when_absent(parsed: list[ScrapedShow]) -> None:
    byrne = next(s for s in parsed if s.headliner_raw == "David Byrne")
    assert byrne.support_raw == []


def test_doors_time_captured(parsed: list[ScrapedShow]) -> None:
    souls = next(s for s in parsed if s.headliner_raw == "Thee Sacred Souls")
    assert souls.doors_local == dt.datetime(2026, 8, 15, 17, 30)


def test_sold_out_button_still_yields_ticket_url(parsed: list[ScrapedShow]) -> None:
    # Sold-out shows swap "Buy Tickets" for a "Sold Out!" button that still
    # links the Ticketmaster event; we keep it as ticket_url.
    souls = next(s for s in parsed if s.headliner_raw == "Thee Sacred Souls")
    assert souls.ticket_url == (
        "https://www.ticketmaster.com/thee-sacred-souls-berkeley-california-08-15-2026"
        "/event/1C00644DBB592456?camefrom=CFC_ANOTHERPLANET_web&brand=anotherplanet"
    )


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    bob = next(s for s in parsed if s.headliner_raw == "Bob Moses & Cannons")
    assert bob.source_url == "https://thegreekberkeley.com/events/bob-moses-cannons-260717"


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "greek_theatre_berkeley"
    assert show.price_text is None  # the template shows no prices
