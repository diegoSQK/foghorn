"""Tests for the DNA Lounge iCal parser.

Fixture-driven and deterministic: ``parse_ics`` takes an injected ``today`` so
the window doesn't depend on the clock. The fixture
(``fixtures/dna_lounge_2026_07.ics``) is a trimmed copy of the real feed
exercising the edge cases — an accented single-brand night, ``+``-delimited
co-bills, a movie screening and a tech meetup (non-music), a door-only night
with no ticket sales, a past event, and an out-of-window event.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import dna_lounge

FIXTURE = Path(__file__).parent.parent / "fixtures" / "dna_lounge_2026_07.ics"
TODAY = dt.date(2026, 7, 1)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return dna_lounge.parse_ics(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-03T21:30:00", "Perreo Eléctrico: Latin Rave"),  # accent kept
        ("2026-08-15T21:00:00", "Audiofreq"),
        ("2026-09-04T21:30:00", "Dark Sparkle"),
        ("2026-09-09T19:00:00", "16 Volt"),
    ]


def test_excludes_non_music(parsed: list[ScrapedShow]) -> None:
    names = [s.headliner_raw for s in parsed]
    assert not any("Conan The Barbarian" in n for n in names)  # movie screening
    assert not any("Game Development" in n for n in names)  # meetup


def test_excludes_past_event(parsed: list[ScrapedShow]) -> None:
    # June 27 is before the injected TODAY of July 1.
    assert not any("Kumta" in s.headliner_raw for s in parsed)


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # Dennett is Nov 12, past TODAY + 90 days.
    assert not any(s.headliner_raw == "Dennett" for s in parsed)


def test_window_size_is_respected() -> None:
    # A 5-day window from July 1 only catches the July 3 event.
    shows = dna_lounge.parse_ics(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=5
    )
    assert [s.headliner_raw for s in shows] == ["Perreo Eléctrico: Latin Rave"]


def test_plus_delimited_bill_split(parsed: list[ScrapedShow]) -> None:
    audiofreq = next(s for s in parsed if s.headliner_raw == "Audiofreq")
    assert audiofreq.support_raw == ["Code Black", "Toneshifterz"]
    volt = next(s for s in parsed if s.headliner_raw == "16 Volt")
    assert volt.support_raw == ["Acumen Nation"]


def test_colon_subtitle_not_split(parsed: list[ScrapedShow]) -> None:
    perreo = parsed[0]
    assert perreo.headliner_raw == "Perreo Eléctrico: Latin Rave"
    assert perreo.support_raw == []


def test_source_url_is_event_page(parsed: list[ScrapedShow]) -> None:
    perreo = parsed[0]
    assert perreo.source_url == "https://www.dnalounge.com/calendar/2026/07-03.html"


def test_ticket_url_when_sales_advertised(parsed: list[ScrapedShow]) -> None:
    # "Buy tickets:" in the description -> event page doubles as ticket page.
    perreo = parsed[0]
    assert perreo.ticket_url == perreo.source_url


def test_no_ticket_url_for_door_only_night(parsed: list[ScrapedShow]) -> None:
    dark_sparkle = next(s for s in parsed if s.headliner_raw == "Dark Sparkle")
    assert dark_sparkle.ticket_url is None
    assert dark_sparkle.price_text == "$10 advance; $15 door."


def test_price_text_joined_from_description(parsed: list[ScrapedShow]) -> None:
    perreo = parsed[0]
    assert perreo.price_text == "$10 limited advance; $15 after; $22 door."


def test_optional_defaults(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.doors_local is None
    assert show.venue_slug == "dna_lounge"
