"""Tests for ``GET /api/shows``.

Points the app at a tmp DB via ``FOGHORN_DB_PATH`` (read at connect time),
seeds + ingests a small deterministic set, then drives the endpoint with
``TestClient``. Assertions use explicit ``from``/``to`` so they don't depend on
the wall clock.
"""

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


def _show(headliner: str, start: dt.datetime, support: list[str] | None = None) -> ScrapedShow:
    return ScrapedShow(
        venue_slug="bird_and_beckett",
        headliner_raw=headliner,
        support_raw=support or [],
        start_local=start,
        source_url="https://birdbeckett.com/events/",
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "api.db"))
    conn = db.connect()
    seed(conn)
    venue = venues_repo.get_by_slug(conn, "bird_and_beckett")
    assert venue is not None
    ingest_scraped_shows(
        conn,
        venue,
        [
            _show("David Parker Sextet", dt.datetime(2026, 6, 5, 19, 30)),
            _show("Late Trio", dt.datetime(2026, 6, 5, 21, 30), support=["An Opener"]),
            _show("Later Act", dt.datetime(2026, 6, 20, 20, 0)),
        ],
    )
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def test_window_returns_all_and_orders_by_start(client: TestClient) -> None:
    resp = client.get("/api/shows", params={"from": "2026-06-01", "to": "2026-06-30"})
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["headliner"]["display"] for r in rows] == [
        "David Parker Sextet",  # 19:30
        "Late Trio",  # 21:30 same night -> later start_utc
        "Later Act",  # June 20
    ]


def test_response_shape(client: TestClient) -> None:
    rows = client.get(
        "/api/shows", params={"from": "2026-06-05", "to": "2026-06-05"}
    ).json()
    late = next(r for r in rows if r["headliner"]["display"] == "Late Trio")
    assert late["venue"]["slug"] == "bird_and_beckett"
    assert late["venue"]["region"] == "SF"
    assert late["headliner"]["canonical"] == "late trio"
    assert [s["display"] for s in late["support"]] == ["An Opener"]
    assert late["ticket_url"] is None
    assert late["start_local_time"] == "21:30"


def test_from_filter_excludes_earlier(client: TestClient) -> None:
    rows = client.get(
        "/api/shows", params={"from": "2026-06-06", "to": "2026-06-30"}
    ).json()
    assert [r["headliner"]["display"] for r in rows] == ["Later Act"]


def test_venue_filter(client: TestClient) -> None:
    # sfjazz is seeded but has no shows.
    rows = client.get("/api/shows", params={"venue": "sfjazz"}).json()
    assert rows == []


def test_default_window_returns_200(client: TestClient) -> None:
    # No params -> today..+30d. Clock-dependent contents, so just assert it works.
    resp = client.get("/api/shows")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
