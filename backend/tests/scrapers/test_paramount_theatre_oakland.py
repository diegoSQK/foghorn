"""Tests for the Paramount Theatre (Oakland) carbonhouse listing parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today``.
The main fixture is a trimmed snapshot of the live ``/events/`` blocks — a
film-series block ("Paramount Movie Classics" presenter, the non-music
filter's live case), two dates of one tour, and a ticketless block — plus one
comedy block synthesized from the same real markup (no live example existed
at snapshot time). The second fixture is the decoded ``events_ajax/6``
fragment, proving the lazy-load markup parses identically.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import paramount_theatre_oakland

FIXTURES = Path(__file__).parent.parent / "fixtures"
FIXTURE = FIXTURES / "paramount_theatre_oakland_2026_07.html"
AJAX_FIXTURE = FIXTURES / "paramount_theatre_oakland_2026_07_ajax.html"
TODAY = dt.date(2026, 7, 19)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return paramount_theatre_oakland.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-08-06T19:30:00", "Jill Scott – To Whom This May Concern Tour"),
        ("2026-08-07T19:30:00", "Jill Scott – To Whom This May Concern Tour"),
        ("2026-08-29T20:00:00", "Brad Mehldau: Ride Into The Sun"),
        ("2026-09-17T19:30:00", "The Bald and the Beautiful LIVE: Very Bald, Very Beautiful"),
        ("2026-09-18T19:30:00", "Mojo Brookzz: Outta Pocket Tour"),
    ]


def test_film_and_comedy_blocks_dropped(parsed: list[ScrapedShow]) -> None:
    # Both blocks are in-window (Jul 24 / Sep 25), so their absence is the
    # non-music keyword filter — "Movie" in the film series' presenter line,
    # "Comedy" in the synthesized showcase title — not the date filter.
    titles = {s.headliner_raw for s in parsed}
    assert "The Maltese Falcon" not in titles
    assert "Oakland Comedy Showcase" not in titles


def test_ajax_fragment_parses_like_the_page() -> None:
    # events_ajax fragments carry the same eventItem markup as the page.
    shows = paramount_theatre_oakland.parse_html(
        AJAX_FIXTURE.read_text(encoding="utf-8"), today=TODAY
    )
    assert [(s.start_local.isoformat(), s.headliner_raw) for s in shows] == [
        ("2026-09-22T20:00:00", "Lily Allen Performs West End Girl"),
        ("2026-10-02T20:00:00", "Snarky Puppy"),
    ]


def test_ticket_source_and_optional_fields(parsed: list[ScrapedShow]) -> None:
    first_jill = parsed[0]
    assert first_jill.ticket_url == "https://www.ticketmaster.com/event/1C006465BF4017BD"
    assert first_jill.source_url == (
        "https://www.paramountoakland.org/events/detail/jill-scott-to-whom-it-may-concern-1"
    )
    # The Bald and the Beautiful block has no tickets link (not yet on sale).
    ticketless = next(s for s in parsed if "Bald" in s.headliner_raw)
    assert ticketless.ticket_url is None
    show = parsed[0]
    assert show.venue_slug == "paramount_theatre_oakland"
    assert show.support_raw == []  # the listing never carries support billing
    assert show.doors_local is None  # ... nor doors times
    assert show.price_text is None  # ... nor prices
    assert show.genre is None  # ... nor genres


def test_window_excludes_earlier_and_later() -> None:
    # From Sep 1 the two August dates fall behind `today`; everything left is
    # inside the forward window.
    shows = paramount_theatre_oakland.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=dt.date(2026, 9, 1)
    )
    assert [s.start_local.date().isoformat() for s in shows] == ["2026-09-17", "2026-09-18"]
