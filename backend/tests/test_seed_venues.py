"""Tests for the venue seed."""

from __future__ import annotations

import sqlite3

from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed


def test_seed_populates_the_four_venues(conn: sqlite3.Connection) -> None:
    seed(conn)
    slugs = {v.slug for v in venues_repo.list_all(conn)}
    assert slugs == {"sfjazz", "keys_jazz_bistro", "bird_and_beckett", "mr_tipples"}


def test_seed_is_idempotent(conn: sqlite3.Connection) -> None:
    seed(conn)
    seed(conn)
    assert len(venues_repo.list_all(conn)) == 4
