"""Tests for scrape-run trimming (bounded history)."""

from __future__ import annotations

import sqlite3

from foghorn.models import ScrapeRun, ScrapeRunVenue
from foghorn.repo import scrape_runs as scrape_runs_repo


def _run(tag: str) -> ScrapeRun:
    return ScrapeRun(
        started_at=tag,
        finished_at=tag,
        venues=[
            ScrapeRunVenue(
                venue_slug="bird_and_beckett",
                started_at=tag,
                finished_at=tag,
                created=1,
                updated=0,
                errors=[],
            )
        ],
    )


def test_insert_trims_to_keep_most_recent(conn: sqlite3.Connection) -> None:
    for i in range(1, 33):  # 32 runs, default keep=30
        scrape_runs_repo.record_run(conn, _run(f"run-{i:02d}"))
    assert scrape_runs_repo.count(conn) == 30

    latest = scrape_runs_repo.latest(conn)
    assert latest is not None
    assert latest.started_at == "run-32"  # newest survives

    oldest = conn.execute(
        "SELECT started_at FROM scrape_runs ORDER BY id LIMIT 1"
    ).fetchone()["started_at"]
    assert oldest == "run-03"  # run-01 / run-02 trimmed


def test_trim_removes_child_rows_no_orphans(conn: sqlite3.Connection) -> None:
    for i in range(5):
        scrape_runs_repo.record_run(conn, _run(str(i)), keep=1000)  # don't trim yet
    assert scrape_runs_repo.count(conn) == 5

    scrape_runs_repo.trim(conn, keep=2)
    assert scrape_runs_repo.count(conn) == 2
    orphans = conn.execute(
        "SELECT COUNT(*) FROM scrape_run_venues WHERE scrape_run_id NOT IN "
        "(SELECT id FROM scrape_runs)"
    ).fetchone()[0]
    assert orphans == 0
