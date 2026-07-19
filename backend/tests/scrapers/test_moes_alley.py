"""Tests for the Moe's Alley popup-dialog parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected
``today``. The fixture (``fixtures/moes_alley_2026_07.html``) is a trimmed
snapshot of the live calendar page's hidden popups exercising the edge
cases — a "Presents:"-prefixed title with " w/ " support, a colon-less
"Doors 7pm / Show 8pm" description, a popup with no stated time (skipped),
and far-future popups excluded by the 90-day window.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import moes_alley

FIXTURE = Path(__file__).parent.parent / "fixtures" / "moes_alley_2026_07.html"
TODAY = dt.date(2026, 7, 19)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return moes_alley.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_expected_shows_in_window(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    # El Sol (Aug 15) states no time — skipped, never fabricated. Wine Lips
    # (Oct 27) and Buck Meek (Dec 8) fall outside the 90-day window.
    assert got == [
        ("2026-07-19T15:00:00", "Dusted Angel"),
        ("2026-07-22T20:00:00", "Western Wednesday #92: Brea Burns and the Boleros x Tony Hannah"),
        ("2026-07-26T16:00:00", "Sue Foley"),
    ]


def test_presents_prefix_and_support_split(parsed: list[ScrapedShow]) -> None:
    dusted = parsed[0]
    # "Moe's Alley Presents: Dusted Angel w/ Phantasmal Abyss + Winter Wind"
    assert dusted.headliner_raw == "Dusted Angel"
    assert dusted.support_raw == ["Phantasmal Abyss", "Winter Wind"]
    assert dusted.doors_local == dt.datetime(2026, 7, 19, 14, 0)
    assert dusted.price_text == "$24.65"
    assert dusted.source_url.endswith("dusted-angel-w-phantasmal-abyss-winter-wind/")
    assert dusted.ticket_url is not None and "ticketweb.com" in dusted.ticket_url


def test_colonless_doors_show_parsed() -> None:
    # Wine Lips' description reads "Doors: 7pm / Show 8pm" (no colon on
    # Show); a 365-day window pulls it in with the right times.
    shows = moes_alley.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=365)
    wine_lips = next(s for s in shows if s.headliner_raw == "Wine Lips")
    assert wine_lips.start_local == dt.datetime(2026, 10, 27, 20, 0)
    assert wine_lips.doors_local == dt.datetime(2026, 10, 27, 19, 0)
    # The folkYEAH promoter credit is stripped and " w/ " split.
    buck = next(s for s in shows if s.headliner_raw == "Buck Meek")
    assert buck.support_raw == ["Kisser"]
