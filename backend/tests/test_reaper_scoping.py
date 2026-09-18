"""Per-contributor reaper scoping (#130).

The old reaper was scoped to ``(venue, span)``, which encoded "exactly one
scraper is authoritative at this venue". That was true only because the
registry forbade anything else — and the moment a presenter books a room it
doesn't own, it is false. The workarounds cost real shows: `scrape_center()`
dropped a Julian Lage date at Davies, and it appeared nowhere.

The property under test is the one the ticket exists to establish: **a run of
one scraper never deletes another scraper's rows at the same venue.**
"""

from __future__ import annotations

import datetime as dt
import sqlite3

import pytest

from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow, ShowFilters, Venue
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed

PARAMOUNT = "paramount_theatre_oakland"


def _show(slug: str, name: str, day: int) -> ScrapedShow:
    return ScrapedShow(
        venue_slug=slug,
        headliner_raw=name,
        support_raw=[],
        start_local=dt.datetime(2026, 10, day, 20, 0),
        source_url="https://example.test/",
    )


def _ingest(
    conn: sqlite3.Connection,
    venue: Venue,
    shows: list[ScrapedShow],
    scraper: str,
    *,
    prune: bool = True,
):  # type: ignore[no-untyped-def]
    return ingest_scraped_shows(
        conn, venue, shows, prune=prune, source_scraper=scraper
    )


def _billings(conn: sqlite3.Connection, slug: str) -> set[str]:
    return {
        s.headliner_canonical
        for s in shows_repo.list(conn, ShowFilters(venue_slugs=[slug]))
    }


@pytest.fixture
def paramount(conn: sqlite3.Connection) -> Venue:
    seed(conn)
    venue = venues_repo.get_by_slug(conn, PARAMOUNT)
    assert venue is not None
    return venue


class TestTwoScrapersOneVenue:
    def test_a_run_never_reaps_another_scrapers_rows(
        self, conn: sqlite3.Connection, paramount: Venue
    ) -> None:
        """The whole point. SFJAZZ lists only the two nights it presents at
        the Paramount; before #130, registering it here would have reaped
        every other Paramount show in the span."""
        _ingest(
            conn,
            paramount,
            [_show(PARAMOUNT, "House Act One", 1), _show(PARAMOUNT, "House Act Two", 9)],
            PARAMOUNT,
        )
        assert _billings(conn, PARAMOUNT) == {"house act one", "house act two"}

        # A presenter's feed covers the same span but lists only its own night.
        _ingest(conn, paramount, [_show(PARAMOUNT, "Snarky Puppy", 5)], "sfjazz")

        assert _billings(conn, PARAMOUNT) == {
            "house act one",
            "house act two",
            "snarky puppy",
        }

    def test_each_scraper_still_reaps_its_own_stale_rows(
        self, conn: sqlite3.Connection, paramount: Venue
    ) -> None:
        _ingest(conn, paramount, [_show(PARAMOUNT, "Snarky Puppy", 5)], "sfjazz")
        _ingest(conn, paramount, [_show(PARAMOUNT, "House Act", 5)], PARAMOUNT)
        # SFJAZZ re-runs with the date retitled: its own old row goes, the
        # venue scraper's row stays.
        _ingest(
            conn, paramount, [_show(PARAMOUNT, "Snarky Puppy Trio", 5)], "sfjazz"
        )
        assert _billings(conn, PARAMOUNT) == {"house act", "snarky puppy trio"}

    def test_rows_carry_their_contributor(
        self, conn: sqlite3.Connection, paramount: Venue
    ) -> None:
        _ingest(conn, paramount, [_show(PARAMOUNT, "Snarky Puppy", 5)], "sfjazz")
        rows = shows_repo.list(conn, ShowFilters(venue_slugs=[PARAMOUNT]))
        assert [r.source_scraper for r in rows] == ["sfjazz"]


