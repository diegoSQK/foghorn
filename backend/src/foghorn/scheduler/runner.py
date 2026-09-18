"""Nightly scrape runner + the APScheduler wiring around it.

`run_scrape` is the unit of work shared by the scheduler and `make scrape`: it
runs the scrapers it's given (default: every registered one) through ingest,
captures a per-venue result, and records one `scrape_runs` row (trimmed to the
last N). It never raises on a per-venue failure — the failure is captured in
that venue's `errors` so one bad venue can't take down the run or the scheduler
thread.

**Cadence.** The scheduled run covers `scrapers_due(today)`, which is everything
except `MONTHLY_SCRAPERS` on most days and everything on the 1st. `run_scrape`
itself is cadence-agnostic, so `make scrape` still refreshes every venue —
typing it is an explicit "refresh now", and silently skipping a venue there
would be a footgun.

**Scheduler choice: `BackgroundScheduler`, not `AsyncIOScheduler`.** The job is
synchronous and blocking (httpx fetches + SQLite writes); running it on a
background thread keeps it off the FastAPI event loop. Each run opens its own
SQLite connection in that thread, satisfying sqlite3's `check_same_thread`.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from foghorn.aggregators import AGGREGATOR_SOURCES
from foghorn.aggregators.ingest import ingest_aggregated_events
from foghorn.aggregators.models import AggregatedEvent
from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow, ScrapeRun, ScrapeRunVenue
from foghorn.repo import db
from foghorn.repo import scrape_runs as scrape_runs_repo
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed
from foghorn.scrapers import MONTHLY_SCRAPERS, REGISTERED_SCRAPERS, diagnostics

logger = logging.getLogger("foghorn.scheduler")

# 04:00 America/Los_Angeles — low-traffic, after most West Coast venues have
# settled the next day's listings.
SCRAPE_HOUR = 4
SCRAPE_TZ = "America/Los_Angeles"
JOB_ID = "nightly_scrape"
# Day of the month the MONTHLY_SCRAPERS join the nightly run.
MONTHLY_SCRAPE_DAY = 1
DISABLE_ENV = "FOGHORN_DISABLE_SCHEDULER"

ScraperMap = dict[str, Callable[[], list[ScrapedShow]]]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def run_scrape(
    conn: sqlite3.Connection,
    scrapers: ScraperMap | None = None,
    *,
    aggregators: dict[str, Callable[[], list[AggregatedEvent]]] | None = None,
    keep_runs: int = scrape_runs_repo.DEFAULT_KEEP,
) -> ScrapeRun:
    """Run every scraper + aggregator source through ingest and record the
    run. Both maps default to the live registries (injectable for tests)."""
    if scrapers is None:
        scrapers = REGISTERED_SCRAPERS
    if aggregators is None:
        aggregators = AGGREGATOR_SOURCES
    seed(conn)  # ensure venues exist before ingest
    run_started = _now()
    venue_results: list[ScrapeRunVenue] = []
    for slug, scrape in scrapers.items():
        venue_started = _now()
        created = updated = reaped = 0
        errors: list[str] = []
        # A successful run can still drop a show on purpose; scrapers report
        # that here rather than it vanishing (see scrapers/diagnostics).
        diagnostics.reset()
        try:
            # A scraper may contribute to several venues — SFJAZZ books rooms
            # it doesn't own — so its output is grouped by the venue each show
            # actually names rather than assumed to be the registry key's.
            # Each group ingests with prune scoped to (venue, this scraper),
            # which is what makes sharing a venue safe (#130).
            by_venue: dict[str, list[ScrapedShow]] = {}
            for show in scrape():
                by_venue.setdefault(show.venue_slug, []).append(show)
            if not by_venue:
                # Nothing returned: still check the registry's own venue
                # exists, which is the misconfiguration this used to catch.
                if venues_repo.get_by_slug(conn, slug) is None:
                    errors.append(f"no seeded venue for slug {slug!r}")
            for venue_slug, shows in sorted(by_venue.items()):
                venue = venues_repo.get_by_slug(conn, venue_slug)
                if venue is None:
                    errors.append(f"no seeded venue for slug {venue_slug!r}")
                    continue
                # prune=True: a scraper returns its whole current window for
                # the venues it covers, so rows *it* contributed and no longer
                # lists are stale (retitled / rescheduled / cancelled).
                result = ingest_scraped_shows(
                    conn, venue, shows, prune=True, source_scraper=slug
                )
                created += result.created
                updated += result.updated
                reaped += result.reaped
                errors.extend(result.errors)
        except Exception as exc:
            # Isolate a venue-level failure (scraper raised, network, etc.).
            errors.append(f"{type(exc).__name__}: {exc}")
        venue_finished = _now()
        logger.info(
            "scrape.venue",
            extra={
                "venue": slug,
                "created": created,
                "updated": updated,
                "reaped": reaped,
                "errors": len(errors),
            },
        )
        venue_results.append(
            ScrapeRunVenue(
                venue_slug=slug,
                started_at=venue_started,
                finished_at=venue_finished,
                created=created,
                updated=updated,
                errors=errors,
                notes=diagnostics.drain(),
            )
        )
    # Rows whose contributing scraper is no longer registered would otherwise
    # linger forever, since a scraper now only reaps its own (#130). Runs after
    # the scrapers so one that succeeded this pass has already refreshed its
    # rows' scraped_at and can never be caught by the threshold.
    orphan_cutoff = (
        datetime.now(UTC) - timedelta(days=shows_repo.ORPHAN_SWEEP_DAYS)
    ).isoformat()
    swept = shows_repo.reap_orphaned(
        conn, scrapers.keys(), scraped_before=orphan_cutoff
    )
    if swept:
        logger.info("scrape.orphans_swept", extra={"rows": swept})

    # Aggregator sources run after the venue scrapers so the duplicate guard
    # defers to fresh authoritative rows. Each records one pseudo-venue slice
    # (slug "aggregator:<source>") in the run, same isolation contract.
    for source_id, fetch in aggregators.items():
        source_started = _now()
        created = updated = 0
        errors = []
        try:
            result = ingest_aggregated_events(conn, fetch(), source_id)
            created, updated = result.created, result.updated
            errors = list(result.errors)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        logger.info(
            "scrape.aggregator",
            extra={"source": source_id, "created": created, "errors": len(errors)},
        )
        venue_results.append(
            ScrapeRunVenue(
                venue_slug=f"aggregator:{source_id}",
                started_at=source_started,
                finished_at=_now(),
                created=created,
                updated=updated,
                errors=errors,
            )
        )
    run = ScrapeRun(
        started_at=run_started, finished_at=_now(), venues=venue_results
    )
    stored = scrape_runs_repo.record_run(conn, run, keep=keep_runs)
    total_errors = sum(len(v.errors) for v in venue_results)
    logger.info(
        "scrape.run",
        extra={"venues": len(venue_results), "errors": total_errors},
    )
    return stored


def scrapers_due(today: date, scrapers: ScraperMap | None = None) -> ScraperMap:
    """The scrapers the scheduled run should cover on ``today``.

    Everything runs nightly except ``MONTHLY_SCRAPERS``, which join in on the
    1st. Varying one job's venue set — rather than adding a second monthly job
    — keeps the scrape-health surface honest: it reports the *last run*, so a
    separate job would leave it showing a single venue and 78 apparently
    missing until the next nightly.
    """
    source = REGISTERED_SCRAPERS if scrapers is None else scrapers
    if today.day == MONTHLY_SCRAPE_DAY:
        return dict(source)
    return {
        slug: scrape
        for slug, scrape in source.items()
        if slug not in MONTHLY_SCRAPERS
    }


def scheduled_scrape() -> None:
    """Entry point APScheduler invokes — owns its own connection (it runs on a
    background thread)."""
    conn = db.connect()
    try:
        run_scrape(conn, scrapers_due(date.today()))
    finally:
        conn.close()


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=SCRAPE_TZ)
    scheduler.add_job(
        scheduled_scrape,
        CronTrigger(hour=SCRAPE_HOUR, minute=0, timezone=SCRAPE_TZ),
        id=JOB_ID,
        replace_existing=True,
    )
    return scheduler


def start_scheduler() -> BackgroundScheduler | None:
    """Start the nightly scheduler, unless disabled (e.g. in tests via
    ``FOGHORN_DISABLE_SCHEDULER``). Returns the running scheduler, or ``None``
    when disabled."""
    if os.environ.get(DISABLE_ENV):
        logger.info("scheduler.disabled", extra={"env": DISABLE_ENV})
        return None
    scheduler = build_scheduler()
    scheduler.start()
    logger.info(
        "scheduler.started",
        extra={"job": JOB_ID, "hour": SCRAPE_HOUR, "tz": SCRAPE_TZ},
    )
    return scheduler
