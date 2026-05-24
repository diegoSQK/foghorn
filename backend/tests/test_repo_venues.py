"""Tests for the venues repository."""

from __future__ import annotations

import sqlite3

from foghorn.models import Venue
from foghorn.repo import venues as venues_repo


def _venue(slug: str = "sfjazz", name: str = "SFJAZZ Center") -> Venue:
    return Venue(
        slug=slug,
        name=name,
        neighborhood="Hayes Valley",
        region="SF",
        address="201 Franklin St, San Francisco, CA",
        tz="America/Los_Angeles",
        calendar_url="https://www.sfjazz.org/tickets/",
    )


def test_upsert_assigns_id_and_get_by_slug(conn: sqlite3.Connection) -> None:
    stored = venues_repo.upsert(conn, _venue())
    assert stored.id is not None

    fetched = venues_repo.get_by_slug(conn, "sfjazz")
    assert fetched is not None
    assert fetched.id == stored.id
    assert fetched.name == "SFJAZZ Center"
    assert fetched.region == "SF"


def test_get_by_slug_missing_returns_none(conn: sqlite3.Connection) -> None:
    assert venues_repo.get_by_slug(conn, "nope") is None


def test_upsert_is_idempotent_on_slug(conn: sqlite3.Connection) -> None:
    first = venues_repo.upsert(conn, _venue())
    second = venues_repo.upsert(conn, _venue(name="SFJAZZ (renamed)"))
    assert first.id == second.id  # same row, not a duplicate
    assert second.name == "SFJAZZ (renamed)"  # mutable column refreshed
    assert len(venues_repo.list_all(conn)) == 1


def test_list_all_orders_by_name(conn: sqlite3.Connection) -> None:
    venues_repo.upsert(conn, _venue(slug="zzz", name="Zingg"))
    venues_repo.upsert(conn, _venue(slug="aaa", name="Aardvark"))
    names = [v.name for v in venues_repo.list_all(conn)]
    assert names == ["Aardvark", "Zingg"]
