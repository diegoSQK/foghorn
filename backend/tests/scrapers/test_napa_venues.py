"""Napa: the successor venue and the surviving series.

Blue Note Napa's club closed; 1030 Main St is now Napa Music Hall, and the
Blue Note name continues as a summer series at the Meritage. Two addresses,
two venue rows — and Napa Music Hall is two Ticketmaster rooms behind one row.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed
from foghorn.scrapers import (
    REGISTERED_SCRAPERS,
    blue_note_napa_summer_sessions,
    napa_music_hall,
)

FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "ticketmaster_fillmore_2026_07.json"
)
BATCH = [napa_music_hall, blue_note_napa_summer_sessions]


def test_both_are_registered_and_seeded(conn: sqlite3.Connection) -> None:
    seed(conn)
    for module in BATCH:
        assert REGISTERED_SCRAPERS.get(module.VENUE_SLUG) is module.scrape
        venue = venues_repo.get_by_slug(conn, module.VENUE_SLUG)
        assert venue is not None, f"{module.VENUE_SLUG} is not seeded"
        assert venue.region == "North Bay"


def test_they_are_separate_venues_at_separate_addresses(
    conn: sqlite3.Connection,
) -> None:
    # The whole point: folding the series under the old club name would file a
    # resort series 3.5 miles away at an address that no longer books music.
    seed(conn)
    hall = venues_repo.get_by_slug(conn, "napa_music_hall")
    series = venues_repo.get_by_slug(conn, "blue_note_napa_summer_sessions")
    assert hall is not None and series is not None
    assert hall.address is not None and "1030 Main" in hall.address
    assert series.address is not None and "Meritage" in series.address
    assert hall.id != series.id


def test_napa_music_hall_covers_two_rooms() -> None:
    ids = list(napa_music_hall.TM_ROOMS)
    assert len(set(ids)) == 2, "main hall + The Club"
    # The main hall carries no room label — repeating the venue name on every
    # card is noise; only the second room needs distinguishing.
    assert sorted(napa_music_hall.TM_ROOMS.values(), key=lambda v: (v is not None, v)) == [
        None,
        "The Club",
    ]


def test_each_room_stamps_its_own_label() -> None:
    payload: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))

    with patch.object(napa_music_hall, "fetch_events", return_value=payload):
        shows = napa_music_hall.scrape(today=dt.date(2026, 7, 1))

    assert shows, "shared fixture should yield shows"
    assert {s.venue_slug for s in shows} == {"napa_music_hall"}
    # Same payload for both ids, so every show appears once per room —
    # which is exactly what proves the label is applied per fetch.
    rooms = {s.room for s in shows}
    assert rooms == {None, "The Club"}
    assert shows == sorted(shows, key=lambda s: (s.start_local, s.headliner_raw))


def test_series_venue_id_is_the_one_with_inventory() -> None:
    # Discovery has four "Blue Note Napa" records; only this one sells. The
    # club's record returns zero, and the club itself has closed.
    assert blue_note_napa_summer_sessions.TM_VENUE_ID == "KovZ917AmJ7"
    assert blue_note_napa_summer_sessions.TM_VENUE_ID not in napa_music_hall.TM_ROOMS
