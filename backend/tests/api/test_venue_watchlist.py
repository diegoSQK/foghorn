"""Tests for the venue watchlist (Phase 9): CRUD + ?venue_watchlist= filter."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foghorn.api import app
from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow
from foghorn.repo import db
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "api.db"))
    conn = db.connect()
    seed(conn)
    for slug, headliner in (
        ("keys_jazz_bistro", "Keys Act"),
        ("the_back_room", "Back Room Act"),
        ("yoshis", "Yoshis Act"),
    ):
        venue = venues_repo.get_by_slug(conn, slug)
        assert venue is not None
        ingest_scraped_shows(
            conn,
            venue,
            [
                ScrapedShow(
                    venue_slug=slug,
                    headliner_raw=headliner,
                    start_local=dt.datetime(2026, 6, 10, 20, 0),
                    source_url="https://example.com/s",
                )
            ],
        )
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def _june(client: TestClient, **params: str) -> list[dict]:
    return client.get(
        "/api/shows", params={"from": "2026-06-01", "to": "2026-06-30", **params}
    ).json()


def test_crud_roundtrip(client: TestClient) -> None:
    assert client.get("/api/venues/watchlist").json() == []
    resp = client.post("/api/venues/watchlist", json={"venue_slug": "the_back_room"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "The Back Room"
    slugs = [e["venue_slug"] for e in client.get("/api/venues/watchlist").json()]
    assert slugs == ["the_back_room"]
    assert client.delete("/api/venues/watchlist/the_back_room").status_code == 204
    assert client.get("/api/venues/watchlist").json() == []


def test_unknown_venue_404s(client: TestClient) -> None:
    assert (
        client.post("/api/venues/watchlist", json={"venue_slug": "nowhere"}).status_code
        == 404
    )
    assert client.delete("/api/venues/watchlist/nowhere").status_code == 404


def test_filter_matches_only_watched_venues(client: TestClient) -> None:
    client.post("/api/venues/watchlist", json={"venue_slug": "keys_jazz_bistro"})
    client.post("/api/venues/watchlist", json={"venue_slug": "yoshis"})
    rows = _june(client, venue_watchlist="true")
    assert sorted(r["headliner"]["display"] for r in rows) == ["Keys Act", "Yoshis Act"]


def test_empty_venue_watchlist_matches_nothing(client: TestClient) -> None:
    assert _june(client, venue_watchlist="true") == []


def test_stacks_with_other_filters(client: TestClient) -> None:
    client.post("/api/venues/watchlist", json={"venue_slug": "keys_jazz_bistro"})
    client.post("/api/venues/watchlist", json={"venue_slug": "the_back_room"})
    rows = _june(client, venue_watchlist="true", region="East Bay")
    assert [r["headliner"]["display"] for r in rows] == ["Back Room Act"]
