"""Tests for manual event entry (POST/DELETE /api/events)."""

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
    # One scraped show, to prove scraped rows are not deletable.
    venue = venues_repo.get_by_slug(conn, "keys_jazz_bistro")
    assert venue is not None
    ingest_scraped_shows(
        conn,
        venue,
        [
            ScrapedShow(
                venue_slug="keys_jazz_bistro",
                headliner_raw="Scraped Act",
                start_local=dt.datetime(2026, 6, 6, 20, 0),
                source_url="https://example.com/scraped",
            )
        ],
    )
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _session(client: TestClient, sign_in) -> None:
    """Every request in this module runs signed in as an admin."""
    sign_in(client, admin=True)



def _june(client: TestClient, **params: str) -> list[dict]:
    return client.get(
        "/api/shows", params={"from": "2026-06-01", "to": "2026-06-30", **params}
    ).json()


def test_create_at_existing_venue(client: TestClient) -> None:
    resp = client.post(
        "/api/events",
        json={
            "venue_slug": "keys_jazz_bistro",
            "headliner": "Friend's Band",
            "support": ["Opener Pal"],
            "date": "2026-06-10",
            "time": "20:00",
            "price_text": "$10",
        },
    )
    assert resp.status_code == 201
    row = next(r for r in _june(client) if r["headliner"]["display"] == "Friend's Band")
    assert row["source"] == "manual"
    assert row["support"][0]["display"] == "Opener Pal"
    assert row["price_text"] == "$10"


def test_create_with_new_manual_venue(client: TestClient) -> None:
    resp = client.post(
        "/api/events",
        json={
            "venue": {"name": "Secret Warehouse", "region": "East Bay"},
            "headliner": "House Show Trio",
            "date": "2026-06-12",
            "time": "19:30",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["venue_slug"] == "secret_warehouse"
    # The manual venue appears in /api/venues despite having no scraper…
    venues = {v["slug"]: v for v in client.get("/api/venues").json()}
    assert venues["secret_warehouse"]["region"] == "East Bay"
    # …and its show is filterable like any other.
    rows = _june(client, region="East Bay")
    assert [r["headliner"]["display"] for r in rows] == ["House Show Trio"]


def test_create_is_idempotent_on_natural_key(client: TestClient) -> None:
    body = {
        "venue_slug": "keys_jazz_bistro",
        "headliner": "Twice Entered",
        "date": "2026-06-15",
        "time": "21:00",
    }
    assert client.post("/api/events", json=body).status_code == 201
    assert client.post("/api/events", json=body).status_code == 201
    assert len([r for r in _june(client) if r["headliner"]["display"] == "Twice Entered"]) == 1


def test_delete_manual_event(client: TestClient) -> None:
    created = client.post(
        "/api/events",
        json={
            "venue_slug": "keys_jazz_bistro",
            "headliner": "Oops Wrong Date",
            "date": "2026-06-20",
            "time": "20:00",
        },
    ).json()
    resp = client.delete(f"/api/events/{created['id']}")
    assert resp.status_code == 204
    assert not any(
        r["headliner"]["display"] == "Oops Wrong Date" for r in _june(client)
    )


def test_scraped_shows_are_not_deletable(client: TestClient) -> None:
    scraped = next(r for r in _june(client) if r["headliner"]["display"] == "Scraped Act")
    resp = client.delete(f"/api/events/{scraped['id']}")
    assert resp.status_code == 403
    assert any(r["headliner"]["display"] == "Scraped Act" for r in _june(client))


def test_requires_exactly_one_venue_field(client: TestClient) -> None:
    base = {"headliner": "X", "date": "2026-06-10", "time": "20:00"}
    assert client.post("/api/events", json=base).status_code == 422
    both = {
        **base,
        "venue_slug": "keys_jazz_bistro",
        "venue": {"name": "Somewhere"},
    }
    assert client.post("/api/events", json=both).status_code == 422


def test_unknown_venue_slug_404s(client: TestClient) -> None:
    resp = client.post(
        "/api/events",
        json={
            "venue_slug": "nowhere",
            "headliner": "X",
            "date": "2026-06-10",
            "time": "20:00",
        },
    )
    assert resp.status_code == 404
