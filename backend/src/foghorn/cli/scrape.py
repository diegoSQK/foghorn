"""`make scrape`: run every registered scraper through the ingest pipeline.

Seeds venues (idempotent), then for each entry in ``REGISTERED_SCRAPERS``
scrapes, ingests, and prints per-venue ``created / updated / errors`` counts.
A scraper that raises is reported and skipped so one broken venue doesn't take
down the run. Exit code is the total number of per-show ingest errors plus
scraper-level failures, so CI/cron can detect trouble.
"""

from __future__ import annotations

import sqlite3
import sys

from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.repo import db
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed
from foghorn.scrapers import REGISTERED_SCRAPERS


def run_all(conn: sqlite3.Connection) -> int:
    """Scrape + ingest every registered venue. Returns a failure count
    (per-show ingest errors + scrapers that raised)."""
    seed(conn)
    failures = 0
    for slug, scrape in REGISTERED_SCRAPERS.items():
        venue = venues_repo.get_by_slug(conn, slug)
        if venue is None:
            print(f"{slug}: no seeded venue — skipping")
            failures += 1
            continue
        try:
            scraped = scrape()
        except Exception as exc:
            print(f"{slug}: scrape failed: {exc}")
            failures += 1
            continue
        result = ingest_scraped_shows(conn, venue, scraped)
        print(
            f"{slug}: scraped={len(scraped)} "
            f"created={result.created} updated={result.updated} "
            f"errors={len(result.errors)}"
        )
        for message in result.errors:
            print(f"    ! {message}")
        failures += len(result.errors)
    return failures


def main() -> None:
    conn = db.connect()
    try:
        failures = run_all(conn)
    finally:
        conn.close()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
