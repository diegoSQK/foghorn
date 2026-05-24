"""Tests for ``GET /api/venues``."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foghorn.api import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "venues.db"))
    with TestClient(app) as test_client:  # lifespan seeds the venues
        yield test_client


def test_lists_only_scraped_venues(client: TestClient) -> None:
    resp = client.get("/api/venues")
    assert resp.status_code == 200
    slugs = [v["slug"] for v in resp.json()]
    # The three venues with scrapers — not deferred/unscraped SFJAZZ.
    assert slugs == ["bird_and_beckett", "keys_jazz_bistro", "mr_tipples"]


def test_venue_shape(client: TestClient) -> None:
    bb = next(v for v in client.get("/api/venues").json() if v["slug"] == "bird_and_beckett")
    assert bb["name"] == "Bird & Beckett Books and Records"
    assert bb["neighborhood"] == "Glen Park"
    assert bb["region"] == "SF"
