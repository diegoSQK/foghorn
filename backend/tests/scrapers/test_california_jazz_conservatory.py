"""Tests for the California Jazz Conservatory (Jazzschool) parsers.

Fixture-driven and deterministic: ``parse_listing`` takes an injected ``today``
so the 90-day window doesn't depend on the clock, and ``build_shows`` is pure —
it takes the listing stubs plus a URL → HTML mapping standing in for the
per-event fetches. The fixtures are trimmed snapshots of the live site: the
listing (``california_jazz_conservatory_2026_07.html``) has two concerts on one
day, an em-dash entity title, a non-music movie night, and a tile whose event
page isn't fetched; the three ``…_event_*.html`` pages cover a show with doors
in the prose, a free daytime event, and an evening event with no doors line.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import california_jazz_conservatory as cjc

FIXTURES = Path(__file__).parent.parent / "fixtures"
LISTING = FIXTURES / "california_jazz_conservatory_2026_07.html"
TODAY = dt.date(2026, 7, 2)

JUPITER_URL = "https://concerts.jazzschool.org/jazz-jams-at-jupiter-4/"
BROWNBAG_URL = "https://concerts.jazzschool.org/free-brown-bag-jazz-hangs-lewis-jordan-on-archie-shepp/"
RAFFI_URL = "https://concerts.jazzschool.org/raffi-garabedian-quartet/"
VINYL_URL = "https://concerts.jazzschool.org/new-fridays-in-june-after-hours-vinyl-lounge/"


def _listing_stubs() -> list[cjc.EventStub]:
    return cjc.parse_listing(LISTING.read_text(encoding="utf-8"), today=TODAY)


def _pages() -> dict[str, str]:
    return {
        JUPITER_URL: (
            FIXTURES / "california_jazz_conservatory_2026_07_event_jupiter.html"
        ).read_text(encoding="utf-8"),
        BROWNBAG_URL: (
            FIXTURES / "california_jazz_conservatory_2026_07_event_brownbag.html"
        ).read_text(encoding="utf-8"),
        RAFFI_URL: (
            FIXTURES / "california_jazz_conservatory_2026_07_event_raffi.html"
        ).read_text(encoding="utf-8"),
        # No page for VINYL_URL — build_shows must skip it, not crash.
    }


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return cjc.build_shows(_listing_stubs(), _pages())


def test_listing_keeps_concerts_and_drops_movie_night() -> None:
    stubs = _listing_stubs()
    assert [(s.date.isoformat(), s.title) for s in stubs] == [
        ("2026-07-08", "Jazz Jams at Jupiter"),
        ("2026-07-08", "FREE! Brown Bag Jazz Hangs: Lewis Jordan — on Archie Shepp"),
        ("2026-07-11", "Raffi Garabedian Quartet"),
        # "FREE! Jazz Movie Night – Miles Davis: Birth of the Cool (2019)" is
        # a film screening — dropped as clearly non-music.
        ("2026-07-31", "NEW! Fridays in July: After Hours Vinyl Lounge"),
    ]


def test_listing_window_size_is_respected() -> None:
    stubs = cjc.parse_listing(
        LISTING.read_text(encoding="utf-8"), today=TODAY, window_days=7
    )
    assert [s.date.isoformat() for s in stubs] == ["2026-07-08", "2026-07-08"]


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        # Two events on July 8, ordered by time (the tiles list them the other
        # way round); times come from the per-event pages.
        ("2026-07-08T12:30:00", "FREE! Brown Bag Jazz Hangs: Lewis Jordan — on Archie Shepp"),
        ("2026-07-08T19:00:00", "Jazz Jams at Jupiter"),
        ("2026-07-11T20:00:00", "Raffi Garabedian Quartet"),
        # The Vinyl Lounge stub has no fetched page — skipped, not invented.
    ]


def test_parse_event_page_extracts_date_time_and_doors() -> None:
    date, start, doors = cjc.parse_event_page(_pages()[RAFFI_URL])
    assert date == dt.date(2026, 7, 11)
    assert start == dt.time(20, 0)
    assert doors == dt.time(19, 0)  # "Doors 7pm" in the prose


def test_parse_event_page_without_time_returns_none() -> None:
    html = (
        '<div class="page-single-event__date">July 31, 2026</div>'
        '<div class="page-single-event"><div class="base-text"><p>TBA</p></div></div>'
    )
    date, start, doors = cjc.parse_event_page(html)
    assert date == dt.date(2026, 7, 31)
    assert start is None
    assert doors is None


def test_doors_captured_when_announced(parsed: list[ScrapedShow]) -> None:
    raffi = next(s for s in parsed if s.headliner_raw == "Raffi Garabedian Quartet")
    assert raffi.doors_local == dt.datetime(2026, 7, 11, 19, 0)


def test_doors_none_when_not_announced(parsed: list[ScrapedShow]) -> None:
    jupiter = next(s for s in parsed if s.headliner_raw == "Jazz Jams at Jupiter")
    assert jupiter.doors_local is None


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    raffi = next(s for s in parsed if s.headliner_raw == "Raffi Garabedian Quartet")
    assert raffi.source_url == RAFFI_URL


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "california_jazz_conservatory"
    assert show.support_raw == []
    # Ticketing is a client-side VBO widget on the event page (= source_url),
    # so there's no static ticket link or price to capture.
    assert show.ticket_url is None
    assert show.price_text is None
