"""Tests for the Cornerstone Berkeley JSON-LD parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today``
so the window doesn't depend on the clock. The fixture
(``fixtures/cornerstone_berkeley_2026_07.html``) is a trimmed copy of the real
events page — JSON-LD Event blocks paired with their card markup (which
carries the ``starts 8:30 pm`` time) — exercising the edge cases: an
HTML-escaped ampersand, a zero-priced offer, a comedy tour and a class
reunion (non-music), an accented name, and an out-of-window event.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import cornerstone_berkeley

FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "cornerstone_berkeley_2026_07.html"
)
TODAY = dt.date(2026, 7, 1)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return cornerstone_berkeley.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY
    )


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        # start time comes from the card markup, not the (date-only) JSON-LD
        ("2026-07-03T20:30:00", "Kelsy Karter & The Heroines: The Pleasure Tour"),
        ("2026-07-05T20:00:00", "Evan Hatfield, Morillo, Mycelial"),
        ("2026-07-17T21:00:00", "RJD2"),
        ("2026-09-19T21:00:00", "Vieux Farka Touré"),  # accent preserved
    ]


def test_excludes_non_music(parsed: list[ScrapedShow]) -> None:
    names = [s.headliner_raw for s in parsed]
    assert not any("Reunion" in n for n in names)  # class reunion
    assert not any("FunkyFrogBait" in n for n in names)  # comedy tour


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # In Her Own Words x Every Avenue is Oct 4, past TODAY + 90 days.
    assert not any("In Her Own Words" in s.headliner_raw for s in parsed)


def test_window_size_is_respected() -> None:
    # A 10-day window from July 1 catches only the two early-July shows.
    shows = cornerstone_berkeley.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=10
    )
    assert [s.start_local.date().isoformat() for s in shows] == [
        "2026-07-03",
        "2026-07-05",
    ]


def test_ampersand_unescaped(parsed: list[ScrapedShow]) -> None:
    assert parsed[0].headliner_raw.startswith("Kelsy Karter & The Heroines")


def test_ticket_url_is_tixr_offer(parsed: list[ScrapedShow]) -> None:
    assert parsed[0].ticket_url == "https://tixr.com/e/171743"
    assert all(
        s.ticket_url is not None and s.ticket_url.startswith("https://tixr.com/e/")
        for s in parsed
    )


def test_price_text_from_offer(parsed: list[ScrapedShow]) -> None:
    assert parsed[0].price_text == "$28"


def test_zero_price_treated_as_unknown(parsed: list[ScrapedShow]) -> None:
    # The page stamps price "0" on shows whose pricing isn't in the schema —
    # that's "unknown", not "free".
    evan = next(s for s in parsed if s.headliner_raw.startswith("Evan Hatfield"))
    assert evan.price_text is None


def test_source_url_is_events_page(parsed: list[ScrapedShow]) -> None:
    assert all(s.source_url == cornerstone_berkeley.EVENTS_URL for s in parsed)


def test_optional_defaults(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    # The single PerformingGroup duplicates the event name, so no support.
    assert show.support_raw == []
    assert show.doors_local is None
    assert show.venue_slug == "cornerstone_berkeley"
