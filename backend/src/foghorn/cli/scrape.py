"""`make scrape`: run every registered scraper through the ingest pipeline.

Delegates to ``scheduler.runner.run_scrape`` — the same unit of work the nightly
scheduler runs — so a manual refresh records a ``scrape_runs`` row and shows up
in ``GET /api/health/scrape`` exactly like a scheduled one. Prints the per-venue
``created / updated / errors`` breakdown; exits non-zero if any venue errored.
"""

from __future__ import annotations

import sys

from foghorn.repo import db
from foghorn.scheduler.runner import run_scrape


def main() -> None:
    conn = db.connect()
    try:
        run = run_scrape(conn)
    finally:
        conn.close()
    failures = 0
    for venue in run.venues:
        print(
            f"{venue.venue_slug}: created={venue.created} "
            f"updated={venue.updated} errors={len(venue.errors)}"
        )
        for message in venue.errors:
            print(f"    ! {message}")
        failures += len(venue.errors)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
