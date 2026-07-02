"""Tests for the Ocean Ale House TSV parser.

Fixture-driven and deterministic: ``parse_tsv`` takes an injected ``today`` so
the 90-day window and year inference don't depend on the clock. The fixture
(``fixtures/ocean_ale_house_2026_07.tsv``) is a trimmed snapshot of the venue's
``events.tsv`` exercising the edge cases — three shows on one day, past-dated
rows, non-music nights (game/trivia/karaoke) to drop, ambiguous entries to
keep, placeholder titles ("-", "#N/A"), a row with no time, a noon show, and a
far-future row outside the window. Carry-forward columns and December→January
year rollover are exercised with inline TSV snippets.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import ocean_ale_house

FIXTURE = Path(__file__).parent.parent / "fixtures" / "ocean_ale_house_2026_07.tsv"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return ocean_ale_house.parse_tsv(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-03T16:00:00", "Francisco Rosales"),
        ("2026-07-03T19:00:00", "Blame it on Sally"),  # same day, later time
        ("2026-07-03T22:30:00", "DJ Yeee!"),  # ambiguous DJ set is kept
        ("2026-07-04T22:30:00", "AwaBeats"),
        ("2026-07-05T12:00:00", "James Napoli"),  # "12:00 PM" is noon, not midnight
        ("2026-07-05T14:00:00", "Na Wahine"),
        ("2026-07-05T18:00:00", "Ultimate Combo: VGM"),  # "Video Game Jazz" is kept
        ("2026-07-08T19:00:00", "OAH Jazz Jam"),
        ("2026-07-09T19:00:00", "The Nimbles"),
    ]


def test_excludes_past_rows(parsed: list[ScrapedShow]) -> None:
    # June 28-30 and July 1 rows predate the pinned today.
    assert all(s.start_local.date() >= TODAY for s in parsed)
    titles = {s.headliner_raw for s in parsed}
    assert "Karen Segal" not in titles
    assert "Songwriters Open Mic - Vibo" not in titles


def test_excludes_non_music_programming(parsed: list[ScrapedShow]) -> None:
    titles = {s.headliner_raw for s in parsed}
    assert "Game Night" not in titles
    assert "Trivia Night" not in titles
    assert "Karaoke Nights" not in titles


def test_excludes_placeholder_and_timeless_rows(parsed: list[ScrapedShow]) -> None:
    titles = {s.headliner_raw for s in parsed}
    assert "-" not in titles
    assert "#N/A" not in titles
    assert "Ghost Entry" not in titles  # row with an empty time cell


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # December 15 is ~166 days past the pinned today (> 90-day window).
    assert not any(s.headliner_raw == "Far Future Phantoms" for s in parsed)


def test_window_size_is_respected() -> None:
    # A 2-day window from today catches only the July 3 and July 4 shows.
    shows = ocean_ale_house.parse_tsv(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=2
    )
    assert [s.headliner_raw for s in shows] == [
        "Francisco Rosales",
        "Blame it on Sally",
        "DJ Yeee!",
        "AwaBeats",
    ]


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    # The TSV carries no ticket/price/doors data and has no per-event pages.
    show = parsed[0]
    assert show.venue_slug == "ocean_ale_house"
    assert show.support_raw == []
    assert show.doors_local is None
    assert show.ticket_url is None
    assert show.price_text is None
    assert show.source_url == "https://oceanalehouse.com/events/"


def test_blank_month_and_day_carry_forward() -> None:
    # Continuation rows may leave month/day blank; they inherit the previous
    # row's date (the site's own parser does the same).
    tsv = "July\tFri\t3\t7:00 PM\t\tBand One\tJazz\n\t\t\t10:30 PM\t\tBand Two\tFunk\n"
    shows = ocean_ale_house.parse_tsv(tsv, today=TODAY)
    assert [(s.start_local.isoformat(), s.headliner_raw) for s in shows] == [
        ("2026-07-03T19:00:00", "Band One"),
        ("2026-07-03T22:30:00", "Band Two"),
    ]


def test_january_rows_roll_to_next_year_in_december() -> None:
    # The TSV has no year column; near New Year's, a January date must resolve
    # to the coming year, not ~360 days into the past. Also covers the "7 PM"
    # minute-less time format.
    tsv = "January\tFri\t1\t7 PM\t\tNew Year Band\tJazz\n"
    shows = ocean_ale_house.parse_tsv(tsv, today=dt.date(2026, 12, 28))
    assert [s.start_local for s in shows] == [dt.datetime(2027, 1, 1, 19, 0)]
