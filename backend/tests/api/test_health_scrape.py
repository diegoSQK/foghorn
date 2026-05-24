"""Tests for ``GET /api/health/scrape``."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foghorn.api import app
from foghorn.models import ScrapeRun, ScrapeRunVenue
from foghorn.repo import db
from foghorn.repo import scrape_runs as scrape_runs_repo


def _seed_run(started: str, finished: str) -> ScrapeRun:
    return ScrapeRun(
        started_at=started,
        finished_at=finished,
        venues=[
            ScrapeRunVenue(
                venue_slug="bird_and_beckett",
                started_at=started,
                finished_at=finished,
                created=0,
                updated=12,
                errors=[],
            ),
            ScrapeRunVenue(
                venue_slug="keys_jazz_bistro",
                started_at=started,
                finished_at=finished,
                created=0,
                updated=0,
                errors=["timeout fetching calendar (httpx.ReadTimeout)"],
            ),
        ],
    )


def test_503_when_no_runs_yet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "h.db"))
    with TestClient(app) as client:
        resp = client.get("/api/health/scrape")
    assert resp.status_code == 503
    assert resp.json() == {"error": "no_scrape_runs_yet"}


def test_returns_latest_run_with_per_venue_breakdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "h.db"))
    conn = db.connect()
    scrape_runs_repo.record_run(conn, _seed_run("2026-05-23T04:00:00+00:00", "x"))
    scrape_runs_repo.record_run(
        conn, _seed_run("2026-05-24T04:00:00+00:00", "2026-05-24T04:01:43+00:00")
    )
    conn.close()

    with TestClient(app) as client:
        resp = client.get("/api/health/scrape")

    assert resp.status_code == 200
    body = resp.json()
    assert body["last_run_at"] == "2026-05-24T04:00:00+00:00"  # most recent run
    assert body["last_run_finished_at"] == "2026-05-24T04:01:43+00:00"
    by_slug = {v["slug"]: v for v in body["venues"]}
    assert by_slug["bird_and_beckett"]["updated"] == 12
    assert by_slug["bird_and_beckett"]["errors"] == []
    assert by_slug["keys_jazz_bistro"]["errors"] == [
        "timeout fetching calendar (httpx.ReadTimeout)"
    ]
