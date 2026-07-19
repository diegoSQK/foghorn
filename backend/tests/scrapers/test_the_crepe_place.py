"""Tests for the Crepe Place Squarespace-collection parser.

Fixture-driven and deterministic: ``parse_items`` takes an injected
``today``. The fixture (``fixtures/the_crepe_place_2026_07.json``) is a
trimmed ``?format=json`` payload exercising the edge cases — flyer titles
with date/time/price/stage noise baked in (comma-separated and not), a
promoter "PRESENTS:" credit, a jam night, a non-music talk series
(dropped), a TicketWeb link in the excerpt, and a far-future item excluded
by the 90-day window.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import the_crepe_place

FIXTURE = Path(__file__).parent.parent / "fixtures" / "the_crepe_place_2026_07.json"
TODAY = dt.date(2026, 7, 19)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return the_crepe_place.parse_items(payload, today=TODAY)


def test_titles_cleaned_and_window_applied(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    # "SCIENCE ON TAP" (talk series) is dropped; the far-future folkYEAH
    # item falls outside the 90-day window. Titles lose their baked-in
    # "SATURDAY AUGUST 1 @9PM, $10"-style noise but keep the billing.
    assert got == [
        ("2026-07-19T18:00:00", "GRATEFUL SUNDAY With MATT HARTLE And The HARTLE GOLD BAND"),
        ("2026-07-20T18:00:00", "FAMILY JAM"),
        ("2026-07-24T20:00:00", "JUNE SWOON, CAREER WOMAN, NOT YET OLD DOG"),
        ("2026-07-28T17:30:00", "JAZZ ON THE ROCKS"),  # comma-less noise
        ("2026-08-01T21:00:00", "ROSEBUD"),
        ("2026-08-05T19:00:00", "ALELA DIANE WITH SHANNON LAY"),  # PRESENTS: stripped
    ]


def test_stated_end_and_jam_type(parsed: list[ScrapedShow]) -> None:
    jam = next(s for s in parsed if s.headliner_raw == "FAMILY JAM")
    assert jam.event_type == "jam"
    assert jam.end_local == dt.datetime(2026, 7, 20, 21, 0)


def test_ticketweb_link_from_excerpt(parsed: list[ScrapedShow]) -> None:
    june = next(s for s in parsed if s.headliner_raw.startswith("JUNE SWOON"))
    assert june.ticket_url is not None and "ticketweb.com" in june.ticket_url
    assert june.source_url.startswith("https://thecrepeplace.com/shows-list/")
