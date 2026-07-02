"""Tests for ``?origin=`` on ``GET /api/shows`` and the manual-override
endpoint (``PUT /api/performers/{canonical}/origin``)."""

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
from foghorn.repo import performers as performers_repo
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "api.db"))
    conn = db.connect()
    seed(conn)
    venue = venues_repo.get_by_slug(conn, "keys_jazz_bistro")
    assert venue is not None
    ingest_scraped_shows(
        conn,
        venue,
        [
            ScrapedShow(
                venue_slug="keys_jazz_bistro",
                headliner_raw="Touring Star",
                support_raw=["Local Opener"],
                start_local=dt.datetime(2026, 6, 6, 20, 0),
                source_url="https://example.com/a",
            ),
            ScrapedShow(
                venue_slug="keys_jazz_bistro",
                headliner_raw="Untagged Act",
                start_local=dt.datetime(2026, 6, 7, 20, 0),
                source_url="https://example.com/b",
            ),
        ],
    )
    performers_repo.set_origin(conn, "touring star", "touring", "manual")
    performers_repo.set_origin(conn, "local opener", "local", "manual")
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def _june(client: TestClient, **params: str) -> list[dict]:
    return client.get(
        "/api/shows", params={"from": "2026-06-01", "to": "2026-06-30", **params}
    ).json()


def test_origin_local_matches_any_performer_on_the_bill(client: TestClient) -> None:
    # The local opener makes the touring headliner's show match origin=local.
    rows = _june(client, origin="local")
    assert [r["headliner"]["display"] for r in rows] == ["Touring Star"]


def test_origin_touring_filters(client: TestClient) -> None:
    rows = _june(client, origin="touring")
    assert [r["headliner"]["display"] for r in rows] == ["Touring Star"]


def test_unknown_origin_value_is_ignored(client: TestClient) -> None:
    assert len(_june(client, origin="martian")) == 2


def test_performer_views_carry_origin(client: TestClient) -> None:
    row = next(r for r in _june(client) if r["headliner"]["display"] == "Touring Star")
    assert row["headliner"]["origin"] == "touring"
    assert row["support"][0]["origin"] == "local"
    untagged = next(r for r in _june(client) if r["headliner"]["display"] == "Untagged Act")
    assert untagged["headliner"]["origin"] is None


def test_manual_override_endpoint_roundtrip(client: TestClient) -> None:
    resp = client.put(
        "/api/performers/untagged act/origin", json={"origin": "local"}
    )
    assert resp.status_code == 200
    assert resp.json()["origin"] == "local"
    assert resp.json()["origin_source"] == "manual"
    assert len(_june(client, origin="local")) == 2  # now both shows match


def test_manual_override_unknown_performer_404s(client: TestClient) -> None:
    resp = client.put("/api/performers/nobody/origin", json={"origin": "local"})
    assert resp.status_code == 404


def test_manual_override_rejects_bad_origin(client: TestClient) -> None:
    resp = client.put(
        "/api/performers/untagged act/origin", json={"origin": "intergalactic"}
    )
    assert resp.status_code == 422
