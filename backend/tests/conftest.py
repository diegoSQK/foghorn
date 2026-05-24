"""Shared test fixtures for the data layer."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from foghorn.models import Venue
from foghorn.repo import db
from foghorn.repo import venues as venues_repo


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A connection to a fresh, schema-initialized SQLite file per test."""
    connection = db.connect(tmp_path / "test.db")
    try:
        yield connection
    finally:
        connection.close()


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
