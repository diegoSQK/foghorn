"""Tests for ``GET /api/shows?watchlist=true`` (Phase 4.1)."""

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


def _show(venue_slug: str, headliner: str, start: dt.datetime) -> ScrapedShow:
    return ScrapedShow(
        venue_slug=venue_slug,
        headliner_raw=headliner,
        support_raw=[],
        start_local=start,
        source_url="https://example.com/show",
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "wlf.db"))
    conn = db.connect()
    seed(conn)
    bb = venues_repo.get_by_slug(conn, "bird_and_beckett")
    keys = venues_repo.get_by_slug(conn, "keys_jazz_bistro")
    assert bb is not None and keys is not None
    ingest_scraped_shows(
        conn,
        bb,
        [
            _show("bird_and_beckett", "Joshua Redman Quartet", dt.datetime(2026, 6, 5, 20, 0)),
            _show("bird_and_beckett", "Kamasi Washington", dt.datetime(2026, 6, 6, 20, 0)),
            _show("bird_and_beckett", "Some Other Band", dt.datetime(2026, 6, 7, 20, 0)),
        ],
    )
    ingest_scraped_shows(
        conn,
        keys,
        [_show("keys_jazz_bistro", "Joshua Redman Trio", dt.datetime(2026, 6, 8, 20, 0))],
    )
    watchlist_repo.add(conn, "Joshua Redman")  # token bag {joshua, redman}
    watchlist_repo.add(conn, "Kamasi Washington")
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def _names(rows: list[dict]) -> list[str]:
    return [r["headliner"]["display"] for r in rows]


def _wl(client: TestClient, **params: str) -> list[dict]:
    return client.get(
        "/api/shows",
        params={"from": "2026-06-01", "to": "2026-06-30", "watchlist": "true", **params},
    ).json()


def test_watchlist_filter_matches_any_entry(client: TestClient) -> None:
    # Both watched names match (across venues, token-based), in start order;
    # "Some Other Band" is excluded.
    assert _names(_wl(client)) == [
        "Joshua Redman Quartet",  # 06-05 (joshua + redman)
        "Kamasi Washington",  # 06-06
        "Joshua Redman Trio",  # 06-08 (joshua + redman, different venue)
    ]


def test_stacks_with_venue(client: TestClient) -> None:
    assert _names(_wl(client, venues="keys_jazz_bistro")) == ["Joshua Redman Trio"]


def test_stacks_with_date_window(client: TestClient) -> None:
    rows = client.get(
        "/api/shows",
        params={"from": "2026-06-06", "to": "2026-06-30", "watchlist": "true"},
    ).json()
    assert _names(rows) == ["Kamasi Washington", "Joshua Redman Trio"]


def test_empty_watchlist_returns_empty(client: TestClient) -> None:
    # Clear the watchlist, then the filter should surface nothing (not all shows).
    for entry in client.get("/api/watchlist").json():
        client.delete(f"/api/watchlist/{entry['canonical_name'].replace(' ', '%20')}")
    assert _wl(client) == []
    # Sanity: without the watchlist filter, shows are still there.
    unfiltered = client.get(
        "/api/shows", params={"from": "2026-06-01", "to": "2026-06-30"}
    ).json()
    assert len(unfiltered) == 4
