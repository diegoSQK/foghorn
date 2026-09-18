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
            aggregators={},
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
    run = run_scrape(conn, {"bird_and_beckett": _ok_scraper}, aggregators={})
    latest = scrape_runs_repo.latest(conn)
    assert latest is not None
    assert latest.id == run.id
    assert [v.venue_slug for v in latest.venues] == ["bird_and_beckett"]
    # The successful scrape actually wrote a show.
    shows = shows_repo.list(conn, ShowFilters(venue_slugs=["bird_and_beckett"]))
    assert len(shows) == 1


def _unseeded_venue_scraper() -> list[ScrapedShow]:
    return [
        ScrapedShow(
            venue_slug="nope_not_a_venue",
            headliner_raw="Some Act",
            support_raw=[],
            start_local=datetime(2026, 6, 1, 20, 0),
            source_url="https://example.com/show",
        )
    ]


def test_run_records_error_for_unseeded_venue(conn: sqlite3.Connection) -> None:
    """Since #130 a scraper's output is grouped by the venue each show names,
    so the misconfiguration worth catching is a *show* naming a venue that
    isn't seeded — not a registry key that isn't a venue slug, which is now
    legitimate for a scraper covering several rooms."""
    run = run_scrape(conn, {"some_scraper": _unseeded_venue_scraper}, aggregators={})
    venue = run.venues[0]
    assert venue.created == 0
    assert any("no seeded venue" in e for e in venue.errors)


def test_a_scraper_may_be_registered_under_a_non_venue_id(
    conn: sqlite3.Connection,
) -> None:
    """The registry key is a scraper identity now, not necessarily a venue —
    that decoupling is what lets one scraper cover rooms it doesn't own."""
    run = run_scrape(conn, {"a_presenter_feed": _ok_scraper}, aggregators={})
    assert run.venues[0].errors == []
    assert run.venues[0].created == 1
    shows = shows_repo.list(conn, ShowFilters(venue_slugs=["bird_and_beckett"]))
    assert len(shows) == 1
    assert shows[0].source_scraper == "a_presenter_feed"
