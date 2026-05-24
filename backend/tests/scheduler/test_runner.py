"""Tests for the scrape runner — the shared scheduler / make-scrape unit."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from foghorn.models import ScrapedShow, ShowFilters
from foghorn.repo import scrape_runs as scrape_runs_repo
from foghorn.repo import shows as shows_repo
from foghorn.scheduler.runner import run_scrape


def _ok_scraper() -> list[ScrapedShow]:
    return [
        ScrapedShow(
            venue_slug="bird_and_beckett",
            headliner_raw="Test Act",
            support_raw=[],
            start_local=datetime(2026, 6, 1, 20, 0),
            source_url="https://example.com/show",
        )
    ]


def _raising_scraper() -> list[ScrapedShow]:
    raise RuntimeError("boom")


def test_run_records_per_venue_results_and_isolates_failure(
    conn: sqlite3.Connection,
) -> None:
    # One scraper succeeds, one raises — the run must complete and capture both.
    run = run_scrape(
        conn,
        {"bird_and_beckett": _ok_scraper, "keys_jazz_bistro": _raising_scraper},
    )
    assert run.id is not None
    by_slug = {v.venue_slug: v for v in run.venues}
    assert set(by_slug) == {"bird_and_beckett", "keys_jazz_bistro"}

    good = by_slug["bird_and_beckett"]
    assert good.created == 1
    assert good.errors == []

    bad = by_slug["keys_jazz_bistro"]
    assert bad.created == 0
    assert any("boom" in e for e in bad.errors)  # exception captured, not raised


def test_run_persists_and_is_readable_as_latest(conn: sqlite3.Connection) -> None:
    run = run_scrape(conn, {"bird_and_beckett": _ok_scraper})
    latest = scrape_runs_repo.latest(conn)
    assert latest is not None
    assert latest.id == run.id
    assert [v.venue_slug for v in latest.venues] == ["bird_and_beckett"]
    # The successful scrape actually wrote a show.
    shows = shows_repo.list(conn, ShowFilters(venue_slugs=["bird_and_beckett"]))
    assert len(shows) == 1


def test_run_records_error_for_unseeded_venue(conn: sqlite3.Connection) -> None:
    run = run_scrape(conn, {"nope_not_a_venue": _ok_scraper})
    venue = run.venues[0]
    assert venue.created == 0
    assert any("no seeded venue" in e for e in venue.errors)
