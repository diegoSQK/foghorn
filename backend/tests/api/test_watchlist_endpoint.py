"""Tests for the watchlist CRUD endpoints (Phase 4.1)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from foghorn.api import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "wl.db"))
    with TestClient(app) as test_client:
        yield test_client


def test_post_get_delete_roundtrip(client: TestClient) -> None:
    created = client.post("/api/watchlist", json={"display_name": "Joshua Redman Quartet"})
    assert created.status_code == 200
    body = created.json()
    assert body["canonical_name"] == "joshua redman quartet"
    assert body["display_name"] == "Joshua Redman Quartet"

    listed = client.get("/api/watchlist").json()
    assert [e["canonical_name"] for e in listed] == ["joshua redman quartet"]

    deleted = client.delete("/api/watchlist/" + quote("joshua redman quartet"))
    assert deleted.status_code == 204
    assert client.get("/api/watchlist").json() == []


def test_post_canonicalizes_display_name(client: TestClient) -> None:
    body = client.post("/api/watchlist", json={"display_name": "Café Tacvba"}).json()
    assert body["canonical_name"] == "cafe tacvba"
    assert body["display_name"] == "Café Tacvba"


def test_delete_missing_is_404(client: TestClient) -> None:
    assert client.delete("/api/watchlist/" + quote("not on list")).status_code == 404


def test_post_empty_name_rejected(client: TestClient) -> None:
    assert client.post("/api/watchlist", json={"display_name": "   "}).status_code == 422
    assert client.post("/api/watchlist", json={"display_name": "!!!"}).status_code == 422
