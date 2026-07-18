"""Tests for the Make-Out Room (Weebly homepage posts) scraper, driven from
two real posts: Tue 7/21 (two events; multi-line billing; "7pm show"
override; trailing set list → support) and Sat 7/18 (promo prose after the
ranges must NOT become support)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from foghorn.scrapers import make_out_room

FIXTURE = Path(__file__).parent.parent / "fixtures" / "make_out_room_home.html"
TODAY = dt.date(2026, 7, 17)


def _shows() -> list:
    return make_out_room.parse_posts(FIXTURE.read_text(), TODAY)


def test_two_events_per_night_with_correct_starts() -> None:
    shows = _shows()
    tue = [s for s in shows if s.start_local.date() == dt.date(2026, 7, 21)]
    assert len(tue) == 2
    jazz, techno = tue
    # Multi-line billing joins; "7pm show" overrides the 6:30 range start.
    assert jazz.headliner_raw == "JAZZ at the MAKE OUT ROOM!"
    assert jazz.start_local.time() == dt.time(19, 0)
    assert jazz.doors_local is not None and jazz.doors_local.time() == dt.time(18, 0)
    assert jazz.price_text == "Free"
    assert techno.start_local.time() == dt.time(21, 30)


def test_set_list_players_become_support() -> None:
    jazz = next(
        s for s in _shows() if s.headliner_raw == "JAZZ at the MAKE OUT ROOM!"
    )
    assert "Lorin Benedict" in jazz.support_raw
    assert "Saki Minamimoto" in jazz.support_raw
    # Instrument credits and connectors don't leak in.
    assert all(not act.startswith("-") for act in jazz.support_raw)


def test_promo_prose_does_not_become_support() -> None:
    sat = [s for s in _shows() if s.start_local.date() == dt.date(2026, 7, 18)]
    assert sat  # both Saturday events parse
    assert all(not s.support_raw for s in sat)


def test_window_filter() -> None:
    assert make_out_room.parse_posts(FIXTURE.read_text(), dt.date(2026, 8, 1)) == []
