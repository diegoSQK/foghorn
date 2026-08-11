"""Tests for the venue seed."""

from __future__ import annotations

import sqlite3

from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import SEED_VENUES, seed


def test_seed_persists_every_seed_venue(conn: sqlite3.Connection) -> None:
    seed(conn)
    slugs = {v.slug for v in venues_repo.list_all(conn)}
    assert slugs == {v.slug for v in SEED_VENUES}
    # The original Phase 2 four must never drop out of the seed.
    assert {"sfjazz", "keys_jazz_bistro", "bird_and_beckett", "mr_tipples"} <= slugs


def test_seed_is_idempotent(conn: sqlite3.Connection) -> None:
    seed(conn)
    seed(conn)
    assert len(venues_repo.list_all(conn)) == len(SEED_VENUES)


def test_the_mellow_seeds_both_rooms_separately(conn: sqlite3.Connection) -> None:
    # One venue's calendar, two rooms in different neighborhoods. Folding them
    # into one row would file Lakehouse Jazz under the Haight and make the
    # venue watchlist unable to pin one room without the other.
    seed(conn)
    haight = venues_repo.get_by_slug(conn, "the_mellow_haight")
    boathouse = venues_repo.get_by_slug(conn, "blue_heron_boathouse")
    assert haight is not None and boathouse is not None
    assert (haight.neighborhood, haight.region) == ("Haight", "SF")
    assert (boathouse.neighborhood, boathouse.region) == ("Golden Gate Park", "SF")
    assert haight.genre == boathouse.genre == "jazz"
