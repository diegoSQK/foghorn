"""Venue size tiers (#133).

Metadata only — deliberately no filter facet, because whether one earns a
place on an already-crowded filter bar is a decision to make *after* seeing
the distribution. So these tests pin the data and its surfaces, and
explicitly pin that nothing about querying shows changed.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foghorn.api import app
from foghorn.models import Venue
from foghorn.repo import db
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import SEED_VENUES, SIZE_TIERS, seed

TIERS = {"listening_room", "club", "theatre", "large"}


class TestTheTable:
    def test_every_seeded_venue_is_tiered(self) -> None:
        """The guard that matters: a venue added without a tier fails the gate
        rather than silently landing untiered."""
        untiered = sorted(v.slug for v in SEED_VENUES if v.size_tier is None)
        assert untiered == []

    def test_no_tier_outlives_its_venue(self) -> None:
        seeded = {v.slug for v in SEED_VENUES}
        assert sorted(set(SIZE_TIERS) - seeded) == []

    def test_tiers_are_from_the_vocabulary(self) -> None:
        assert set(SIZE_TIERS.values()) <= TIERS

    def test_all_four_tiers_are_used(self) -> None:
        assert set(SIZE_TIERS.values()) == TIERS

    @pytest.mark.parametrize(
        "slug,tier",
        [
            ("bird_and_beckett", "listening_room"),
            ("audium", "listening_room"),
            ("bottom_of_the_hill", "club"),
            ("keys_jazz_bistro", "club"),
            ("the_fillmore", "theatre"),
            ("davies_symphony_hall", "theatre"),
            ("bill_graham_civic", "large"),
            ("greek_theatre_berkeley", "large"),
        ],
    )
    def test_the_tickets_anchors(self, slug: str, tier: str) -> None:
        assert SIZE_TIERS[slug] == tier


class TestPersistence:
    def test_round_trips(self, conn: sqlite3.Connection) -> None:
        seed(conn)
        venue = venues_repo.get_by_slug(conn, "bill_graham_civic")
        assert venue is not None
        assert venue.size_tier == "large"

    def test_reseeding_converges(self, conn: sqlite3.Connection) -> None:
        seed(conn)
        before = len(venues_repo.list_all(conn))
        seed(conn)
        after = venues_repo.list_all(conn)
        assert len(after) == before
        assert all(v.size_tier is not None for v in after if v.source == "seed")

    def test_an_aggregator_venue_stays_untiered(
        self, conn: sqlite3.Connection
    ) -> None:
        """Inventing metadata for ~50 auto-discovered spaces would be
        guesswork — the same reason they carry no region or genre."""
        venues_repo.upsert(
            conn,
            Venue(
                slug="some_discovered_space",
                name="Some Discovered Space",
                neighborhood=None,
                region=None,
                address=None,
                tz="America/Los_Angeles",
                website_url=None,
                calendar_url="https://example.test/",
                genre=None,
                source="aggregator",
            ),
        )
        seed(conn)
        found = venues_repo.get_by_slug(conn, "some_discovered_space")
        assert found is not None
        assert found.size_tier is None
        assert found.source == "aggregator"

    def test_migration_is_idempotent(self, tmp_path: Path) -> None:
        """init_schema runs at every connect()."""
        path = tmp_path / "migrate.db"
        conn = db.connect(path)
        seed(conn)
        before = len(venues_repo.list_all(conn))
        conn.close()

        reopened = db.connect(path)
        after = venues_repo.list_all(reopened)
        tier = venues_repo.get_by_slug(reopened, "bird_and_beckett")
        reopened.close()
        assert len(after) == before
        assert tier is not None and tier.size_tier == "listening_room"


class TestSurfaces:
    @pytest.fixture
    def client(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Iterator[TestClient]:
        monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "api.db"))
        conn = db.connect()
        seed(conn)
        conn.close()
        with TestClient(app) as test_client:
            yield test_client

    def test_api_returns_the_tier(self, client: TestClient) -> None:
        venues = client.get("/api/venues").json()
        by_slug = {v["slug"]: v for v in venues}
        assert by_slug["bird_and_beckett"]["size_tier"] == "listening_room"

    def test_every_listed_seed_venue_has_one(self, client: TestClient) -> None:
        for venue in client.get("/api/venues").json():
            if venue["source"] == "seed":
                assert venue["size_tier"] in TIERS, venue["slug"]

    def test_mcp_list_venues_documents_the_tier(self) -> None:
        """The MCP tool returns the API row verbatim, so the field rides along
        — but the description has to name it or the model won't know to use
        it, which is the point of surfacing it at all."""
        import asyncio

        from foghorn.mcp.server import build_server

        tools = asyncio.run(build_server().list_tools())
        description = next(t for t in tools if t.name == "list_venues").description
        assert description is not None
        assert "size_tier" in description
        for tier in TIERS:
            assert tier in description


class TestNothingElseChanged:
    def test_shows_endpoint_has_no_size_parameter(self) -> None:
        """Explicitly out of scope: whether a size facet earns a place on the
        filter bar is a decision for after the distribution is visible."""
        import inspect

        from foghorn.api.shows import list_shows

        assert "size_tier" not in inspect.signature(list_shows).parameters
        assert "size" not in inspect.signature(list_shows).parameters
