"""Tests for the Keys Jazz Bistro HTML parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture
(``fixtures/keys_jazz_bistro_2026_05.html``) is a trimmed snapshot of the live
``/upcoming-shows/`` page exercising the edge cases — three shows on one day, a
time with minutes, curly quotes/apostrophes in the title, an event with no
ticket link, a description paragraph that must not be read as the date, and a
far-future event excluded by the window.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import keys_jazz_bistro

FIXTURE = Path(__file__).parent.parent / "fixtures" / "keys_jazz_bistro_2026_05.html"
TODAY = dt.date(2026, 5, 23)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return keys_jazz_bistro.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-05-23T19:00:00", "Lavay Smith & Her Red Hot Skillet Lickers"),
        ("2026-05-23T21:00:00", "Fog City Swing"),  # same day, later time
        ("2026-05-23T22:30:00", "Late Set: Simon Rowe Organ Trio"),  # minutes
        ("2026-06-04T19:00:00", "Howard Wiley"),
        ("2026-06-10T19:00:00", "Frank Martin/Michael O’Neill Quartet"),  # apostrophe
        ("2026-06-12T19:00:00", "“Emily Day & Cosmo Alleycats”"),  # curly quotes
    ]


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # September 19 is ~119 days past the pinned today (> 90-day window).
    assert not any(s.headliner_raw == "Out-Of-Window Octet" for s in parsed)


def test_window_size_is_respected() -> None:
    # A 7-day window from today catches only the three May 23 shows.
    shows = keys_jazz_bistro.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=7
    )
    assert [s.headliner_raw for s in shows] == [
        "Lavay Smith & Her Red Hot Skillet Lickers",
        "Fog City Swing",
        "Late Set: Simon Rowe Organ Trio",
    ]


def test_description_paragraph_not_mistaken_for_date(parsed: list[ScrapedShow]) -> None:
    # The Lavay Smith item carries a prose <p> mentioning "May"; the parser must
    # read the date from the dedicated date line, yielding 7pm not something else.
    lavay = next(s for s in parsed if s.headliner_raw.startswith("Lavay Smith"))
    assert lavay.start_local == dt.datetime(2026, 5, 23, 19, 0)


def test_ticket_url_captured_when_present(parsed: list[ScrapedShow]) -> None:
    fog = next(s for s in parsed if s.headliner_raw == "Fog City Swing")
    assert fog.ticket_url == "https://keysjazzbistro.com/cart/?add-to-cart=74363&ticket=true"


def test_ticket_url_none_when_absent(parsed: list[ScrapedShow]) -> None:
    howard = next(s for s in parsed if s.headliner_raw == "Howard Wiley")
    assert howard.ticket_url is None


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    fog = next(s for s in parsed if s.headliner_raw == "Fog City Swing")
    assert fog.source_url == "https://keysjazzbistro.com/event/fog-city-swing-7/"


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "keys_jazz_bistro"
    assert show.support_raw == []
    assert show.doors_local is None
    assert show.price_text is None
