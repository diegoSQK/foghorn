"""Tests for ``GET /api/venues``."""

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
from foghorn.repo.seed_venues import SEED_VENUES
from foghorn.scrapers import REGISTERED_SCRAPERS


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "venues.db"))
    with TestClient(app) as test_client:  # lifespan seeds the venues
        yield test_client


def test_lists_only_scraped_venues(client: TestClient) -> None:
    resp = client.get("/api/venues")
    assert resp.status_code == 200
    slugs = [v["slug"] for v in resp.json()]
    # Every seeded venue with a registered scraper — and nothing else while
    # the DB carries no shows: seeded-but-dormant venues (SFJAZZ) and still
    # -empty group-feed halls (Davies, Herbst, the Wilsey Atrium) both wait
    # until they have data.
    expected = sorted(v.slug for v in SEED_VENUES if v.slug in REGISTERED_SCRAPERS)
    assert sorted(slugs) == expected
    assert "sfjazz" not in slugs


def test_group_fed_hall_appears_once_it_has_shows(client: TestClient) -> None:
    # davies_symphony_hall is seeded but scraperless — its shows arrive via
    # the SF Symphony group feed. Hidden while empty, listed once fed.
    assert "davies_symphony_hall" not in [
        v["slug"] for v in client.get("/api/venues").json()
    ]
    conn = db.connect()
    venue = venues_repo.get_by_slug(conn, "davies_symphony_hall")
    assert venue is not None
    ingest_scraped_shows(
        conn,
        venue,
        [
            ScrapedShow(
                venue_slug="davies_symphony_hall",
                headliner_raw="Mahler 9",
                start_local=dt.datetime(2026, 9, 10, 19, 30),
                source_url="https://www.sfsymphony.org/x",
            )
        ],
        source="aggregator",
    )
    conn.close()
    venues = {v["slug"]: v for v in client.get("/api/venues").json()}
    assert venues["davies_symphony_hall"]["source"] == "seed"
    assert "sfjazz" not in venues  # still dormant, still excluded


def test_venue_shape(client: TestClient) -> None:
    bb = next(v for v in client.get("/api/venues").json() if v["slug"] == "bird_and_beckett")
    assert bb["name"] == "Bird & Beckett Books and Records"
    assert bb["neighborhood"] == "Glen Park"
    assert bb["region"] == "SF"
