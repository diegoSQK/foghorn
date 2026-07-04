"""Tests for the Neck of the Woods HTML parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today``
so the 90-day window (and the year inference for the template's year-less
"Fri, Jul 3" dates) doesn't depend on the clock. The fixture
(``fixtures/neck_of_the_woods_2026_07.html``) is a trimmed snapshot of the
live homepage list exercising the edge cases — a four-act slash bill, an
unspaced slash that must stay joined, the weekly karaoke/open-mic/comedy
rows (dropped), a row with its Buy Tickets button trimmed, a verbatim
duplicate row from the email-signup popup, and the live pagination block.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import neck_of_the_woods
from foghorn.scrapers._ticketweb_calendar import find_next_page_url

FIXTURE = Path(__file__).parent.parent / "fixtures" / "neck_of_the_woods_2026_07.html"
TODAY = dt.date(2026, 7, 3)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return neck_of_the_woods.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-03T19:30:00", "Frolic"),  # today itself is in the window
        ("2026-07-04T20:00:00", "Pussy Whipped"),
        ("2026-07-19T21:00:00", "High Fantasy"),
    ]


def test_non_music_series_dropped(parsed: list[ScrapedShow]) -> None:
    # Weekly karaoke / open mic / stand-up rows are clearly not concerts.
    names = [s.headliner_raw for s in parsed]
    assert not any("Karaoke" in n or "Open Mic" in n or "Comedy" in n for n in names)


def test_duplicate_popup_row_deduped(parsed: list[ScrapedShow]) -> None:
    # The Frolic row appears twice in the fixture (email-signup popup copy).
    assert sum(1 for s in parsed if s.headliner_raw == "Frolic") == 1


def test_window_size_is_respected() -> None:
    # A 0-day window (today only, inclusive) catches only the July 3 show.
    shows = neck_of_the_woods.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=0
    )
    assert [s.headliner_raw for s in shows] == ["Frolic"]


def test_slash_bill_split_into_headliner_and_support(parsed: list[ScrapedShow]) -> None:
    frolic = next(s for s in parsed if s.headliner_raw == "Frolic")
    assert frolic.support_raw == ["Blind Illusion", "Broken Glass Sanctuary", "Hemotoxin"]


def test_unspaced_slash_stays_one_act(parsed: list[ScrapedShow]) -> None:
    pw = next(s for s in parsed if s.headliner_raw == "Pussy Whipped")
    assert pw.support_raw == ["Mahbuhay Gardens", "W*B*PR*S*NC*/The Unevicted"]


def test_single_act_not_split(parsed: list[ScrapedShow]) -> None:
    hf = next(s for s in parsed if s.headliner_raw == "High Fantasy")
    assert hf.support_raw == []


def test_w_slash_is_not_a_bill_separator() -> None:
    assert neck_of_the_woods._split_bill("Some Band w/ Special Guest") == (
        "Some Band w/ Special Guest",
        [],
    )


def test_doors_and_price_captured_from_row(parsed: list[ScrapedShow]) -> None:
    frolic = next(s for s in parsed if s.headliner_raw == "Frolic")
    assert frolic.doors_local == dt.datetime(2026, 7, 3, 19, 0)
    assert frolic.price_text == "$19.00"


def test_ticket_url_captured_when_present(parsed: list[ScrapedShow]) -> None:
    frolic = next(s for s in parsed if s.headliner_raw == "Frolic")
    assert frolic.ticket_url == (
        "https://www.ticketweb.com/event/frolic-blind-illusion-broken-glass"
        "-neck-of-the-woods-tickets/14897083?pl=nwoods&REFID=clientsitewp"
    )


def test_ticket_url_none_when_absent(parsed: list[ScrapedShow]) -> None:
    hf = next(s for s in parsed if s.headliner_raw == "High Fantasy")
    assert hf.ticket_url is None


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    frolic = next(s for s in parsed if s.headliner_raw == "Frolic")
    assert frolic.source_url == (
        "https://www.neckofthewoodssf.com/tm-event"
        "/frolic-blind-illusion-broken-glass-sanctuary-plague-ritual/"
    )


def test_next_page_link_found() -> None:
    # The live tm-paginate block is kept in the fixture; scrape() walks it.
    assert (
        find_next_page_url(FIXTURE.read_text(encoding="utf-8"))
        == "https://www.neckofthewoodssf.com/page/2/"
    )


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    for show in parsed:
        assert show.venue_slug == "neck_of_the_woods"
        assert show.event_type is None
        assert show.genre is None
