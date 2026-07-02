"""Tests for the Fox Theater Oakland HTML parser (APE listing template).

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture
(``fixtures/fox_theater_oakland_2026_07.html``) is a trimmed snapshot of the
live ``/listing/`` page exercising the edge cases — a show with a support act,
one without a ticket link, a multi-support line split on ``<br>``, a
"Featuring …" lead-in, a "SHOW CANCELLED" topline that must be dropped, an
italic support annotation that isn't an act, a comedy show that must be
dropped, and far-future events excluded by the window.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import fox_theater_oakland

FIXTURE = Path(__file__).parent.parent / "fixtures" / "fox_theater_oakland_2026_07.html"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return fox_theater_oakland.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-07T20:00:00", "Marcus King Band"),
        ("2026-07-16T20:00:00", "Widespread Panic"),
        ("2026-07-18T20:00:00", "Widespread Panic"),  # same run, no ticket link yet
        ("2026-08-05T19:00:00", "Poppy"),
        ("2026-08-10T20:00:00", "Little Feat"),
        ("2026-09-12T20:00:00", "Thievery Corporation"),
    ]


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # Boy Harsher (Oct 15) and Nothing But Thieves (Apr 2027) are past the
    # 90-day window from the pinned today.
    assert not any(s.headliner_raw == "Boy Harsher" for s in parsed)
    assert not any(s.headliner_raw == "Nothing But Thieves" for s in parsed)


def test_window_size_is_respected() -> None:
    # A 200-day window picks up Boy Harsher but still not April 2027.
    shows = fox_theater_oakland.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=200
    )
    names = [s.headliner_raw for s in shows]
    assert "Boy Harsher" in names
    assert "Nothing But Thieves" not in names


def test_cancelled_show_dropped(parsed: list[ScrapedShow]) -> None:
    # Oliver Tree (Aug 22, in window) keeps its block with a "SHOW CANCELLED"
    # topline; it must not be scraped.
    assert not any(s.headliner_raw == "Oliver Tree" for s in parsed)


def test_comedy_show_dropped() -> None:
    # Fortune Feimster's "… Comedy Tour" title marks a clearly-non-music event;
    # dropped even when the window would include it.
    shows = fox_theater_oakland.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=200
    )
    assert not any("Fortune Feimster" in s.headliner_raw for s in shows)


def test_support_split_on_br(parsed: list[ScrapedShow]) -> None:
    poppy = next(s for s in parsed if s.headliner_raw == "Poppy")
    assert poppy.support_raw == ["LANDMVRKS", "Thousand Below"]


def test_support_featuring_lead_in_stripped(parsed: list[ScrapedShow]) -> None:
    little_feat = next(s for s in parsed if s.headliner_raw == "Little Feat")
    assert little_feat.support_raw == ["Grahame Lesh"]  # from "Featuring Grahame Lesh"


def test_italic_support_annotation_not_an_act(parsed: list[ScrapedShow]) -> None:
    # Thievery Corporation's support element holds only "<i>An all encompassing
    # retrospective</i>" — an annotation, not a support act.
    thievery = next(s for s in parsed if s.headliner_raw == "Thievery Corporation")
    assert thievery.support_raw == []


def test_doors_time_captured(parsed: list[ScrapedShow]) -> None:
    marcus = next(s for s in parsed if s.headliner_raw == "Marcus King Band")
    assert marcus.doors_local == dt.datetime(2026, 7, 7, 19, 0)


def test_ticket_url_captured_when_present(parsed: list[ScrapedShow]) -> None:
    panic = next(s for s in parsed if s.start_local == dt.datetime(2026, 7, 16, 20, 0))
    assert panic.ticket_url == (
        "https://www.ticketmaster.com/widespread-panic-716-oakland-california-07-16-2026"
        "/event/1C006470DDB4EE89?camefrom=CFC_ANOTHERPLANET_web&brand=anotherplanet"
    )


def test_ticket_url_none_when_absent(parsed: list[ScrapedShow]) -> None:
    # The July 18 Widespread Panic night has no ticket button on the listing.
    panic = next(s for s in parsed if s.start_local == dt.datetime(2026, 7, 18, 20, 0))
    assert panic.ticket_url is None


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    marcus = next(s for s in parsed if s.headliner_raw == "Marcus King Band")
    assert marcus.source_url == "https://thefoxoakland.com/events/marcus-king-band-260707"


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "fox_theater_oakland"
    assert show.price_text is None  # the template shows no prices
