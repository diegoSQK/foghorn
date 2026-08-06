"""Tests for the watchlist repository (Phase 4.1)."""

from __future__ import annotations

import sqlite3

from foghorn.models import User
from foghorn.repo import watchlist as watchlist_repo


def test_add_canonicalizes_and_keeps_display(conn: sqlite3.Connection, user: User) -> None:
    uid = user.id
    assert uid is not None
    entry = watchlist_repo.add(conn, uid, "Joshua Redman Quartet")
    assert entry.canonical_name == "joshua redman quartet"
    assert entry.display_name == "Joshua Redman Quartet"
    assert entry.notes is None


def test_add_twice_same_canonical_is_idempotent(conn: sqlite3.Connection, user: User) -> None:
    uid = user.id
    assert uid is not None
    watchlist_repo.add(conn, uid, "Joshua Redman Quartet")
    watchlist_repo.add(conn, uid, "joshua redman quartet!!")  # same canonical form
    assert len(watchlist_repo.list_all(conn, uid)) == 1


def test_readd_preserves_display_updates_notes(conn: sqlite3.Connection, user: User) -> None:
    uid = user.id
    assert uid is not None
    watchlist_repo.add(conn, uid, "Joshua Redman Quartet")
    entry = watchlist_repo.add(conn, uid, "JOSHUA REDMAN QUARTET", notes="seen them live")
    assert entry.display_name == "Joshua Redman Quartet"  # original, not overwritten
    assert entry.notes == "seen them live"


def test_remove(conn: sqlite3.Connection, user: User) -> None:
    uid = user.id
    assert uid is not None
    watchlist_repo.add(conn, uid, "Kamasi Washington")
    assert watchlist_repo.remove(conn, uid, "kamasi washington") is True
    assert watchlist_repo.remove(conn, uid, "kamasi washington") is False  # already gone
    assert watchlist_repo.list_all(conn, uid) == []


def test_list_all_newest_first(conn: sqlite3.Connection, user: User) -> None:
    uid = user.id
    assert uid is not None
    # Explicit added_at so ordering is deterministic (real adds use now()).
    conn.execute(
        "INSERT INTO watchlist VALUES (?, ?, ?, ?, ?)",
        (uid, "older", "Older", "2026-01-01T00:00:00+00:00", None),
    )
    conn.execute(
        "INSERT INTO watchlist VALUES (?, ?, ?, ?, ?)",
        (uid, "newer", "Newer", "2026-02-01T00:00:00+00:00", None),
    )
    conn.commit()
    assert [e.canonical_name for e in watchlist_repo.list_all(conn, uid)] == ["newer", "older"]
