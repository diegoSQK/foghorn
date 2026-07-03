"""Tests for the 924 Gilman ShowSlinger parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today``
so the 90-day window doesn't depend on the clock. The fixture
(``fixtures/gilman_924_2026_07.html``) is a trimmed snapshot of the live
ShowSlinger listing exercising the edge cases — grid-layout duplicate cards
that must be ignored, "+"- and comma-packed bills, a "More!" support
placeholder, a title that must not be split, and dates whose year comes from
the card's numeric filter class.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import gilman_924

FIXTURE = Path(__file__).parent.parent / "fixtures" / "gilman_924_2026_07.html"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return gilman_924.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-03T19:00:00", "Gilman Emo Night!"),
        ("2026-07-08T19:30:00", "The Wameki (Japan)"),
        ("2026-07-10T19:00:00", "Schlong"),
        ("2026-07-12T18:30:00", "HappyDays Presents: Parting Gift"),
        ("2026-08-09T19:30:00", "2Morrows June"),
        ("2026-08-15T20:00:00", "Lapse of Memory Presents: Ink and Dagger"),
    ]


def test_grid_layout_duplicates_ignored(parsed: list[ScrapedShow]) -> None:
    # The fixture carries grid-layout duplicate cards for two shows (as the
    # live page does); only the list-layout cards must be parsed.
    emo = [s for s in parsed if s.headliner_raw == "Gilman Emo Night!"]
    assert len(emo) == 1


def test_window_size_is_respected() -> None:
    # A 30-day window from today excludes the two August shows.
    shows = gilman_924.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=30
    )
    assert [s.start_local.date().isoformat() for s in shows] == [
        "2026-07-03",
        "2026-07-08",
        "2026-07-10",
        "2026-07-12",
    ]


def test_plus_bill_split(parsed: list[ScrapedShow]) -> None:
    wameki = next(s for s in parsed if s.headliner_raw == "The Wameki (Japan)")
    assert wameki.support_raw == ["Whine", "Replica Watch"]


def test_comma_bill_split(parsed: list[ScrapedShow]) -> None:
    schlong = next(s for s in parsed if s.headliner_raw == "Schlong")
    assert schlong.support_raw == [
        "Party Force",
        "Bobby Joe Ebola",
        "Flamango Bay",
        "Contraptions",
    ]


def test_more_support_placeholder_dropped(parsed: list[ScrapedShow]) -> None:
    # "HappyDays Presents: Parting Gift + Haunted Samurai Files + More!"
    happydays = next(s for s in parsed if s.headliner_raw.startswith("HappyDays"))
    assert happydays.support_raw == ["Haunted Samurai Files"]


def test_unpacked_title_not_split(parsed: list[ScrapedShow]) -> None:
    emo = next(s for s in parsed if s.headliner_raw == "Gilman Emo Night!")
    assert emo.support_raw == []


def test_year_resolved_from_card_class(parsed: list[ScrapedShow]) -> None:
    # The visible date is just "Aug 15"; the year comes from the card's
    # "<day><month><year>" filter class ("1582026").
    lapse = next(s for s in parsed if s.headliner_raw.startswith("Lapse of Memory"))
    assert lapse.start_local == dt.datetime(2026, 8, 15, 20, 0)


def test_ticket_url_is_clean_per_event_page(parsed: list[ScrapedShow]) -> None:
    # Hrefs are relative and carry widget-referrer query params; the parser
    # absolutizes and strips them.
    emo = next(s for s in parsed if s.headliner_raw == "Gilman Emo Night!")
    assert emo.ticket_url == "https://app.showslinger.com/v/gilman-emo-night"
    assert emo.source_url == emo.ticket_url


def test_price_text_captured(parsed: list[ScrapedShow]) -> None:
    emo = next(s for s in parsed if s.headliner_raw == "Gilman Emo Night!")
    assert emo.price_text == "$10"


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "gilman_924"
    assert show.doors_local is None  # cards carry a single time, no doors line
