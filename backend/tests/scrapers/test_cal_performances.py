"""Tests for the Cal Performances season-listing parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today``.
The fixture is a trimmed snapshot of the live 2026–27 season page (the
``/calendar/`` redirect target): per-production ``event-filter-item`` blocks
whose inline schema.org JSON-LD carries one Event per performance in the
site's ``MM/DD/YYYYTHH:MM`` format. It covers a multi-date Dance run and a
Theater run (genre-dropped), single-performance keeps at Zellerbach and
Hertz, a multi-performance Family run (kept — conservative filter), a
"Jazz, Seasonal Holidays" double badge, a season-code-suffixed billing
string, and a Jan 2027 recital outside the September window.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import cal_performances

FIXTURE = Path(__file__).parent.parent / "fixtures" / "cal_performances_2026_27_season.html"
TODAY = dt.date(2026, 9, 20)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return cal_performances.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_with_genres(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw, s.genre) for s in parsed]
    assert got == [
        (
            "2026-09-27T15:00:00",
            # JSON-LD bills this as "… piano 2627" — season code stripped.
            "Lester Lynch, baritone; Kevin Korth, piano",
            "Recital",
        ),
        (
            "2026-10-11T15:00:00",
            "Takács Quartet with Jeremy Denk, piano",
            "Orchestra & Chamber Music",
        ),
        (
            "2026-10-18T15:00:00",
            "Judy Collins: Sweet Judy Blue Eyes: The Farewell Tour",
            "Vocal Celebration",
        ),
        (
            "2026-11-21T19:30:00",
            "Jason Moran and the Harlem Hellfighters: James Reese Europe and the Absence of Ruin",
            "Jazz",  # primary segment of the "Jazz, Illuminations: …" badge
        ),
        # One JSON-LD Event per performance: the two-day Family run expands.
        ("2026-11-28T14:00:00", "Cirque Kalabanté: WOW (World of Words)", "Family"),
        ("2026-11-29T15:00:00", "Cirque Kalabanté: WOW (World of Words)", "Family"),
        ("2026-12-17T19:30:00", "The Hot Sardines: Holiday Stomp", "Jazz"),
    ]


def test_dance_and_theater_dropped(parsed: list[ScrapedShow]) -> None:
    # Both runs sit inside the window (Sep 25–27 / Nov 12–15), so their
    # absence is the primary-genre filter, not the date filter.
    titles = {s.headliner_raw for s in parsed}
    assert not any("Australian Ballet" in t for t in titles)  # badge "Dance, …"
    assert len(parsed) == 7  # nothing from the Theater block either


def test_source_urls_and_optional_fields(parsed: list[ScrapedShow]) -> None:
    lynch = parsed[0]
    assert lynch.source_url == (
        "https://calperformances.org/events/2026-27/recital/"
        "lester-lynch-baritone-kevin-korth-piano-2627/"
    )
    assert lynch.venue_slug == "cal_performances"
    assert lynch.support_raw == []  # billing stays one combined string
    assert lynch.doors_local is None  # the listing states no doors times
    assert lynch.ticket_url is None  # ticketing sits behind detail pages
    assert lynch.price_text is None  # ... and no prices on the listing


def test_window_rolls_forward() -> None:
    # From Nov 1 the September/October dates fall behind `today` and the
    # Jan 17 recital (with its own "2627"-coded billing) comes into range.
    shows = cal_performances.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=dt.date(2026, 11, 1)
    )
    assert [s.headliner_raw for s in shows][-1] == "Lukas Sternath, piano"
    assert shows[-1].start_local == dt.datetime(2027, 1, 17, 15, 0)
