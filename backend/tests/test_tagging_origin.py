"""Tests for the local/touring origin heuristic (Phase 7 tagging v1)."""

from __future__ import annotations

import datetime as dt
import sqlite3

from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow
from foghorn.repo import performers as performers_repo
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed
from foghorn.tagging.origin import apply_heuristic, compute_verdicts


def _ingest(
    conn: sqlite3.Connection,
    venue_slug: str,
    headliner: str,
    start: dt.datetime,
    *,
    support: list[str] | None = None,
    ticket_url: str | None = None,
) -> None:
    venue = venues_repo.get_by_slug(conn, venue_slug)
    assert venue is not None
    result = ingest_scraped_shows(
        conn,
        venue,
        [
            ScrapedShow(
                venue_slug=venue_slug,
                headliner_raw=headliner,
                support_raw=support or [],
                start_local=start,
                ticket_url=ticket_url,
                source_url="https://example.com/show",
            )
        ],
    )
    assert result.errors == []


def _origin(conn: sqlite3.Connection, canonical: str) -> str | None:
    performer = performers_repo.get_by_canonical(conn, canonical)
    assert performer is not None
    return performer.origin


def test_spread_recurrence_at_local_rooms_tags_local(conn: sqlite3.Connection) -> None:
    seed(conn)
    # Two dates a month apart at two local-leaning rooms: spread + multi-venue
    # + venue prior all fire.
    _ingest(conn, "keys_jazz_bistro", "Homegrown Trio", dt.datetime(2026, 7, 3, 20, 0))
    _ingest(conn, "madrone_art_bar", "Homegrown Trio", dt.datetime(2026, 8, 2, 21, 0))
    apply_heuristic(conn)
    assert _origin(conn, "homegrown trio") == "local"


def test_big_room_ticketmaster_headliner_tags_touring(conn: sqlite3.Connection) -> None:
    seed(conn)
    _ingest(
        conn,
        "fox_theater_oakland",
        "Arena Act",
        dt.datetime(2026, 7, 10, 20, 0),
        ticket_url="https://www.ticketmaster.com/event/123",
    )
    apply_heuristic(conn)
    assert _origin(conn, "arena act") == "touring"


def test_single_appearance_at_mixed_room_stays_unknown(conn: sqlite3.Connection) -> None:
    seed(conn)
    # One night at Yoshi's (no venue prior): not enough evidence either way.
    _ingest(conn, "yoshis", "Somebody Quartet", dt.datetime(2026, 7, 10, 19, 30))
    apply_heuristic(conn)
    assert _origin(conn, "somebody quartet") is None


def test_consecutive_night_run_is_not_spread_recurrence(conn: sqlite3.Connection) -> None:
    seed(conn)
    # A two-night touring run at a mixed room must not read as local recurrence.
    _ingest(conn, "yoshis", "Two Night Run", dt.datetime(2026, 7, 10, 19, 30))
    _ingest(conn, "yoshis", "Two Night Run", dt.datetime(2026, 7, 11, 19, 30))
    apply_heuristic(conn)
    assert _origin(conn, "two night run") is None


def test_manual_tag_survives_heuristic(conn: sqlite3.Connection) -> None:
    seed(conn)
    _ingest(
        conn,
        "fox_theater_oakland",
        "Actually A Local Big Act",
        dt.datetime(2026, 7, 10, 20, 0),
        ticket_url="https://www.ticketmaster.com/event/456",
    )
    performers_repo.set_origin(conn, "actually a local big act", "local", "manual")
    apply_heuristic(conn)
    assert _origin(conn, "actually a local big act") == "local"


def test_stale_heuristic_tag_clears_when_evidence_fades(conn: sqlite3.Connection) -> None:
    seed(conn)
    _ingest(conn, "keys_jazz_bistro", "Fading Act", dt.datetime(2026, 7, 3, 20, 0))
    _ingest(conn, "madrone_art_bar", "Fading Act", dt.datetime(2026, 8, 2, 21, 0))
    apply_heuristic(conn)
    assert _origin(conn, "fading act") == "local"
    # Simulate the evidence disappearing (shows dropped); the tag must clear
    # rather than fossilize.
    conn.execute("DELETE FROM show_performers")
    conn.execute("DELETE FROM shows")
    conn.commit()
    apply_heuristic(conn)
    assert _origin(conn, "fading act") == "local"  # no verdict at all -> untouched
    # But with one neutral appearance the verdict is unknown -> heuristic clears.
    _ingest(conn, "yoshis", "Fading Act", dt.datetime(2026, 9, 1, 19, 30))
    apply_heuristic(conn)
    assert _origin(conn, "fading act") is None


def test_verdict_scores_are_reported(conn: sqlite3.Connection) -> None:
    seed(conn)
    _ingest(conn, "keys_jazz_bistro", "Score Check", dt.datetime(2026, 7, 3, 20, 0))
    verdicts = {v.canonical_name: v for v in compute_verdicts(conn)}
    assert "score check" in verdicts
    # One local-room appearance = +1.0: below threshold, unknown.
    assert verdicts["score check"].origin is None
    assert verdicts["score check"].score == 1.0
