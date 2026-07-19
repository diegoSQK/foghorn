"""Tests for the three shared-core Squarespace scrapers (Dawn Club,
Pier 23, Sound Room), driven from trimmed live collection payloads with
synthetic non-music rows appended. Covers: current-window parsing, stated
endDate pass-through, per-venue non-music filters (incl. rows that are
REAL in the live payloads — Mahjong, StorySlam, Illusion), and jam typing.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from foghorn.scrapers import pier_23_cafe, the_dawn_club, the_sound_room

FIXTURES = Path(__file__).parent.parent / "fixtures"
TODAY = dt.date(2026, 7, 18)


def _payload(name: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((FIXTURES / name).read_text())
    return data


def test_dawn_club_parses_and_drops_classes() -> None:
    shows = the_dawn_club.parse_items(_payload("dawn_club_2026_07.json"), TODAY)
    titles = [s.headliner_raw for s in shows]
    assert "Beginner Swing Class" not in titles
    assert len(shows) == 5
    trio = next(s for s in shows if s.headliner_raw == "Midnight blue organ trio")
    assert trio.start_local == dt.datetime(2026, 7, 20, 20, 0)
    assert trio.end_local == dt.datetime(2026, 7, 20, 23, 0)  # stated end


def test_pier_23_filters_mahjong_and_types_jams() -> None:
    shows = pier_23_cafe.parse_items(_payload("pier_23_2026_07.json"), TODAY)
    titles = [s.headliner_raw for s in shows]
    assert not any("MAHJONG" in t.upper() for t in titles)
    jam = next(s for s in shows if "BLUES JAM" in s.headliner_raw)
    assert jam.event_type == "jam"


def test_sound_room_filters_nonmusic_and_finds_tickets() -> None:
    shows = the_sound_room.parse_items(_payload("sound_room_2026_07.json"), TODAY)
    titles = [s.headliner_raw for s in shows]
    assert "An Evening of Illusion" not in titles
    assert "StorySlam Oakland" not in titles
    assert "Comedy Night Live" not in titles
    assert any(s.ticket_url and "eventbrite" in s.ticket_url for s in shows)
