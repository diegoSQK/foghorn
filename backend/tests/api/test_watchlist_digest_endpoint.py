"""Tests for ``GET /api/watchlist/digest`` (Phase 4.2).

The digest uses the real ``date.today()`` (no from/to params), so the fixture
ingests shows at offsets from today — clock-independent, unlike the param-driven
endpoint tests.
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
from foghorn.repo import watchlist as watchlist_repo
from foghorn.repo.seed_venues import seed

TODAY = dt.date.today()


def _show(headliner: str, day_offset: int, support: list[str] | None = None) -> ScrapedShow:
    start = dt.datetime.combine(TODAY + dt.timedelta(days=day_offset), dt.time(20, 0))
    return ScrapedShow(
        venue_slug="bird_and_beckett",
        headliner_raw=headliner,
        support_raw=support or [],
        start_local=start,
        source_url="https://example.com/show",
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "digest.db"))
    conn = db.connect()
    seed(conn)
    bb = venues_repo.get_by_slug(conn, "bird_and_beckett")
    assert bb is not None
    ingest_scraped_shows(
        conn,
        bb,
        [
            _show("Joshua Redman Quartet", 1),
            _show("Kamasi Washington", 2),
            _show("Some Other Band", 3),  # no watchlist match
            _show("Joshua Redman", 4, support=["Kamasi Washington"]),  # matches two
            _show("Far Future Act", 200),  # beyond the default 14-day window
        ],
    )
    for name in ["Joshua Redman", "Kamasi Washington", "Far Future Act"]:
        watchlist_repo.add(conn, name)
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def _names(matches: list[dict]) -> list[str]:
    return [m["headliner"]["display"] for m in matches]


def test_default_digest_filters_and_orders(client: TestClient) -> None:
    body = client.get("/api/watchlist/digest").json()
    assert "generated_at" in body
    # Ordered by start_utc; "Some Other Band" (no match) and "Far Future Act"
    # (beyond 14d) excluded.
    assert _names(body["matches"]) == [
        "Joshua Redman Quartet",
        "Kamasi Washington",
        "Joshua Redman",
    ]


def test_watchlist_matches_field(client: TestClient) -> None:
    matches = client.get("/api/watchlist/digest").json()["matches"]
    by_name = {m["headliner"]["display"]: m["watchlist_matches"] for m in matches}
    assert by_name["Joshua Redman Quartet"] == ["Joshua Redman"]
    assert by_name["Kamasi Washington"] == ["Kamasi Washington"]
    # The +4 show matches two watched names (headliner + support).
    assert sorted(by_name["Joshua Redman"]) == ["Joshua Redman", "Kamasi Washington"]


def test_days_widens_window(client: TestClient) -> None:
    assert "Far Future Act" not in _names(
        client.get("/api/watchlist/digest").json()["matches"]
    )
    wide = client.get("/api/watchlist/digest", params={"days": 365}).json()
    assert "Far Future Act" in _names(wide["matches"])


def test_limit_caps_results(client: TestClient) -> None:
    body = client.get("/api/watchlist/digest", params={"limit": 1}).json()
    assert len(body["matches"]) == 1
    assert body["matches"][0]["headliner"]["display"] == "Joshua Redman Quartet"


def test_empty_watchlist_returns_empty_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "empty.db"))
    with TestClient(app) as test_client:
        body = test_client.get("/api/watchlist/digest").json()
    assert body["matches"] == []
    assert "generated_at" in body


def test_no_upcoming_matches_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "nomatch.db"))
    conn = db.connect()
    seed(conn)
    watchlist_repo.add(conn, "Nobody In The Calendar")
    conn.close()
    with TestClient(app) as test_client:
        assert test_client.get("/api/watchlist/digest").json()["matches"] == []
