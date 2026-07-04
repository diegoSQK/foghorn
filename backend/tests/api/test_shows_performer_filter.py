"""Tests for the ``?performer_query=`` filter on ``GET /api/shows`` (Phase 3.3).

Kept in its own file (not extending ``test_shows_endpoint.py``). As of Phase
4.1 the matching is **token-bag** (``repo.performer_match``), shared with the
watchlist — so reordered queries now match. These confirm the API wiring +
canonicalize-on-input behave.
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


def _show(
    venue_slug: str,
    headliner: str,
    start: dt.datetime,
    support: list[str] | None = None,
) -> ScrapedShow:
    return ScrapedShow(
        venue_slug=venue_slug,
        headliner_raw=headliner,
        support_raw=support or [],
        start_local=start,
        source_url="https://example.com/show",
    )


def _names(rows: list[dict]) -> list[str]:
    return [r["headliner"]["display"] for r in rows]


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "perf.db"))
    conn = db.connect()
    seed(conn)
    bb = venues_repo.get_by_slug(conn, "bird_and_beckett")
    keys = venues_repo.get_by_slug(conn, "keys_jazz_bistro")
    assert bb is not None and keys is not None
    ingest_scraped_shows(
        conn,
        bb,
        [
            _show(
                "bird_and_beckett",
                "Joshua Redman Quartet",
                dt.datetime(2026, 6, 5, 20, 0),
                ["Brian Blade"],
            ),
            _show("bird_and_beckett", "Café Tacvba", dt.datetime(2026, 6, 6, 20, 0)),
        ],
    )
    ingest_scraped_shows(
        conn,
        keys,
        [_show("keys_jazz_bistro", "Joshua Redman Trio", dt.datetime(2026, 6, 8, 20, 0))],
    )
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def _q(client: TestClient, **params: str) -> list[dict]:
    return client.get(
        "/api/shows", params={"from": "2026-06-01", "to": "2026-06-30", **params}
    ).json()


def test_reordered_query_matches_token_based(client: TestClient) -> None:
    # Token-bag (4.1): "redman joshua" matches "joshua redman quartet" even
    # though the old substring match (3.3) would have missed the reordering.
    assert _names(_q(client, performer_query="redman joshua")) == [
        "Joshua Redman Quartet",
        "Joshua Redman Trio",
    ]


def test_matches_headliner_across_venues(client: TestClient) -> None:
    # "joshua redman" tokens appear in both canonical headliners, ordered by start.
    assert _names(_q(client, performer_query="joshua redman")) == [
        "Joshua Redman Quartet",
        "Joshua Redman Trio",
    ]


def test_matches_support_performer(client: TestClient) -> None:
    assert _names(_q(client, performer_query="brian blade")) == ["Joshua Redman Quartet"]


def test_no_match_returns_empty(client: TestClient) -> None:
    assert _q(client, performer_query="nobody in particular") == []


def test_empty_or_punctuation_query_does_not_filter(client: TestClient) -> None:
    assert len(_q(client)) == 3  # baseline: no param
    assert len(_q(client, performer_query="")) == 3
    assert len(_q(client, performer_query="   ")) == 3
    assert len(_q(client, performer_query="!!!")) == 3  # canonicalizes to ""


def test_accent_insensitive(client: TestClient) -> None:
    # Query without the accent matches the accented performer (NFKD strip).
    assert _names(_q(client, performer_query="cafe tacvba")) == ["Café Tacvba"]
    # And the accented spelling canonicalizes to the same thing.
    assert _names(_q(client, performer_query="Café Tacvba")) == ["Café Tacvba"]


def test_stacks_with_venue_filter(client: TestClient) -> None:
    rows = _q(client, performer_query="joshua redman", venues="keys_jazz_bistro")
    assert _names(rows) == ["Joshua Redman Trio"]


def test_stacks_with_date_window(client: TestClient) -> None:
    rows = client.get(
        "/api/shows",
        params={"from": "2026-06-07", "to": "2026-06-30", "performer_query": "joshua redman"},
    ).json()
    assert _names(rows) == ["Joshua Redman Trio"]  # excludes the June 5 B&B show


def test_search_matches_token_prefix(client: TestClient) -> None:
    # Search-as-you-type: a partial word matches as a token prefix…
    assert _names(_q(client, performer_query="redm")) == [
        "Joshua Redman Quartet",
        "Joshua Redman Trio",
    ]
    # …but only a *prefix* — mid-token fragments still don't match.
    assert _q(client, performer_query="edman") == []
