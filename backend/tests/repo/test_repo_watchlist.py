"""Tests for the watchlist repository (Phase 4.1)."""

from __future__ import annotations

import sqlite3

from foghorn.repo import watchlist as watchlist_repo


def test_add_canonicalizes_and_keeps_display(conn: sqlite3.Connection) -> None:
    entry = watchlist_repo.add(conn, "Joshua Redman Quartet")
    assert entry.canonical_name == "joshua redman quartet"
    assert entry.display_name == "Joshua Redman Quartet"
    assert entry.notes is None


def test_add_twice_same_canonical_is_idempotent(conn: sqlite3.Connection) -> None:
    watchlist_repo.add(conn, "Joshua Redman Quartet")
    watchlist_repo.add(conn, "joshua redman quartet!!")  # same canonical form
    assert len(watchlist_repo.list_all(conn)) == 1


def test_readd_preserves_display_updates_notes(conn: sqlite3.Connection) -> None:
    watchlist_repo.add(conn, "Joshua Redman Quartet")
    entry = watchlist_repo.add(conn, "JOSHUA REDMAN QUARTET", notes="seen them live")
    assert entry.display_name == "Joshua Redman Quartet"  # original, not overwritten
    assert entry.notes == "seen them live"


def test_remove(conn: sqlite3.Connection) -> None:
    watchlist_repo.add(conn, "Kamasi Washington")
    assert watchlist_repo.remove(conn, "kamasi washington") is True
    assert watchlist_repo.remove(conn, "kamasi washington") is False  # already gone
    assert watchlist_repo.list_all(conn) == []


def test_list_all_newest_first(conn: sqlite3.Connection) -> None:
    # Explicit added_at so ordering is deterministic (real adds use now()).
    conn.execute(
        "INSERT INTO watchlist VALUES (?, ?, ?, ?)",
        ("older", "Older", "2026-01-01T00:00:00+00:00", None),
    )
    conn.execute(
        "INSERT INTO watchlist VALUES (?, ?, ?, ?)",
        ("newer", "Newer", "2026-02-01T00:00:00+00:00", None),
    )
    conn.commit()
    assert [e.canonical_name for e in watchlist_repo.list_all(conn)] == ["newer", "older"]
