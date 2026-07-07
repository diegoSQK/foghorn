"""Tests for the Mystic Theatre SeeTickets-card parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture
(``fixtures/mystic_theatre_2026_07.html``) is a trimmed snapshot of the live
``/calendar/`` list cards exercising the edge cases — a "with …"-labeled
supporting-talent line, a "Featuring: …"-labeled one, a co-billed headliners
line, a card with no support at all, a Stand-Up (non-music) card, a multi-night
"Heart of Gold Band" card with no doors/show time spans, and an out-of-window
November card. It also carries the AJAX nonce script and pagination strip the
pager helpers read.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import mystic_theatre

FIXTURE = Path(__file__).parent.parent / "fixtures" / "mystic_theatre_2026_07.html"
TODAY = dt.date(2026, 7, 7)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return mystic_theatre.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-10T20:00:00", "Burning Down The House"),
        ("2026-07-11T21:00:00", "Fantasías: Latin Rave"),
        ("2026-07-17T20:00:00", "”An evening with: The Stinkfoot Orchestra\""),
        ("2026-08-26T20:00:00", "Willie Watson"),
    ]


def test_with_prefixed_support_parsed(parsed: list[ScrapedShow]) -> None:
    # "with Jason Beard's Bring Joy" — the "with" label is stripped.
    bdth = next(s for s in parsed if s.headliner_raw == "Burning Down The House")
    assert bdth.support_raw == ["Jason Beard's Bring Joy"]


def test_featuring_prefixed_support_parsed(parsed: list[ScrapedShow]) -> None:
    # "Featuring: Napoleon Murphy Brock" — the "Featuring:" label is stripped.
    stinkfoot = next(s for s in parsed if "Stinkfoot" in s.headliner_raw)
    assert stinkfoot.support_raw == ["Napoleon Murphy Brock"]


def test_cobilled_headliners_split_top_billing_first(parsed: list[ScrapedShow]) -> None:
    # p.headliners "Willie Watson, Erin Rae": first is headliner, rest support.
    willie = next(s for s in parsed if s.headliner_raw == "Willie Watson")
    assert willie.support_raw == ["Erin Rae"]


def test_no_support_is_empty(parsed: list[ScrapedShow]) -> None:
    fantasias = next(s for s in parsed if s.headliner_raw == "Fantasías: Latin Rave")
    assert fantasias.support_raw == []


def test_doors_and_showtime(parsed: list[ScrapedShow]) -> None:
    # "Doors: 7:00PM / Show: 8:00PM" — show is start, doors kept separately.
    bdth = next(s for s in parsed if s.headliner_raw == "Burning Down The House")
    assert bdth.start_local == dt.datetime(2026, 7, 10, 20, 0)
    assert bdth.doors_local == dt.datetime(2026, 7, 10, 19, 0)


def test_price_and_ticket_and_source(parsed: list[ScrapedShow]) -> None:
    bdth = next(s for s in parsed if s.headliner_raw == "Burning Down The House")
    expected_url = (
        "https://wl.seetickets.us/event/burning-down-the-house/"
        "691671?afflky=MysticTheatre"
    )
    assert bdth.price_text == "$20.00-$30.00"
    # The per-event SeeTickets page is both provenance and the ticket link.
    assert bdth.ticket_url == expected_url
    assert bdth.source_url == expected_url


def test_per_event_genre_passed_through(parsed: list[ScrapedShow]) -> None:
    bdth = next(s for s in parsed if s.headliner_raw == "Burning Down The House")
    assert bdth.genre == "tribute act"
    willie = next(s for s in parsed if s.headliner_raw == "Willie Watson")
    assert willie.genre == "bluegrass"


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # "Fri Nov 20" (Y&T) is ~136 days out: excluded at the default 90-day
    # window, included when the window is widened.
    assert not any(s.headliner_raw == "Y&T" for s in parsed)
    wide = mystic_theatre.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=200
    )
    yt = next(s for s in wide if s.headliner_raw == "Y&T")
    assert yt.start_local == dt.datetime(2026, 11, 20, 20, 0)
    assert yt.support_raw == ["Gretchen Menn Trio"]


def test_non_music_genre_dropped(parsed: list[ScrapedShow]) -> None:
    # Tom Rhodes is tagged Stand-Up; Jul 16 is inside the window, so its
    # absence is the genre filter, not the date filter.
    assert not any(s.headliner_raw == "Tom Rhodes" for s in parsed)


def test_multi_night_card_without_times_skipped(parsed: list[ScrapedShow]) -> None:
    # The "Heart of Gold Band" multi-night card has no see-doortime/see-showtime
    # spans (the times live in the title text): skipped even though its date
    # (Aug 22) is inside the window.
    assert not any("Heart of Gold" in s.headliner_raw for s in parsed)


def test_pager_helpers_read_nonce_and_total_pages() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    assert mystic_theatre._extract_nonce(html) == "5afcff19d1"
    assert mystic_theatre._extract_total_pages(html) == 2


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "mystic_theatre"
    assert show.event_type is None  # ingest infers; the source doesn't say
    assert show.doors_local is not None  # doors are given on real cards
    assert show.price_text is not None
