"""Tests for the deterministic performer-genre bootstrap (Phase 7.4 stage 1)."""

from __future__ import annotations

import datetime as dt
import sqlite3

from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow
from foghorn.repo import performers as performers_repo
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed
from foghorn.tagging.genre import apply_heuristic


def _ingest(
    conn: sqlite3.Connection,
    venue_slug: str,
    headliner: str,
    start: dt.datetime,
    *,
    genre: str | None = None,
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
                start_local=start,
                source_url="https://example.com/show",
                genre=genre,
            )
        ],
    )
    assert result.errors == []


def _genre(conn: sqlite3.Connection, canonical: str) -> str | None:
    performer = performers_repo.get_by_canonical(conn, canonical)
    assert performer is not None
    return performer.genre


def test_consistent_venue_lean_evidence_tags(conn: sqlite3.Connection) -> None:
    seed(conn)
    # Two jazz-lean rooms, unanimous evidence -> jazz.
    _ingest(conn, "keys_jazz_bistro", "Consistent Trio", dt.datetime(2026, 7, 3, 20, 0))
    _ingest(conn, "yoshis", "Consistent Trio", dt.datetime(2026, 8, 2, 19, 30))
    apply_heuristic(conn)
    assert _genre(conn, "consistent trio") == "jazz"


def test_single_venue_lean_observation_is_not_enough(conn: sqlite3.Connection) -> None:
    seed(conn)
    _ingest(conn, "keys_jazz_bistro", "One Nighter", dt.datetime(2026, 7, 3, 20, 0))
    apply_heuristic(conn)
    assert _genre(conn, "one nighter") is None


def test_single_override_grade_observation_tags(conn: sqlite3.Connection) -> None:
    seed(conn)
    # A per-show source genre is a claim about that exact bill — one suffices.
    _ingest(
        conn,
        "great_american_music_hall",
        "Override Act",
        dt.datetime(2026, 7, 8, 20, 0),
        genre="Hip-Hop",
    )
    apply_heuristic(conn)
    assert _genre(conn, "override act") == "hip-hop"


def test_mixed_evidence_stays_untagged(conn: sqlite3.Connection) -> None:
    seed(conn)
    # Jazz room + rock room -> mixed -> no guess.
    _ingest(conn, "keys_jazz_bistro", "Genre Hopper", dt.datetime(2026, 7, 3, 20, 0))
    _ingest(conn, "bottom_of_the_hill", "Genre Hopper", dt.datetime(2026, 8, 2, 20, 0))
    apply_heuristic(conn)
    assert _genre(conn, "genre hopper") is None


def test_performer_name_counts_as_override_grade_evidence(
    conn: sqlite3.Connection,
) -> None:
    seed(conn)
    # Eclectic venue contributes nothing, but the act's own name is a claim.
    _ingest(conn, "madrone_art_bar", "Fog City Swing", dt.datetime(2026, 7, 5, 21, 0))
    apply_heuristic(conn)
    assert _genre(conn, "fog city swing") == "jazz"


def test_manual_tag_survives_and_stale_heuristic_clears(
    conn: sqlite3.Connection,
) -> None:
    seed(conn)
    _ingest(conn, "keys_jazz_bistro", "Correctable", dt.datetime(2026, 7, 3, 20, 0))
    _ingest(conn, "yoshis", "Correctable", dt.datetime(2026, 8, 2, 19, 30))
    apply_heuristic(conn)
    assert _genre(conn, "correctable") == "jazz"
    performers_repo.set_genre(conn, "correctable", "latin", "manual")
    apply_heuristic(conn)
    assert _genre(conn, "correctable") == "latin"  # manual wins forever

    # Stale heuristic clears when evidence turns mixed.
    _ingest(conn, "keys_jazz_bistro", "Fader", dt.datetime(2026, 7, 4, 20, 0))
    _ingest(conn, "yoshis", "Fader", dt.datetime(2026, 8, 3, 19, 30))
    apply_heuristic(conn)
    assert _genre(conn, "fader") == "jazz"
    _ingest(conn, "bottom_of_the_hill", "Fader", dt.datetime(2026, 9, 1, 20, 0))
    apply_heuristic(conn)
    assert _genre(conn, "fader") is None
