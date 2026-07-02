"""Tests for the Kilowatt Dice-API parser.

Fixture-driven and deterministic: ``parse_events`` takes an injected ``today``
so the 90-day window doesn't depend on the clock. The fixture
(``fixtures/kilowatt_2026_07.json``) is a trimmed snapshot of the live Dice
events API exercising the edge cases — two shows on one local day, a comma
bill with an Oxford-less "and" tail, a "w/" DJ-night bill, a co-bill left
unsplit, a free show, an event with no lineup (no doors), non-music entries
(karaoke, a World Cup watch party), and a far-future event excluded by the
window.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import kilowatt

FIXTURE = Path(__file__).parent.parent / "fixtures" / "kilowatt_2026_07.json"
TODAY = dt.date(2026, 7, 2)


def _events() -> list[dict[str, object]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    events: list[dict[str, object]] = payload["data"]
    return events


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return kilowatt.parse_events(_events(), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-02T19:00:00", "Head Stone"),
        ("2026-07-03T19:00:00", "La Sombra"),
        ("2026-07-03T22:00:00", "Dreamscape DJ Night"),  # same local day, later
        ("2026-07-09T21:00:00", "Twisterella"),
        ("2026-07-10T19:00:00", "Pearl Charles & Carson McHone"),
    ]


def test_comma_bill_split_into_support(parsed: list[ScrapedShow]) -> None:
    head_stone = next(s for s in parsed if s.headliner_raw == "Head Stone")
    assert head_stone.support_raw == ["Pussy Velour", "Fuzz Kit"]


def test_oxfordless_and_tail_split(parsed: list[ScrapedShow]) -> None:
    # "La Sombra, Touchy Feely and Clumsy Tungs" — the final comma segment
    # splits on " and ".
    la_sombra = next(s for s in parsed if s.headliner_raw == "La Sombra")
    assert la_sombra.support_raw == ["Touchy Feely", "Clumsy Tungs"]


def test_w_slash_bill_split(parsed: list[ScrapedShow]) -> None:
    # "Twisterella w/ DJs Galine, Liam and Matt"
    twisterella = next(s for s in parsed if s.headliner_raw == "Twisterella")
    assert twisterella.support_raw == ["DJs Galine", "Liam", "Matt"]


def test_ampersand_cobill_left_whole(parsed: list[ScrapedShow]) -> None:
    # No comma and no "w/": "&" may be part of a band name, so no split.
    pearl = next(s for s in parsed if "Pearl Charles" in s.headliner_raw)
    assert pearl.headliner_raw == "Pearl Charles & Carson McHone"
    assert pearl.support_raw == []


def test_non_music_events_dropped(parsed: list[ScrapedShow]) -> None:
    names = [s.headliner_raw for s in parsed]
    assert "KILOWATT KARAOKE" not in names
    assert not any("Watch Party" in name for name in names)


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # October 15 (local) is ~105 days past the pinned today (> 90-day window).
    assert not any(s.headliner_raw == "Out Of Window Wailers" for s in parsed)


def test_window_size_is_respected() -> None:
    # A 2-day window from today catches only the July 2–3 (local) shows.
    shows = kilowatt.parse_events(_events(), today=TODAY, window_days=2)
    assert [s.headliner_raw for s in shows] == [
        "Head Stone",
        "La Sombra",
        "Dreamscape DJ Night",
    ]


def test_doors_from_lineup(parsed: list[ScrapedShow]) -> None:
    head_stone = next(s for s in parsed if s.headliner_raw == "Head Stone")
    assert head_stone.doors_local == dt.datetime(2026, 7, 2, 19, 0)


def test_doors_none_without_lineup(parsed: list[ScrapedShow]) -> None:
    dreamscape = next(s for s in parsed if s.headliner_raw == "Dreamscape DJ Night")
    assert dreamscape.doors_local is None


def test_price_text_formatting(parsed: list[ScrapedShow]) -> None:
    head_stone = next(s for s in parsed if s.headliner_raw == "Head Stone")
    assert head_stone.price_text == "$13.39"  # 1339 cents, fees included
    la_sombra = next(s for s in parsed if s.headliner_raw == "La Sombra")
    assert la_sombra.price_text == "Free"  # all ticket types cost 0


def test_ticket_and_source_url_are_dice_event_link(parsed: list[ScrapedShow]) -> None:
    head_stone = next(s for s in parsed if s.headliner_raw == "Head Stone")
    assert head_stone.ticket_url == "https://link.dice.fm/Bd98dc7f3de3"
    assert head_stone.source_url == "https://link.dice.fm/Bd98dc7f3de3"


def test_venue_slug(parsed: list[ScrapedShow]) -> None:
    assert all(s.venue_slug == "kilowatt" for s in parsed)
