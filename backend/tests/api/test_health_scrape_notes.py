"""Deliberate drops reach ``GET /api/health/scrape`` (#129).

A run can succeed and still lose a show on purpose. Errors don't cover that,
so notes ride alongside them — the point being that a drop with no telemetry
is how a Julian Lage date went missing without anyone noticing.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foghorn.api import app
from foghorn.models import ScrapeRun, ScrapeRunVenue
from foghorn.repo import db
from foghorn.repo import scrape_runs as scrape_runs_repo

STARTED = "2026-09-18T04:00:00+00:00"
FINISHED = "2026-09-18T04:01:43+00:00"
NOTE = (
    "4 off-site date(s) not ingested: davies_symphony_hall 2, grace_cathedral 1, "
    "paramount_theatre_oakland 1; no scraper covers grace_cathedral 1"
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "health.db"))
    conn = db.connect()
    scrape_runs_repo.record_run(
        conn,
        ScrapeRun(
            started_at=STARTED,
            finished_at=FINISHED,
            venues=[
                ScrapeRunVenue(
                    venue_slug="sfjazz",
                    started_at=STARTED,
                    finished_at=FINISHED,
                    created=3,
                    updated=44,
                    errors=[],
                    notes=[NOTE],
                ),
                ScrapeRunVenue(
                    venue_slug="bird_and_beckett",
                    started_at=STARTED,
                    finished_at=FINISHED,
                    created=0,
                    updated=12,
                    errors=[],
                ),
            ],
        ),
    )
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def _venue(client: TestClient, slug: str) -> dict:
    body = client.get("/api/health/scrape").json()
    return next(v for v in body["venues"] if v["slug"] == slug)


def test_notes_are_reported(client: TestClient) -> None:
    sfjazz = _venue(client, "sfjazz")
    assert sfjazz["notes"] == [NOTE]


def test_drops_are_broken_down_by_host(client: TestClient) -> None:
    note = _venue(client, "sfjazz")["notes"][0]
    for host in (
        "davies_symphony_hall 2",
        "grace_cathedral 1",
        "paramount_theatre_oakland 1",
    ):
        assert host in note


def test_scraperless_hosts_are_distinguishable(client: TestClient) -> None:
    """The Paramount's off-site dates are picked up by its own scraper;
    Grace Cathedral's are simply lost. The surface has to say which."""
    note = _venue(client, "sfjazz")["notes"][0]
    lost = note.split("no scraper covers", 1)[1]
    assert "grace_cathedral" in lost
    assert "paramount_theatre_oakland" not in lost


def test_notes_are_not_errors(client: TestClient) -> None:
    """A deliberate drop must not make the venue look broken."""
    assert _venue(client, "sfjazz")["errors"] == []


def test_a_venue_with_nothing_to_report_has_empty_notes(
    client: TestClient,
) -> None:
    assert _venue(client, "bird_and_beckett")["notes"] == []


def test_notes_survive_the_round_trip_through_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "roundtrip.db"))
    conn = db.connect()
    scrape_runs_repo.record_run(
        conn,
        ScrapeRun(
            started_at=STARTED,
            finished_at=FINISHED,
            venues=[
                ScrapeRunVenue(
                    venue_slug="sfjazz",
                    started_at=STARTED,
                    finished_at=FINISHED,
                    notes=["a", "b"],
                )
            ],
        ),
    )
    latest = scrape_runs_repo.latest(conn)
    conn.close()
    assert latest is not None
    assert latest.venues[0].notes == ["a", "b"]
