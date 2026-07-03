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
