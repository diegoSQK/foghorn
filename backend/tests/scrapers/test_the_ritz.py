"""Tests for The Ritz gig-list parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today``
so the 90-day window doesn't depend on the clock. The fixture
(``fixtures/the_ritz_2026_07.html``) is a trimmed snapshot of the live
``POST / ajax=1`` gig-list fragment exercising the edge cases — a single-act
dance night whose blurb prose carries a *wrong year* (the ISO ``datetime``
attribute must win), a two-act bill with a curly apostrophe, a bill with a
sloppy "MOUTH+ WEEPING" separator, an entry with no ticket link, a past
entry, an out-of-window entry, and a non-music (karaoke) entry.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import the_ritz

FIXTURE = Path(__file__).parent.parent / "fixtures" / "the_ritz_2026_07.html"
TODAY = dt.date(2026, 7, 7)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return the_ritz.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-09T21:00:00", "ATOMIC: NEW/DARKWAVE, SYNTH-POP, POST-PUNK DANCE NIGHT"),
        ("2026-07-10T19:00:00", "YOUNG DUBLINERS"),
        ("2026-07-24T21:00:00", "FREE SYNTH NIGHT"),
        ("2026-09-25T18:00:00", "REVOCATION"),
    ]


def test_datetime_attr_wins_over_blurb_prose(parsed: list[ScrapedShow]) -> None:
    # The ATOMIC blurb says "THURSDAY JULY 9, 2025"; the row's ISO datetime
    # attribute (2026, with save-time seconds noise) is the source of truth.
    atomic = next(s for s in parsed if s.headliner_raw.startswith("ATOMIC"))
    assert atomic.start_local == dt.datetime(2026, 7, 9, 21, 0)


def test_bill_split_with_curly_apostrophe(parsed: list[ScrapedShow]) -> None:
    dubs = next(s for s in parsed if s.headliner_raw == "YOUNG DUBLINERS")
    assert dubs.support_raw == ["OCKHAM’S RAZOR"]


def test_bill_split_tolerates_sloppy_plus_spacing(parsed: list[ScrapedShow]) -> None:
    # "REVOCATION + DEFEATED SANITY + FUMING MOUTH+ WEEPING" — the last "+"
    # has no leading space.
    rev = next(s for s in parsed if s.headliner_raw == "REVOCATION")
    assert rev.support_raw == ["DEFEATED SANITY", "FUMING MOUTH", "WEEPING"]


def test_excludes_past_and_out_of_window(parsed: list[ScrapedShow]) -> None:
    names = [s.headliner_raw for s in parsed]
    assert "PAST PUNK NIGHT" not in names  # June 20 < pinned today
    assert "RIN" not in names  # Oct 13 is 98 days out (> 90-day window)


def test_window_size_is_respected() -> None:
    shows = the_ritz.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=7)
    assert [s.headliner_raw for s in shows] == [
        "ATOMIC: NEW/DARKWAVE, SYNTH-POP, POST-PUNK DANCE NIGHT",
        "YOUNG DUBLINERS",
    ]


def test_non_music_dropped(parsed: list[ScrapedShow]) -> None:
    assert not any("KARAOKE" in s.headliner_raw for s in parsed)


def test_ticket_url_captured_when_present(parsed: list[ScrapedShow]) -> None:
    dubs = next(s for s in parsed if s.headliner_raw == "YOUNG DUBLINERS")
    assert dubs.ticket_url == "https://www.ticketweb.com/event/young-dubliners-the-ritz-tickets/14796233"


def test_ticket_url_none_when_absent(parsed: list[ScrapedShow]) -> None:
    free = next(s for s in parsed if s.headliner_raw == "FREE SYNTH NIGHT")
    assert free.ticket_url is None


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "the_ritz"
    assert show.doors_local is None
    assert show.price_text is None
    assert show.source_url == "https://theritzsanjose.com/"
    assert show.event_type is None
    assert show.genre is None
