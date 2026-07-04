"""Tests for The Warfield carbonhouse events-listing parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today``
so the 90-day window doesn't depend on the clock. The fixture
(``fixtures/the_warfield_2026_07.html``) is a trimmed snapshot of the live
``/events`` blocks exercising the edge cases — a single support act
("with julie"), a comma-separated support list, a "with special guest" label,
a no-support block, and an out-of-window block (The Dresden Dolls, Oct 7,
taken verbatim from the live ``events_ajax`` fragment — the same markup, so
one fixture covers both). One block is synthesized from the same real markup
because no live example existed at snapshot time: a comedy showcase (the
non-music title filter). Warfield dates include the year, so there is no
rollover inference to pin down.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import the_warfield

FIXTURE = Path(__file__).parent.parent / "fixtures" / "the_warfield_2026_07.html"
TODAY = dt.date(2026, 7, 3)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return the_warfield.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-08-11T20:00:00", "Interpol"),
        ("2026-08-13T20:00:00", "BossMan Dlow"),
        ("2026-08-14T20:00:00", "Tomahawk"),
        ("2026-09-09T20:00:00", "Blood Orange"),
    ]


def test_single_support_act(parsed: list[ScrapedShow]) -> None:
    # h4 "with julie" — lead-in stripped, one act.
    interpol = next(s for s in parsed if s.headliner_raw == "Interpol")
    assert interpol.support_raw == ["julie"]


def test_comma_separated_support_split(parsed: list[ScrapedShow]) -> None:
    # h4 "with Yung Miami, Bally Baby" — lead-in stripped, comma-split.
    bossman = next(s for s in parsed if s.headliner_raw == "BossMan Dlow")
    assert bossman.support_raw == ["Yung Miami", "Bally Baby"]


def test_special_guest_label_stripped(parsed: list[ScrapedShow]) -> None:
    # h4 "with special guest Melvins" — the whole label is stripped.
    tomahawk = next(s for s in parsed if s.headliner_raw == "Tomahawk")
    assert tomahawk.support_raw == ["Melvins"]


def test_no_support_line(parsed: list[ScrapedShow]) -> None:
    blood_orange = next(s for s in parsed if s.headliner_raw == "Blood Orange")
    assert blood_orange.support_raw == []


def test_ticket_and_source_urls(parsed: list[ScrapedShow]) -> None:
    interpol = next(s for s in parsed if s.headliner_raw == "Interpol")
    # Tickets sell through axs.com; provenance is the venue's detail page.
    assert interpol.ticket_url == (
        "https://www.axs.com/events/1427064/interpol-tickets"
        "?skin=warfield&src=AEGLIVE_WWRFLSFO022715VEN001"
    )
    assert interpol.source_url == "https://www.thewarfieldtheatre.com/events/detail/1427064"


def test_out_of_window_excluded(parsed: list[ScrapedShow]) -> None:
    # The Dresden Dolls block (Oct 7) is ~96 days out: excluded at the default
    # 90-day window, included when the window is widened.
    assert not any(s.headliner_raw == "The Dresden Dolls" for s in parsed)
    wide = the_warfield.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=120
    )
    dresden = next(s for s in wide if s.headliner_raw == "The Dresden Dolls")
    assert dresden.start_local == dt.datetime(2026, 10, 7, 20, 0)


def test_non_music_title_dropped(parsed: list[ScrapedShow]) -> None:
    # The comedy showcase (Sep 18) is in-window, so its absence is the
    # non-music keyword filter, not the date filter.
    assert not any("Comedy" in s.headliner_raw for s in parsed)


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "the_warfield"
    assert show.doors_local is None  # the listing shows no doors times
    assert show.price_text is None  # ... and no prices
    assert show.genre is None  # ... and no genres
