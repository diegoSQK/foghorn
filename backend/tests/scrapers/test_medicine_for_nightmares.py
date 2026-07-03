"""Tests for the Medicine for Nightmares Squarespace-JSON parser.

The fixture is a trimmed snapshot of the live ``/events?format=json``
collection: three "Other Dimensions in Sound" music-series entries (two with
the venue's own "Dimesnions" typo in the series prefix) interleaved with the
bookstore's non-music programming (chess club, printmaking workshop, author
evening, zine festival, poetry night, a benefit event), plus a far-future
copy for the window test.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import medicine_for_nightmares

FIXTURE = Path(__file__).parent.parent / "fixtures" / "medicine_for_nightmares_2026_07.json"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return medicine_for_nightmares.parse_events(payload, today=TODAY)


def test_keeps_only_the_music_series_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-03T19:00:00", "String, Skin & Breath /Bristle"),
        ("2026-07-10T19:00:00", "Free/Wong/Boyce"),
        ("2026-07-17T19:00:00", "Red Fast Luck"),
    ]


def test_series_prefix_stripped_even_with_venue_typo(parsed: list[ScrapedShow]) -> None:
    # Titles arrive as "Other Dimesnions in Sound; <act>" (sic) — the act is
    # the headliner, not the series branding.
    assert all("Dimensions" not in s.headliner_raw for s in parsed)
    assert all("Dimesnions" not in s.headliner_raw for s in parsed)


def test_non_music_programming_dropped(parsed: list[ScrapedShow]) -> None:
    kept = {s.headliner_raw for s in parsed}
    for title_fragment in ("Chess", "Workshop", "Zine", "Axolotl"):
        assert not any(title_fragment in name for name in kept)


def test_out_of_window_excluded(parsed: list[ScrapedShow]) -> None:
    assert not any(s.headliner_raw == "Out Of Window Ensemble" for s in parsed)


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    assert all(
        s.source_url.startswith("https://medicinefornightmares.com/events/")
        for s in parsed
    )


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "medicine_for_nightmares"
    assert show.support_raw == []
    assert show.doors_local is None
    assert show.ticket_url is None
    assert show.price_text is None
