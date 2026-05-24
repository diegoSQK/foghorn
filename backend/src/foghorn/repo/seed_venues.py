"""Seed the four Phase 2 jazz venues.

Idempotent by construction: ``venues.upsert`` keys on ``slug``, so calling
``seed`` repeatedly converges to exactly these rows without duplicating. The
``calendar_url`` for each venue is a placeholder until its Phase 2.x scraper
ticket discovers and sets the real one.

Runnable standalone: ``python -m foghorn.repo.seed_venues`` seeds the default DB.
"""

from __future__ import annotations

import sqlite3

from foghorn.models import Venue
from foghorn.repo import db
from foghorn.repo import venues as venues_repo

_TBD = "TBD"  # set by each venue's Phase 2.x scraper ticket

SEED_VENUES: list[Venue] = [
    Venue(
        slug="sfjazz",
        name="SFJAZZ Center",
        neighborhood="Hayes Valley",
        region="SF",
        address="201 Franklin St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.sfjazz.org",
        calendar_url=_TBD,
    ),
    Venue(
        slug="keys_jazz_bistro",
        name="Keys Jazz Bistro",
        neighborhood="North Beach",
        region="SF",
        address="530 Broadway, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.keysjazzbistro.com",
        calendar_url=_TBD,
    ),
    Venue(
        slug="bird_and_beckett",
        name="Bird & Beckett Books and Records",
        neighborhood="Glen Park",
        region="SF",
        address="653 Chenery St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.birdbeckett.com",
        calendar_url=_TBD,
    ),
    Venue(
        slug="mr_tipples",
        name="Mr. Tipple's Recording Studio",
        neighborhood="Hayes Valley",
        region="SF",
        address="39 Fell St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.mrtipples.com",
        calendar_url=_TBD,
    ),
]


def seed(conn: sqlite3.Connection | None = None) -> None:
    """Upsert the seed venues. Opens the default DB if no connection is given
    (and closes it again); pass a connection in tests to reuse it."""
    own_conn = conn is None
    if conn is None:
        conn = db.connect()
    try:
        for venue in SEED_VENUES:
            venues_repo.upsert(conn, venue)
    finally:
        if own_conn:
            conn.close()


if __name__ == "__main__":
    seed()
