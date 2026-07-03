"""Tests for The Chapel SeeTickets-card parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture
(``fixtures/the_chapel_2026_07.html``) is a trimmed snapshot of the live
``/calendar/`` list cards exercising the edge cases — a real supporting-talent
list, a no-support card, a co-billed multi-act headliners line, a Sports
General card (World Cup screening "at Curio"), a "Private Event" hold card, an
out-of-window card, and a next-calendar-year card (dates carry no year). It
also carries the AJAX nonce script and the seven-page pagination strip the
pager helpers read.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import the_chapel

FIXTURE = Path(__file__).parent.parent / "fixtures" / "the_chapel_2026_07.html"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return the_chapel.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-07T20:00:00", "Dylan LeBlanc"),
        ("2026-07-10T21:00:00", "EMM"),
        ("2026-07-11T21:00:00", "Petty Theft"),
        ("2026-07-23T20:00:00", "Natural Information Society"),
    ]


def test_supporting_talent_parsed(parsed: list[ScrapedShow]) -> None:
    # "Supporting Talent: Bentley Robles, TeZATalks" — label stripped, split.
    emm = next(s for s in parsed if s.headliner_raw == "EMM")
    assert emm.support_raw == ["Bentley Robles", "TeZATalks"]


def test_no_support_is_empty(parsed: list[ScrapedShow]) -> None:
    petty_theft = next(s for s in parsed if s.headliner_raw == "Petty Theft")
    assert petty_theft.support_raw == []


def test_cobilled_headliners_split_top_billing_first(parsed: list[ScrapedShow]) -> None:
    # p.headliners "Natural Information Society, Bitchin Bajas" plus
    # "Supporting Talent: Jill Fraser": co-headliner joins the support list.
    nis = next(s for s in parsed if s.headliner_raw == "Natural Information Society")
    assert nis.support_raw == ["Bitchin Bajas", "Jill Fraser"]


def test_doors_and_showtime(parsed: list[ScrapedShow]) -> None:
    # "Doors at 7:00PM / Show at 8:00PM" — show is start, doors kept separately.
    dylan = next(s for s in parsed if s.headliner_raw == "Dylan LeBlanc")
    assert dylan.start_local == dt.datetime(2026, 7, 7, 20, 0)
    assert dylan.doors_local == dt.datetime(2026, 7, 7, 19, 0)


def test_price_and_ticket_and_source(parsed: list[ScrapedShow]) -> None:
    dylan = next(s for s in parsed if s.headliner_raw == "Dylan LeBlanc")
    expected_url = (
        "https://wl.seetickets.us/event/"
        "dylan-leblanc-cautionary-tale-10-year-anniversary-tour/691420?afflky=TheChapel"
    )
    assert dylan.price_text == "$22.00-$25.00"
    # The per-event SeeTickets page is both provenance and the ticket link.
    assert dylan.ticket_url == expected_url
    assert dylan.source_url == expected_url


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # "Tue Oct 13" is ~103 days out: excluded at the default 90-day window,
    # included once the window is widened past it.
    assert not any(s.headliner_raw == "Militarie Gun" for s in parsed)
    wide = the_chapel.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=120
    )
    militarie_gun = next(s for s in wide if s.headliner_raw == "Militarie Gun")
    assert militarie_gun.start_local == dt.datetime(2026, 10, 13, 19, 0)
    assert militarie_gun.support_raw == ["Softcult", "Shady Nasty", "Dazy"]


def test_year_rollover_resolves_forward() -> None:
    # "Sun Feb 14" resolves forward past today (Jul 2) into the *next* year;
    # at 250 days it's in-window.
    wide = the_chapel.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=250
    )
    carla = next(s for s in wide if s.headliner_raw == "Carla dal Forno")
    assert carla.start_local == dt.datetime(2027, 2, 14, 20, 0)
    assert carla.support_raw == ["Cindy"]


def test_sports_genre_dropped(parsed: list[ScrapedShow]) -> None:
    # The World Cup screening at Curio is tagged "Sports General"; Jul 2 is
    # inside the window, so its absence is the genre filter, not the date one.
    assert not any("Switzerland" in s.headliner_raw for s in parsed)


def test_private_event_hold_card_dropped(parsed: list[ScrapedShow]) -> None:
    # "Private Event" (Aug 16, in-window) has a showtime but no public billing;
    # its genre ("Other Content") is also used on real shows, so it's matched
    # by name.
    assert not any(s.headliner_raw.lower() == "private event" for s in parsed)


def test_pager_helpers_read_nonce_and_total_pages() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    assert the_chapel._extract_nonce(html) == "628c00b85b"
    assert the_chapel._extract_total_pages(html) == 7


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "the_chapel"
    assert show.doors_local is not None  # doors are given on real cards
    assert show.price_text is not None
