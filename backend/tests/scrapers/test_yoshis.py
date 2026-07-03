"""Tests for the Yoshi's calendarJson parser.

Fixture-driven and deterministic: ``parse_events`` takes an injected ``today``
so the 90-day window doesn't depend on the clock. The fixtures are trimmed
snapshots of the live feed — ``fixtures/yoshis_2026_07.json`` (the fullCalendar
JSON: two sets on one night, a sold-out entry with no ticket href, a "7:00 PM"
time with a space, an ampersand title, and a window-boundary event) and
``fixtures/yoshis_2026_07_prices.html`` (two rows of the HTML calendar, the
price source joined by detail URL).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import yoshis

FIXTURES = Path(__file__).parent.parent / "fixtures"
EVENTS_FIXTURE = FIXTURES / "yoshis_2026_07.json"
PRICES_FIXTURE = FIXTURES / "yoshis_2026_07_prices.html"
TODAY = dt.date(2026, 7, 1)

KINDRED_URL = "https://yoshis.com/events/buy-tickets/kindred-the-family-soul-7/detail"
PATRON_URL = "https://yoshis.com/events/sold-out/patron-latin-rhythms-1/detail"


def _events() -> list[dict[str, object]]:
    events: list[dict[str, object]] = json.loads(EVENTS_FIXTURE.read_text(encoding="utf-8"))
    return events


@pytest.fixture
def prices() -> dict[str, str]:
    return yoshis.parse_price_map(PRICES_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def parsed(prices: dict[str, str]) -> list[ScrapedShow]:
    return yoshis.parse_events(_events(), today=TODAY, prices=prices)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-02T19:30:00", "KINDRED THE FAMILY SOUL"),
        ("2026-07-02T21:30:00", "KINDRED THE FAMILY SOUL"),  # second set, same night
        ("2026-07-03T20:00:00", "PATRON LATIN RHYTHMS"),  # sold out
        (
            "2026-07-05T19:00:00",  # "7:00 PM" with a space before the meridiem
            "BLUES EXPLOSION FEAT. THE DYNAMIC MISS FAYE CAROL, FILLMORE SLIM,"
            " LADY BIANCA & ALVON JOHNSON",
        ),
        ("2026-07-06T20:00:00", "MUSIC MONDAY INDIE NIGHT FEAT. RYAN ALLAY AND JORDYN DIEW"),
    ]


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # September 30 is 91 days past the pinned today (> 90-day window).
    assert not any(s.headliner_raw == "SPYRO GYRA" for s in parsed)


def test_window_size_is_respected() -> None:
    # A 2-day window from today catches only the July 2 sets and July 3.
    shows = yoshis.parse_events(_events(), today=TODAY, window_days=2)
    assert [s.start_local.isoformat() for s in shows] == [
        "2026-07-02T19:30:00",
        "2026-07-02T21:30:00",
        "2026-07-03T20:00:00",
    ]


def test_ticket_url_is_per_set_etix_link(parsed: list[ScrapedShow]) -> None:
    early, late = (s for s in parsed if s.headliner_raw == "KINDRED THE FAMILY SOUL")
    assert early.ticket_url == (
        "https://www.etix.com/ticket/p/46236417/kindred-the-family-soul-thu7226-oakland-yoshis"
    )
    assert late.ticket_url == (
        "https://www.etix.com/ticket/p/60885990/kindred-the-family-soul-thu7226-oakland-yoshis"
    )


def test_ticket_url_none_when_sold_out(parsed: list[ScrapedShow]) -> None:
    patron = next(s for s in parsed if s.headliner_raw == "PATRON LATIN RHYTHMS")
    assert patron.ticket_url is None


def test_source_url_is_per_event_detail_page(parsed: list[ScrapedShow]) -> None:
    assert parsed[0].source_url == KINDRED_URL
    patron = next(s for s in parsed if s.headliner_raw == "PATRON LATIN RHYTHMS")
    assert patron.source_url == PATRON_URL


def test_price_map_parsed_from_calendar_html(prices: dict[str, str]) -> None:
    assert prices == {KINDRED_URL: "$49 - $89", PATRON_URL: "$25 - $49"}


def test_price_text_joined_by_detail_url(parsed: list[ScrapedShow]) -> None:
    assert parsed[0].price_text == "$49 - $89"
    patron = next(s for s in parsed if s.headliner_raw == "PATRON LATIN RHYTHMS")
    assert patron.price_text == "$25 - $49"


def test_price_text_none_when_url_not_on_calendar_page(parsed: list[ScrapedShow]) -> None:
    blues = next(s for s in parsed if s.headliner_raw.startswith("BLUES EXPLOSION"))
    assert blues.price_text is None


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "yoshis"
    assert show.support_raw == []
    assert show.doors_local is None