class TestUnchangedWhereOneScraperOwnsAVenue:
    def test_a_retitled_show_still_replaces_rather_than_duplicating(
        self, conn: sqlite3.Connection, paramount: Venue
    ) -> None:
        """#93's behaviour must be identical where one scraper owns a venue."""
        _ingest(conn, paramount, [_show(PARAMOUNT, "Old Title", 5)], PARAMOUNT)
        _ingest(conn, paramount, [_show(PARAMOUNT, "New Title", 5)], PARAMOUNT)
        assert _billings(conn, PARAMOUNT) == {"new title"}

    def test_manual_and_aggregator_rows_survive(
        self, conn: sqlite3.Connection, paramount: Venue
    ) -> None:
        ingest_scraped_shows(
            conn, paramount, [_show(PARAMOUNT, "Hand Entered", 5)], source="manual"
        )
        ingest_scraped_shows(
            conn,
            paramount,
            [_show(PARAMOUNT, "From An Aggregator", 6)],
            source="aggregator",
        )
        _ingest(conn, paramount, [_show(PARAMOUNT, "Scraped", 7)], PARAMOUNT)
        _ingest(conn, paramount, [_show(PARAMOUNT, "Scraped Again", 7)], PARAMOUNT)
        assert _billings(conn, PARAMOUNT) == {
            "hand entered",
            "from an aggregator",
            "scraped again",
        }


class TestOrphanSweep:
    """A scraper that stops running never reaps its own rows again — the cost
    of per-contributor scoping, and this is the backstop."""

    def test_sweeps_rows_of_a_scraper_no_longer_registered(
        self, conn: sqlite3.Connection, paramount: Venue
    ) -> None:
        _ingest(conn, paramount, [_show(PARAMOUNT, "Retired Feed Show", 5)], "gone_away")
        _ingest(conn, paramount, [_show(PARAMOUNT, "Live Feed Show", 6)], PARAMOUNT)

        swept = shows_repo.reap_orphaned(
            conn, {PARAMOUNT}, scraped_before="2099-01-01T00:00:00+00:00"
        )
        assert swept == 1
        assert _billings(conn, PARAMOUNT) == {"live feed show"}

    def test_does_not_sweep_rows_newer_than_the_threshold(
        self, conn: sqlite3.Connection, paramount: Venue
    ) -> None:
        """A scraper that is merely broken today must not have its calendar
        deleted — the threshold is deliberately generous."""
        _ingest(conn, paramount, [_show(PARAMOUNT, "Recently Scraped", 5)], "gone_away")
        swept = shows_repo.reap_orphaned(
            conn, {PARAMOUNT}, scraped_before="2000-01-01T00:00:00+00:00"
        )
        assert swept == 0
        assert _billings(conn, PARAMOUNT) == {"recently scraped"}

    def test_never_sweeps_manual_or_aggregator_rows(
        self, conn: sqlite3.Connection, paramount: Venue
    ) -> None:
        ingest_scraped_shows(
            conn, paramount, [_show(PARAMOUNT, "Hand Entered", 5)], source="manual"
        )
        swept = shows_repo.reap_orphaned(
            conn, set(), scraped_before="2099-01-01T00:00:00+00:00"
        )
        assert swept == 0
        assert _billings(conn, PARAMOUNT) == {"hand entered"}

    def test_threshold_is_conservative(self) -> None:
        """Stale rows beat missing ones — a fortnight's outage must not
        trigger a sweep."""
        assert shows_repo.ORPHAN_SWEEP_DAYS >= 14


class TestWorkaroundsRetired:
    def test_sfjazz_registers_wholesale(self) -> None:
        from foghorn.scrapers import REGISTERED_SCRAPERS, sfjazz

        assert REGISTERED_SCRAPERS[sfjazz.VENUE_SLUG] is sfjazz.scrape

    def test_the_mellow_registers_once(self) -> None:
        from foghorn.scrapers import REGISTERED_SCRAPERS, the_mellow

        registered = [
            slug
            for slug, fn in REGISTERED_SCRAPERS.items()
            if fn in (the_mellow.scrape, the_mellow.scrape_haight, the_mellow.scrape_boathouse)
        ]
        assert registered == [the_mellow.VENUE_SLUG_HAIGHT]
        assert REGISTERED_SCRAPERS[the_mellow.VENUE_SLUG_HAIGHT] is the_mellow.scrape
