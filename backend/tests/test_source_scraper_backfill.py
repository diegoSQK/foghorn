"""The #130 migration attributes pre-existing scraped rows.

Registration was 1:1 per venue before #130, so every existing
``source='scrape'`` row can be mechanically attributed to its venue's
registered scraper. **Skipping this would be the expensive mistake**: the
reaper now matches on ``source_scraper``, so un-backfilled rows would match
nothing, never be reaped, and linger forever as duplicates — reintroducing
exactly the problem the reaper was built to solve.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from foghorn.repo import db
from foghorn.repo.schema import _backfill_source_scraper


def _legacy_row(conn: sqlite3.Connection, venue_id: int, day: str, source: str) -> None:
    """Insert a row as a pre-migration one: no source_scraper."""
    conn.execute(
        "INSERT INTO shows (venue_id, start_utc, start_local_date, start_local_time,"
        " headliner_canonical, source_url, scraped_at, source, source_scraper)"
        " VALUES (?, ?, ?, '20:00', ?, 'https://x/', '2026-01-01T00:00:00+00:00',"
        " ?, NULL)",
        (venue_id, f"{day}T04:00:00+00:00", day, f"act {day}", source),
    )
    conn.commit()


@pytest.fixture
def legacy_db(tmp_path: Path) -> sqlite3.Connection:
    """A DB whose scraped rows predate the column."""
    conn = db.connect(tmp_path / "legacy.db")
    from foghorn.repo.seed_venues import seed

    seed(conn)
    bb = conn.execute(
        "SELECT id FROM venues WHERE slug = 'bird_and_beckett'"
    ).fetchone()[0]
    _legacy_row(conn, bb, "2026-10-01", "scrape")
    _legacy_row(conn, bb, "2026-10-02", "scrape")
    _legacy_row(conn, bb, "2026-10-03", "manual")
    _legacy_row(conn, bb, "2026-10-04", "aggregator")
    return conn


def _attribution(conn: sqlite3.Connection) -> dict[str, str | None]:
    return {
        row["start_local_date"]: row["source_scraper"]
        for row in conn.execute(
            "SELECT start_local_date, source_scraper FROM shows"
        )
    }


def test_backfills_every_scraped_row(legacy_db: sqlite3.Connection) -> None:
    _backfill_source_scraper(legacy_db)
    attribution = _attribution(legacy_db)
    assert attribution["2026-10-01"] == "bird_and_beckett"
    assert attribution["2026-10-02"] == "bird_and_beckett"


def test_leaves_manual_and_aggregator_rows_null(
    legacy_db: sqlite3.Connection,
) -> None:
    """They have their own provenance and are never reaped."""
    _backfill_source_scraper(legacy_db)
    attribution = _attribution(legacy_db)
    assert attribution["2026-10-03"] is None
    assert attribution["2026-10-04"] is None


def test_no_scraped_row_is_left_unattributed(
    legacy_db: sqlite3.Connection,
) -> None:
    """The property that matters: an un-backfilled scraped row would never be
    reaped again."""
    _backfill_source_scraper(legacy_db)
    orphans = legacy_db.execute(
        "SELECT COUNT(*) FROM shows WHERE source = 'scrape' AND source_scraper IS NULL"
    ).fetchone()[0]
    assert orphans == 0


def test_is_idempotent(legacy_db: sqlite3.Connection) -> None:
    _backfill_source_scraper(legacy_db)
    before = _attribution(legacy_db)
    _backfill_source_scraper(legacy_db)
    assert _attribution(legacy_db) == before


def test_does_not_overwrite_an_existing_attribution(
    legacy_db: sqlite3.Connection,
) -> None:
    """A row already attributed to a presenter feed must not be re-stamped
    with the venue's own scraper."""
    legacy_db.execute(
        "UPDATE shows SET source_scraper = 'sfjazz' WHERE start_local_date = '2026-10-01'"
    )
    legacy_db.commit()
    _backfill_source_scraper(legacy_db)
    assert _attribution(legacy_db)["2026-10-01"] == "sfjazz"


class TestMultiVenueAttribution:
    """The near-miss. Attributing by registry id alone stranded 76 Blue Heron
    Boathouse rows in rehearsal — the boathouse's contributor is
    `the_mellow_haight`, so nothing would ever have matched them, and a NULL
    `source_scraper` is deliberately never swept either. Attribution goes by
    venue coverage, not by id."""

    def test_a_second_room_is_attributed_to_its_scraper(self) -> None:
        from foghorn.scrapers import contributor_for_venue, the_mellow

        assert (
            contributor_for_venue(the_mellow.VENUE_SLUG_BOATHOUSE)
            == the_mellow.VENUE_SLUG_HAIGHT
        )

    def test_a_venue_with_its_own_scraper_keeps_it(self) -> None:
        """The Paramount is covered by its own scraper *and* by SFJAZZ. Rows
        there predating #130 were made by the venue's scraper, since the
        presenter feed was filtered out precisely to avoid the reaper."""
        from foghorn.scrapers import contributor_for_venue, sfjazz

        assert "paramount_theatre_oakland" in sfjazz.COVERED_VENUES
        assert (
            contributor_for_venue("paramount_theatre_oakland")
            == "paramount_theatre_oakland"
        )

    def test_a_venue_nothing_scrapes_has_no_contributor(self) -> None:
        """Herbst is fed only by aggregators, whose rows are never reaped and
        so are never attributed."""
        from foghorn.scrapers import contributor_for_venue

        assert contributor_for_venue("herbst_theatre") is None

    def test_davies_is_now_covered_by_sfjazz(self) -> None:
        """Before #130 nothing scraped Davies — SFJAZZ dropped its off-site
        dates rather than risk the reaper. It contributes there now, which is
        what puts the Julian Lage date in foghorn."""
        from foghorn.scrapers import contributor_for_venue

        assert contributor_for_venue("davies_symphony_hall") == "sfjazz"

    def test_coverage_is_derived_not_hand_listed(self) -> None:
        """SFJAZZ's coverage comes off its location map, so the two can't
        drift apart when it starts booking somewhere new."""
        from foghorn.scrapers import sfjazz

        assert sfjazz.COVERED_VENUES == frozenset(sfjazz._LOCATION_SLUGS.values())
        assert "davies_symphony_hall" in sfjazz.COVERED_VENUES


def test_runs_automatically_on_connect(tmp_path: Path) -> None:
    """schema.init_schema() runs at every connect(), so an existing DB is
    migrated the first time anything opens it — no manual step."""
    path = tmp_path / "auto.db"
    conn = db.connect(path)
    from foghorn.repo.seed_venues import seed

    seed(conn)
    bb = conn.execute(
        "SELECT id FROM venues WHERE slug = 'bird_and_beckett'"
    ).fetchone()[0]
    _legacy_row(conn, bb, "2026-11-01", "scrape")
    conn.close()

    reopened = db.connect(path)
    attribution = _attribution(reopened)
    reopened.close()
    assert attribution["2026-11-01"] == "bird_and_beckett"
