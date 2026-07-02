"""Tests for the Guild Theatre HTML parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture
(``fixtures/guild_theatre_2026_07.html``) is a trimmed snapshot of the live
Webflow homepage exercising the edge cases — HTML-entity names (curly
apostrophe, quoted nickname), a card with non-default door/show times, a card
whose time divs are missing (skipped), a zero-price offer (unknown, not free),
a stand-up comedy booking (dropped), and October/December events excluded by
the window.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import guild_theatre

FIXTURE = Path(__file__).parent.parent / "fixtures" / "guild_theatre_2026_07.html"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return guild_theatre.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-09T20:00:00", "Taj Farrant"),
        ("2026-07-11T20:00:00", "Chasta's Birthday Bash"),  # &#39; unescaped
        ("2026-07-30T20:00:00", 'Christone "Kingfish" Ingram'),  # &quot; unescaped
        ("2026-08-06T20:00:00", "Bad Nerves"),
        ("2026-09-16T19:30:00", "The Infamous Stringdusters"),  # non-default time
    ]


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # Killer Queen (Oct 3) is ~93 days past the pinned today (> 90-day window);
    # Missing Persons (Dec 19) is further still.
    assert not any(s.headliner_raw == "Killer Queen" for s in parsed)
    assert not any(s.headliner_raw.startswith("Missing Persons") for s in parsed)


def test_window_size_is_respected() -> None:
    # A 365-day window pulls in the October/December shows (but still no comedy).
    shows = guild_theatre.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=365
    )
    assert [s.headliner_raw for s in shows] == [
        "Taj Farrant",
        "Chasta's Birthday Bash",
        'Christone "Kingfish" Ingram',
        "Bad Nerves",
        "The Infamous Stringdusters",
        "Killer Queen",
        "Missing Persons - Rescheduled from May 30th -",
    ]


def test_non_music_dropped() -> None:
    # "French Stand Up Comedian - Jérémy Charbonnel" (Oct 28) is comedy, not
    # music — dropped even when the window would otherwise include it.
    shows = guild_theatre.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=365
    )
    assert not any("Comedian" in s.headliner_raw for s in shows)


def test_card_without_time_skipped(parsed: list[ScrapedShow]) -> None:
    # The Margo Price card (Jul 18) carries no door/show time markup; the bare
    # JSON-LD date must not be invented into a start.
    assert not any(s.headliner_raw.startswith("Margo Price") for s in parsed)


def test_doors_and_start_times(parsed: list[ScrapedShow]) -> None:
    dusters = next(s for s in parsed if s.headliner_raw == "The Infamous Stringdusters")
    assert dusters.start_local == dt.datetime(2026, 9, 16, 19, 30)
    assert dusters.doors_local == dt.datetime(2026, 9, 16, 18, 30)


def test_ticket_url_from_offer(parsed: list[ScrapedShow]) -> None:
    taj = next(s for s in parsed if s.headliner_raw == "Taj Farrant")
    assert taj.ticket_url == "https://tixr.com/e/183515"


def test_price_text_from_offer(parsed: list[ScrapedShow]) -> None:
    taj = next(s for s in parsed if s.headliner_raw == "Taj Farrant")
    assert taj.price_text == "$35"


def test_zero_price_is_unknown_not_free(parsed: list[ScrapedShow]) -> None:
    # The Bad Nerves offer carries price "0" — pricing not loaded, not free.
    bad_nerves = next(s for s in parsed if s.headliner_raw == "Bad Nerves")
    assert bad_nerves.price_text is None
    assert bad_nerves.ticket_url == "https://tixr.com/e/188547"


def test_source_url_is_events_page(parsed: list[ScrapedShow]) -> None:
    # Cards carry no per-show page; the listing page is the provenance.
    assert all(s.source_url == "https://guildtheatre.com/" for s in parsed)


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "guild_theatre"
    # The JSON-LD PerformingGroup always duplicates the event name, so no
    # distinct support acts are listed.
    assert show.support_raw == []
    assert show.price_text is not None
