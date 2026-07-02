"""Tests for the Center for New Music HTML parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture
(``fixtures/center_for_new_music_2026_07.html``) is a trimmed snapshot of the
live ``/event/`` calendar page plus synthetic cards exercising the edge cases —
a same-day show, a noon matinee with pipe characters in the title, a workshop
and the Composer Meetup (non-music, dropped), a card whose date line has no
time (skipped loudly), a door-sales-only card with no ticket link, a
"classical" description that must not trip the ``class`` filter, and past /
far-future events excluded by the window.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import center_for_new_music

FIXTURE = Path(__file__).parent.parent / "fixtures" / "center_for_new_music_2026_07.html"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return center_for_new_music.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY
    )


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        (
            "2026-07-02T20:00:00",  # same-day show is included
            "The World Sinks Except Japan Record Release Party"
            " with special guests Thomas Carnacki",
        ),
        ("2026-07-16T19:00:00", "Sixtyhurts 3: TION, Ava Khoohbor, Antimatter / Jacob Felix Heule"),
        ("2026-07-25T12:00:00", "G|O|D|W|A|F|F|L|E||N|O|I|S|E||P|A|N|C|A|K|E|S"),  # matinee
        ("2026-08-09T15:00:00", "Overtone Choir & Friends"),
    ]


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # October 15 is ~105 days past the pinned today (> 90-day window).
    assert not any(s.headliner_raw == "Out-Of-Window Ensemble" for s in parsed)


def test_excludes_past_event(parsed: list[ScrapedShow]) -> None:
    # July 1 is the day before the pinned today.
    assert not any(s.headliner_raw == "Yesterday’s Drone Orchestra" for s in parsed)


def test_window_size_is_respected() -> None:
    # A 20-day window from today catches only the two mid-July shows.
    shows = center_for_new_music.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=20
    )
    assert [s.start_local.date().isoformat() for s in shows] == [
        "2026-07-02",
        "2026-07-16",
    ]


def test_non_music_events_dropped(parsed: list[ScrapedShow]) -> None:
    titles = [s.headliner_raw for s in parsed]
    # The monthly Composer Meetup and a workshop are not performances.
    assert not any("Meetup" in t for t in titles)
    assert not any("Workshop" in t for t in titles)


def test_classical_does_not_trip_class_filter(parsed: list[ScrapedShow]) -> None:
    # Word-boundary matching: "classical" in a description/title is music.
    assert any(s.headliner_raw == "Overtone Choir & Friends" for s in parsed)


def test_no_time_event_skipped_loudly(capsys: pytest.CaptureFixture[str]) -> None:
    shows = center_for_new_music.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY
    )
    # Never invent a time: the bare-date card yields no show...
    assert not any(s.headliner_raw == "Tape Loop Séance" for s in shows)
    # ...and the skip is loud (visible in scrape output on stderr).
    err = capsys.readouterr().err
    assert "Tape Loop Séance" in err
    assert "no parseable start time" in err


def test_ticket_url_captured_when_present(parsed: list[ScrapedShow]) -> None:
    world_sinks = next(s for s in parsed if s.headliner_raw.startswith("The World Sinks"))
    assert world_sinks.ticket_url == (
        "https://www.eventbrite.com/e/the-world-sinks-except-japan-record-release-"
        "party-tickets-1991777092902?aff=oddtdtcreator"
    )


def test_ticket_url_none_when_door_sales_only(parsed: list[ScrapedShow]) -> None:
    overtone = next(s for s in parsed if s.headliner_raw == "Overtone Choir & Friends")
    assert overtone.ticket_url is None


def test_price_text_without_tickets_label(parsed: list[ScrapedShow]) -> None:
    world_sinks = next(s for s in parsed if s.headliner_raw.startswith("The World Sinks"))
    assert world_sinks.price_text == "$15 General Admission, $10 Members & Students"
    overtone = next(s for s in parsed if s.headliner_raw == "Overtone Choir & Friends")
    assert overtone.price_text == "Sliding scale $10–$20 at the door"


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    gwaffle = next(s for s in parsed if s.headliner_raw.startswith("G|O|D"))
    assert gwaffle.source_url == "https://centerfornewmusic.com/event/godwafflenoisepancakes-35/"


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "center_for_new_music"
    assert show.support_raw == []
    assert show.doors_local is None
