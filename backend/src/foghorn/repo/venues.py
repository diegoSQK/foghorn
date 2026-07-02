"""Venue persistence primitives."""

from __future__ import annotations

import sqlite3

from foghorn.models import Venue

_COLUMNS = (
    "id, slug, name, neighborhood, region, address, tz, website_url, calendar_url, "
    "genre, source"
)


def _row_to_venue(row: sqlite3.Row) -> Venue:
    return Venue(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        neighborhood=row["neighborhood"],
        region=row["region"],
        address=row["address"],
        tz=row["tz"],
        website_url=row["website_url"],
        calendar_url=row["calendar_url"],
        genre=row["genre"],
        source=row["source"],
    )


def get_by_slug(conn: sqlite3.Connection, slug: str) -> Venue | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM venues WHERE slug = ?", (slug,)
    ).fetchone()
    return _row_to_venue(row) if row is not None else None


def list_all(conn: sqlite3.Connection) -> list[Venue]:
    rows = conn.execute(f"SELECT {_COLUMNS} FROM venues ORDER BY name").fetchall()
    return [_row_to_venue(row) for row in rows]


def upsert(conn: sqlite3.Connection, venue: Venue) -> Venue:
    """Insert or update a venue keyed on ``slug``. Returns the stored row
    (with ``id`` populated). Idempotent — re-upserting the same slug refreshes
    the mutable columns without creating a duplicate."""
    conn.execute(
        """
        INSERT INTO venues (slug, name, neighborhood, region, address, tz,
                            website_url, calendar_url, genre, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            name         = excluded.name,
            neighborhood = excluded.neighborhood,
            region       = excluded.region,
            address      = excluded.address,
            tz           = excluded.tz,
            website_url  = excluded.website_url,
            calendar_url = excluded.calendar_url,
            genre        = excluded.genre,
            source       = excluded.source
        """,
        (
            venue.slug,
            venue.name,
            venue.neighborhood,
            venue.region,
            venue.address,
            venue.tz,
            venue.website_url,
            venue.calendar_url,
            venue.genre,
            venue.source,
        ),
    )
    conn.commit()
    stored = get_by_slug(conn, venue.slug)
    assert stored is not None  # just inserted/updated
    return stored
