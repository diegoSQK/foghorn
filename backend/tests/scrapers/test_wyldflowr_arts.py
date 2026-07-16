"""Tests for the Wyldflowr Arts Viewcy-API parser.

The fixture is a trimmed snapshot of the live
``viewcy.com/api/o/wyldflowrarts/courses`` payload — the real 14-course slate
(12 concerts + 2 classes), with the oversized image URLs and description bodies
cut down. It carries the cases that matter: a tagged jam, a workshop, a
same-day master-class-plus-concert pair, and untagged guest bookings.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import wyldflowr_arts

FIXTURE = Path(__file__).parent.parent / "fixtures" / "wyldflowr_arts_2026_07.json"
TODAY = dt.date(2026, 7, 16)


@pytest.fixture
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def parsed(payload: dict) -> list[ScrapedShow]:
    return wyldflowr_arts.parse_courses(payload, today=TODAY)


def test_concerts_parsed_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got[:4] == [
        ("2026-07-16T19:30:00", "Prayog - An Evening of Hindustani Classical Music"),
        ("2026-07-18T13:00:00", "Wyld Jam"),
        (
            "2026-07-23T19:30:00",
            "Akshay Anantapadmanabhan's Nam Dhi Ensemble - A Contemporary Carnatic"
            " Percussive Taalavaadya",
        ),
        ("2026-07-25T14:00:00", "Maddie Liu - JiTN @ Wyldflowr Arts"),
    ]
    # 14 courses in, 2 classes dropped.
    assert len(got) == 12


def test_utc_converted_to_venue_local(parsed: list[ScrapedShow]) -> None:
    # starts_at "2026-07-17T02:30:00.000Z" is 19:30 the previous day in PDT —
    # the date rolls back, so a naive truncation would file this a day late.
    prayog = next(s for s in parsed if s.headliner_raw.startswith("Prayog"))
    assert prayog.start_local == dt.datetime(2026, 7, 16, 19, 30)
    assert prayog.start_local.tzinfo is None


def test_workshops_filtered_out(parsed: list[ScrapedShow]) -> None:
    names = [s.headliner_raw for s in parsed]
    assert not any("Vocal Workshop" in n for n in names)  # tagged workshop
    assert not any("Master Class" in n for n in names)  # tagged workshop/clinic


def test_workshop_plus_concert_keeps_only_the_concert(parsed: list[ScrapedShow]) -> None:
    # Mike Monford books a master class and an evening concert on the same day;
    # the concert is the artifact of interest.
    same_day = [s for s in parsed if s.start_local.date() == dt.date(2026, 8, 30)]
    # The venue's title carries a double space; the parser collapses it.
    assert [s.headliner_raw for s in same_day] == [
        "Concert: Mike Monford - An Evening Of Jazz & Afrofuturism"
    ]
    assert same_day[0].start_local == dt.datetime(2026, 8, 30, 16, 0)


def test_untagged_bookings_kept(parsed: list[ScrapedShow]) -> None:
    # Genre isn't obvious and Viewcy carries no tags — err toward inclusion.
    names = {s.headliner_raw for s in parsed}
    assert "Nora Free Liberation Qtet" in names
    assert "Morley & Chris Bruce: Soul, Jazz & Folk" in names


def test_jam_tagged_explicitly(parsed: list[ScrapedShow]) -> None:
    # "Wyld Jam" matches no ingest jam-title pattern, so the tag has to carry it.
    jam = next(s for s in parsed if s.headliner_raw == "Wyld Jam")
    assert jam.event_type == "jam"
    assert all(s.event_type is None for s in parsed if s.headliner_raw != "Wyld Jam")


def test_ticket_url_and_price(parsed: list[ScrapedShow]) -> None:
    prayog = next(s for s in parsed if s.headliner_raw.startswith("Prayog"))
    assert prayog.ticket_url == "https://www.viewcy.com/event/shreyas_ravindra__sk"
    assert prayog.source_url == "https://www.viewcy.com/event/shreyas_ravindra__sk"
    # Tiers: Early Bird 21.87, General Admission 0.0, Student/Senior 19.78.
    assert prayog.price_text == "$0–$22"


def test_window_excludes_far_future(payload: dict) -> None:
    # Window is inclusive on both ends: 07-16 + 14d admits 07-30, drops 07-31 on.
    parsed = wyldflowr_arts.parse_courses(payload, today=TODAY, window_days=14)
    assert [s.start_local.date() for s in parsed] == [
        dt.date(2026, 7, 16),
        dt.date(2026, 7, 18),
        dt.date(2026, 7, 23),
        dt.date(2026, 7, 25),
        dt.date(2026, 7, 25),
        dt.date(2026, 7, 30),
    ]


def test_past_events_excluded(payload: dict) -> None:
    parsed = wyldflowr_arts.parse_courses(payload, today=dt.date(2026, 8, 25))
    assert all(s.start_local.date() >= dt.date(2026, 8, 25) for s in parsed)
    assert parsed  # the late-Aug/Sep slate survives


def test_venue_slug_and_no_support(parsed: list[ScrapedShow]) -> None:
    assert {s.venue_slug for s in parsed} == {"wyldflowr_arts"}
    # Viewcy titles are single billings; the bill isn't broken out.
    assert all(s.support_raw == [] for s in parsed)
