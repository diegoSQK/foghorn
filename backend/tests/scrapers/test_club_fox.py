"""Tests for the Club Fox HTML parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window (and the year inference for the page's year-less dates)
doesn't depend on the clock. The fixture (``fixtures/club_fox_2026_07.html``)
is a trimmed snapshot of the live homepage exercising the edge cases — venue
notices with no show date, MUSIC ON THE SQUARE series rows without ticket
links, tagline lines inside the ticket link, "w/" and bare-"Featuring" support
intros, a series label inside the link, an en-dash descriptor glued to an act
name, and an October show just outside the 90-day window.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import club_fox

FIXTURE = Path(__file__).parent.parent / "fixtures" / "club_fox_2026_07.html"
TODAY = dt.date(2026, 7, 3)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return club_fox.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-09T20:00:00", "THE CHINA CATS"),
        ("2026-07-10T17:30:00", "SOUNDS OF SKYNYRD"),  # series label skipped
        ("2026-07-11T19:30:00", "THE SUN KINGS"),  # taglines inside link ignored
        ("2026-07-17T17:30:00", "NATIVE ELEMENTS"),  # "– Reggae" stripped
        ("2026-07-18T20:30:00", "THE DEVIL IN CALIFORNIA"),
        ("2026-07-23T19:30:00", "ALEX JORDAN & FRIENDS"),  # GRATEFUL THURSDAYS label
        ("2026-07-26T19:30:00", "EARL THOMAS"),
        ("2026-07-31T17:30:00", "MERCY AND THE HEARTBEATS"),  # trailing "–" stripped
        ("2026-08-01T20:00:00", "ZEBOP! The Music of Santana"),
        ("2026-08-23T18:30:00", "LUCE"),
    ]


def test_show_time_preferred_over_doors(parsed: list[ScrapedShow]) -> None:
    # "Doors 7PM / Show 8PM" → start 8pm, doors 7pm.
    china = next(s for s in parsed if s.headliner_raw == "THE CHINA CATS")
    assert china.start_local == dt.datetime(2026, 7, 9, 20, 0)
    assert china.doors_local == dt.datetime(2026, 7, 9, 19, 0)


def test_doors_only_row_uses_doors_as_start(parsed: list[ScrapedShow]) -> None:
    # MUSIC ON THE SQUARE rows carry only "Doors 5:30PM".
    skynyrd = next(s for s in parsed if s.headliner_raw == "SOUNDS OF SKYNYRD")
    assert skynyrd.start_local == dt.datetime(2026, 7, 10, 17, 30)
    assert skynyrd.doors_local == dt.datetime(2026, 7, 10, 17, 30)


def test_support_from_w_slash_line(parsed: list[ScrapedShow]) -> None:
    devil = next(s for s in parsed if s.headliner_raw == "THE DEVIL IN CALIFORNIA")
    assert devil.support_raw == ["ZED & RANCHERO"]


def test_support_from_bare_featuring_line(parsed: list[ScrapedShow]) -> None:
    earl = next(s for s in parsed if s.headliner_raw == "EARL THOMAS")
    assert earl.support_raw == ["THE ANTHONY CULLINS BAND"]


def test_support_from_special_guest_spillover(parsed: list[ScrapedShow]) -> None:
    # "LUCE w/Special guest <br> Jeffrey Halford and the Healers".
    luce = next(s for s in parsed if s.headliner_raw == "LUCE")
    assert luce.support_raw == ["Jeffrey Halford and the Healers"]


def test_ticket_url_captured_when_present(parsed: list[ScrapedShow]) -> None:
    china = next(s for s in parsed if s.headliner_raw == "THE CHINA CATS")
    assert china.ticket_url == (
        "https://www.eventbrite.com/e/the-china-cats-tickets-1990675830998"
        "?aff=oddtdtcreator&keep_tld=true"
    )


def test_ticket_url_none_for_free_series(parsed: list[ScrapedShow]) -> None:
    skynyrd = next(s for s in parsed if s.headliner_raw == "SOUNDS OF SKYNYRD")
    assert skynyrd.ticket_url is None


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # October 2 is 91 days past the pinned today (> 90-day window).
    assert not any(s.headliner_raw == "SHRED IS DEAD" for s in parsed)


def test_window_size_is_respected() -> None:
    # A 10-day window from today catches only the first three shows.
    shows = club_fox.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=10
    )
    assert [s.headliner_raw for s in shows] == [
        "THE CHINA CATS",
        "SOUNDS OF SKYNYRD",
        "THE SUN KINGS",
    ]


def test_venue_notices_are_not_shows(parsed: list[ScrapedShow]) -> None:
    # The "over 21" and holiday-closure headings carry no standalone date line.
    assert not any("21" in s.headliner_raw or "closed" in s.headliner_raw.lower() for s in parsed)
    assert not any(s.start_local.date() == dt.date(2026, 7, 4) for s in parsed)


def test_source_url_is_homepage(parsed: list[ScrapedShow]) -> None:
    # No per-event pages on the venue site; provenance is the homepage listing.
    assert all(s.source_url == "https://clubfoxrwc.com/" for s in parsed)


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "club_fox"
    assert show.price_text is None
    assert show.genre is None
