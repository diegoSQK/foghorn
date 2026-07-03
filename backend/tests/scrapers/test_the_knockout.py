"""Tests for The Knockout Squarespace-calendar parser.

Fixture-driven and deterministic: ``parse_events`` takes an injected ``today``
so the 90-day window doesn't depend on the clock. The fixture
(``fixtures/the_knockout_2026_07.json``) is a trimmed snapshot of the live
``/api/open/GetItemsByMonth`` payload exercising the edge cases — "+"-split
multi-act bills (one with an ``&amp;`` entity inside an act name), trailing
"(9PM - CLOSE)" set-time notes, two shows on one local day, non-music entries
(karaoke, trivia), a show already in the past, and a far-future event excluded
by the window.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import the_knockout

FIXTURE = Path(__file__).parent.parent / "fixtures" / "the_knockout_2026_07.json"
TODAY = dt.date(2026, 7, 2)


def _items() -> list[dict[str, object]]:
    items: list[dict[str, object]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return items


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return the_knockout.parse_events(_items(), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-02T20:00:00", "THE BFFDOTFM SUPER SCMACKDOWN : MARINERO"),
        ("2026-07-03T20:00:00", "COOTIE CATCHER"),
        ("2026-07-04T22:00:00", "SWEATER FUNK RARE BOOGIE DANCE PARTY!"),
        (
            "2026-07-11T17:00:00",
            "MATINEE SHOW : MUSIC FOR STUFFED ANIMALS FEATURING FLORA ELMCOLONE",
        ),
        ("2026-07-11T22:00:00", "CHULITA VINYL CLUB SATURDAY NIGHT DARTY!"),  # same day
        ("2026-07-24T21:00:00", "THE CREEPY CRAWLIES"),
    ]


def test_plus_bill_split_into_support(parsed: list[ScrapedShow]) -> None:
    cootie = next(s for s in parsed if s.headliner_raw == "COOTIE CATCHER")
    assert cootie.support_raw == ["DUSTY SLIMS", "STARFISH PRIME", "UNIVERSAL BEAT"]


def test_ampersand_entity_unescaped_inside_act(parsed: list[ScrapedShow]) -> None:
    # "MUK MUK &amp; THE KEWKS" is one act — "&" is unescaped, not a separator.
    creepy = next(s for s in parsed if s.headliner_raw == "THE CREEPY CRAWLIES")
    assert creepy.support_raw == ["STERILE EYES", "MUK MUK & THE KEWKS", "SPIDER GARAGE"]


def test_single_billing_has_no_support(parsed: list[ScrapedShow]) -> None:
    sweater = next(s for s in parsed if s.headliner_raw.startswith("SWEATER FUNK"))
    assert sweater.support_raw == []


def test_time_note_stripped_from_title(parsed: list[ScrapedShow]) -> None:
    # Titles end with "(10PM - CLOSE)"-style notes; none should survive.
    assert not any("CLOSE)" in s.headliner_raw for s in parsed)
    assert not any("PM" in s.headliner_raw for s in parsed)


def test_non_music_events_dropped(parsed: list[ScrapedShow]) -> None:
    names = [s.headliner_raw for s in parsed]
    assert not any("KARAOKE" in name for name in names)
    assert not any("TRIVIA" in name for name in names)


def test_excludes_past_event(parsed: list[ScrapedShow]) -> None:
    # SQUID PISSER played July 1 local — the day before the pinned today.
    assert not any(s.headliner_raw.startswith("SQUID PISSER") for s in parsed)


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # October 20 (local) is ~110 days past the pinned today (> 90-day window).
    assert not any(s.headliner_raw == "OUT OF WINDOW OCTET" for s in parsed)


def test_window_size_is_respected() -> None:
    # A 2-day window from today catches only the July 2–4 (local) shows.
    shows = the_knockout.parse_events(_items(), today=TODAY, window_days=2)
    assert [s.headliner_raw for s in shows] == [
        "THE BFFDOTFM SUPER SCMACKDOWN : MARINERO",
        "COOTIE CATCHER",
        "SWEATER FUNK RARE BOOGIE DANCE PARTY!",
    ]


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    cootie = next(s for s in parsed if s.headliner_raw == "COOTIE CATCHER")
    assert cootie.source_url == (
        "https://theknockoutsf.com/events-2-1/ox7cyklhgmm57bjaoxhnln8xe01eiv"
    )


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "the_knockout"
    assert show.doors_local is None
    assert show.ticket_url is None  # month JSON carries no ticket links
    assert show.price_text is None


def test_months_helper_covers_window() -> None:
    months = the_knockout._months(dt.date(2026, 11, 20), dt.date(2027, 2, 18))
    assert months == ["11-2026", "12-2026", "01-2027", "02-2027"]
