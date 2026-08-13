"""Which scrapers the scheduled run covers on a given day.

Most venues run nightly. ``MONTHLY_SCRAPERS`` join on the 1st — currently just
SFJAZZ, whose site started challenging the scraper again on 2026-08-12 and
whose season is already ingested through February, so a nightly attempt could
only produce a nightly error nobody can act on.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from foghorn.scheduler.runner import (
    MONTHLY_SCRAPE_DAY,
    run_scrape,
    scrapers_due,
)
from foghorn.scrapers import MONTHLY_SCRAPERS, REGISTERED_SCRAPERS


def test_sfjazz_is_the_monthly_one() -> None:
    assert MONTHLY_SCRAPERS == {"sfjazz"}
    # ...and it's still registered — monthly, not removed.
    assert "sfjazz" in REGISTERED_SCRAPERS


def test_monthly_scrapers_sit_out_the_nightly_run() -> None:
    due = scrapers_due(date(2026, 8, 13))
    assert "sfjazz" not in due
    # Every other registered venue still runs.
    assert set(due) == set(REGISTERED_SCRAPERS) - MONTHLY_SCRAPERS
    assert len(due) == len(REGISTERED_SCRAPERS) - 1


def test_monthly_scrapers_join_on_the_first() -> None:
    due = scrapers_due(date(2026, 9, MONTHLY_SCRAPE_DAY))
    assert "sfjazz" in due
    assert set(due) == set(REGISTERED_SCRAPERS)


def test_every_month_gets_exactly_one_attempt() -> None:
    # A whole year of days, so the cadence can't silently become "never".
    firsts = [
        d
        for d in (date(2026, m, day) for m in range(1, 13) for day in (1, 2, 15, 28))
        if "sfjazz" in scrapers_due(d)
    ]
    assert len(firsts) == 12
    assert {d.day for d in firsts} == {1}


def test_the_callables_are_the_registered_ones() -> None:
    # Filtering must not rebind anything — same functions, fewer keys.
    due = scrapers_due(date(2026, 8, 13))
    assert all(due[slug] is REGISTERED_SCRAPERS[slug] for slug in due)


def test_an_injected_map_is_filtered_the_same_way() -> None:
    # Tests and callers can pass their own map; the cadence rule still applies.
    fake = {"sfjazz": lambda: [], "bird_and_beckett": lambda: []}
    assert set(scrapers_due(date(2026, 8, 13), fake)) == {"bird_and_beckett"}
    assert set(scrapers_due(date(2026, 8, 1), fake)) == set(fake)


def test_run_scrape_itself_stays_cadence_agnostic(conn: sqlite3.Connection) -> None:
    """`make scrape` means "refresh now" — it must not silently skip a venue.

    The cadence lives in the scheduler entry point, so run_scrape covers
    whatever map it's handed, monthly slugs included, on any date.
    """
    run = run_scrape(
        conn,
        {"sfjazz": lambda: [], "bird_and_beckett": lambda: []},
        aggregators={},
    )
    assert {v.venue_slug for v in run.venues} == {"sfjazz", "bird_and_beckett"}
    assert all(v.errors == [] for v in run.venues)
