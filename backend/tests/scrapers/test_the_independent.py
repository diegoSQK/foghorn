"""Tests for The Independent HTML parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today``
so the 90-day window (and the year inference for the template's year-less
"7.2" dates) doesn't depend on the clock. The fixture
(``fixtures/the_independent_2026_07.html``) is a trimmed snapshot of the live
homepage list exercising the edge cases — a multi-act bill, a non-music
"World Cup Watch Party" row, an event with no ticket link, an out-of-window
December show, and a "3.17" date that must roll over to the next year.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import the_independent

FIXTURE = Path(__file__).parent.parent / "fixtures" / "the_independent_2026_07.html"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return the_independent.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-02T20:00:00", "Kelly McFarling"),
        ("2026-07-08T20:00:00", "High Fade"),
        ("2026-07-11T21:00:00", "The Emo Night Tour"),  # 9pm show, ambiguous kept
    ]


def test_non_music_event_dropped(parsed: list[ScrapedShow]) -> None:
    # The "7.5" World Cup Watch Party row is clearly not a concert.
    assert not any("Watch Party" in s.headliner_raw for s in parsed)


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # December 13 is ~164 days past the pinned today (> 90-day window).
    assert not any(s.headliner_raw.startswith("Swervedriver") for s in parsed)


def test_window_size_is_respected() -> None:
    # A 3-day window from today catches only the July 2 show.
    shows = the_independent.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=3
    )
    assert [s.headliner_raw for s in shows] == ["Kelly McFarling"]


def test_yearless_date_rolls_over_to_next_year() -> None:
    # The list shows "3.17" with no year; from a July 2026 today that must
    # resolve to March 2027 (a 365-day window makes it visible).
    shows = the_independent.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=365
    )
    dogma = next(s for s in shows if s.headliner_raw == "POSTPONED: Dogma")
    assert dogma.start_local == dt.datetime(2027, 3, 17, 20, 0)


def test_support_acts_split_from_headliner(parsed: list[ScrapedShow]) -> None:
    kelly = next(s for s in parsed if s.headliner_raw == "Kelly McFarling")
    assert kelly.support_raw == ["Rose Paradise", "Uwade"]
    high_fade = next(s for s in parsed if s.headliner_raw == "High Fade")
    assert high_fade.support_raw == ["Turning Jane"]


def test_ticket_url_captured_when_present(parsed: list[ScrapedShow]) -> None:
    kelly = next(s for s in parsed if s.headliner_raw == "Kelly McFarling")
    assert kelly.ticket_url == (
        "https://www.ticketweb.com/event/kelly-mcfarling-the-independent-tickets"
        "/14909493?pl=independentsf&REFID=clientsitewp"
    )


def test_ticket_url_none_when_absent(parsed: list[ScrapedShow]) -> None:
    emo = next(s for s in parsed if s.headliner_raw == "The Emo Night Tour")
    assert emo.ticket_url is None


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    kelly = next(s for s in parsed if s.headliner_raw == "Kelly McFarling")
    assert kelly.source_url == "https://www.theindependentsf.com/tm-event/kelly-mcfarling/"


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    # This deployment has no popup dialogs, so doors and price never appear.
    for show in parsed:
        assert show.venue_slug == "the_independent"
        assert show.doors_local is None
        assert show.price_text is None
    emo = next(s for s in parsed if s.headliner_raw == "The Emo Night Tour")
    assert emo.support_raw == []
