"""Tests for the Felton Music Hall Webflow-card parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected
``today``. The fixture (``fixtures/felton_music_hall_2026_07.html``) is a
trimmed snapshot of the live homepage exercising the edge cases — a card
with both door and show times, a card whose door-time slot is an empty
``w-dyn-bind-empty`` div, an HTML-entity name, a non-default 7 pm start,
and dates past the 90-day window.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import felton_music_hall

FIXTURE = Path(__file__).parent.parent / "fixtures" / "felton_music_hall_2026_07.html"
TODAY = dt.date(2026, 7, 9)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return felton_music_hall.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_expected_shows_in_window(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    # Amélie Farren (Oct 17), Andrew McMahon (Nov 20), and Pokey LaFarge
    # (Dec 17) fall outside the 90-day window pinned to 2026-07-09.
    assert got == [
        ("2026-07-09T20:00:00", "Beth Stelling: Let Me Get Loose (Fully Seated)"),
        ("2026-07-11T20:00:00", "Strangelove - The Depeche Mode Experience"),
        ("2026-07-12T20:00:00", "Nick Lutsko"),
    ]


def test_doors_optional_and_ticket_links(parsed: list[ScrapedShow]) -> None:
    beth = parsed[0]
    assert beth.doors_local == dt.datetime(2026, 7, 9, 19, 0)
    assert beth.ticket_url == "https://tixr.com/e/177955"
    # Strangelove's door-time div is an empty w-dyn-bind-empty slot.
    strangelove = parsed[1]
    assert strangelove.doors_local is None
    assert strangelove.ticket_url == "https://tixr.com/e/189096"


def test_window_and_nondefault_times() -> None:
    shows = felton_music_hall.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=365
    )
    # HTML-entity name survives cleanly; 5:30 pm start parsed as stated.
    amelie = next(s for s in shows if s.headliner_raw.startswith("Amélie"))
    assert amelie.start_local == dt.datetime(2026, 10, 17, 17, 30)
    mcmahon = next(s for s in shows if "McMahon" in s.headliner_raw)
    assert mcmahon.start_local == dt.datetime(2026, 11, 20, 19, 0)
    assert mcmahon.doors_local == dt.datetime(2026, 11, 20, 18, 0)
