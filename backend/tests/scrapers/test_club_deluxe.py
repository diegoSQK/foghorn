"""Tests for the Club Deluxe HTML parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture
(``fixtures/club_deluxe_2026_07.html``) is a trimmed snapshot of the live
``/calendar/`` (Simple Calendar plugin) page exercising the edge cases — two
shows on one day with the cover charge in the title, a ``CLOSED`` day marker,
a title with no price, an all-day "OSL" banner with a ``:59``-second
``data-start``, a 9pm show re-listed under the next day with the same
``data-start`` (dedup), and a far-future event excluded by the window.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import club_deluxe

FIXTURE = Path(__file__).parent.parent / "fixtures" / "club_deluxe_2026_07.html"
TODAY = dt.date(2026, 7, 3)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return club_deluxe.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-03T18:00:00", "JACKNIFE!"),
        ("2026-07-03T21:30:00", "Tony Peebles Quartet"),  # same day, later set
        ("2026-07-05T15:00:00", "Scott Larson Quartet"),
        ("2026-07-05T18:00:00", "Night School"),
        ("2026-07-06T19:00:00", "DeLuxe Jazz Collective"),  # recurring event
        ("2026-08-01T18:00:00", "Hammond Cheese Combo"),  # no price in title
        ("2026-08-07T21:30:00", "Miles Turk"),
        ("2026-08-15T18:00:00", "Banda Sin Nombre"),
        ("2026-08-15T21:00:00", "Kamrin Ortiz & His Knock Outs"),  # deduped
    ]


def test_price_split_out_of_title(parsed: list[ScrapedShow]) -> None:
    tony = next(s for s in parsed if s.headliner_raw == "Tony Peebles Quartet")
    assert tony.price_text == "$15"


def test_no_price_title_has_none(parsed: list[ScrapedShow]) -> None:
    hammond = next(s for s in parsed if s.headliner_raw == "Hammond Cheese Combo")
    assert hammond.price_text is None


def test_closed_marker_dropped(parsed: list[ScrapedShow]) -> None:
    # July 4 carries a single "CLOSED" entry; it must not become a show.
    assert not any(s.start_local.date() == dt.date(2026, 7, 4) for s in parsed)
    assert not any(s.headliner_raw.lower() == "closed" for s in parsed)


def test_all_day_banner_dropped(parsed: list[ScrapedShow]) -> None:
    # "OSL" (festival note) has a :59-second all-day data-start; not a show.
    assert not any(s.headliner_raw == "OSL" for s in parsed)


def test_next_day_relisting_deduped(parsed: list[ScrapedShow]) -> None:
    # The Aug 15 9pm show is re-listed under Aug 16 with the same data-start.
    kamrin = [s for s in parsed if s.headliner_raw.startswith("Kamrin Ortiz")]
    assert len(kamrin) == 1
    assert kamrin[0].start_local == dt.datetime(2026, 8, 15, 21, 0)


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # October 15 is ~104 days past the pinned today (> 90-day window).
    assert not any(s.headliner_raw == "Out-Of-Window Octet" for s in parsed)


def test_window_size_is_respected() -> None:
    # A 7-day window from today stops before the Aug shows.
    shows = club_deluxe.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=7
    )
    assert [s.headliner_raw for s in shows] == [
        "JACKNIFE!",
        "Tony Peebles Quartet",
        "Scott Larson Quartet",
        "Night School",
        "DeLuxe Jazz Collective",
    ]


def test_source_url_is_calendar_page(parsed: list[ScrapedShow]) -> None:
    # No per-event pages exist; provenance is the calendar page for every show.
    assert all(s.source_url == "https://thedeluxesf.com/calendar/" for s in parsed)


def test_no_ticket_urls(parsed: list[ScrapedShow]) -> None:
    # The venue has no ticketing platform; the cover is paid at the door.
    assert all(s.ticket_url is None for s in parsed)


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "club_deluxe"
    assert show.support_raw == []
    assert show.doors_local is None
    assert show.genre is None
