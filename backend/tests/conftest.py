"""Shared test fixtures for the data layer."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from foghorn.models import User, Venue
from foghorn.repo import db
from foghorn.repo import sessions as sessions_repo
from foghorn.repo import users as users_repo
from foghorn.repo import venues as venues_repo

# Never spin up the background scheduler under pytest (no orphan threads / cron
# jobs firing mid-test). Set before any TestClient triggers the app lifespan.
os.environ.setdefault("FOGHORN_DISABLE_SCHEDULER", "1")


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A connection to a fresh, schema-initialized SQLite file per test."""
    connection = db.connect(tmp_path / "test.db")
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def user(conn: sqlite3.Connection) -> User:
    """A claimed, persisted user for per-user data-layer tests."""
    created = users_repo.create_invite(conn, "Test User")
    assert created.id is not None
    return users_repo.claim(conn, created.id)


@pytest.fixture
def sign_in():  # type: ignore[no-untyped-def]
    """A helper that creates a user + session in the API test DB (via
    FOGHORN_DB_PATH, which the caller's client fixture must have set) and
    attaches the session cookie to the TestClient. Returns the user.

    Usage: ``user = sign_in(client)`` / ``sign_in(client, admin=True)``.
    """
    from foghorn.api.auth import SESSION_COOKIE

    def _sign_in(client, *, admin: bool = False, display_name: str = "Test User") -> User:  # type: ignore[no-untyped-def]
        connection = db.connect()
        try:
            created = users_repo.create_invite(connection, display_name, is_admin=admin)
            assert created.id is not None
            signed_in = users_repo.claim(connection, created.id)
            token = sessions_repo.create(connection, created.id)
        finally:
            connection.close()
        client.cookies.set(SESSION_COOKIE, token)
        return signed_in

    return _sign_in


@pytest.fixture
def venue(conn: sqlite3.Connection) -> Venue:
    """A persisted SFJAZZ venue (with ``id`` populated) for ingest/show tests."""
    return venues_repo.upsert(
        conn,
        Venue(
            slug="sfjazz",
            name="SFJAZZ Center",
            neighborhood="Hayes Valley",
            region="SF",
            address="201 Franklin St, San Francisco, CA",
            tz="America/Los_Angeles",
            website_url="https://www.sfjazz.org",
            calendar_url="https://www.sfjazz.org/tickets/",
        ),
    )
