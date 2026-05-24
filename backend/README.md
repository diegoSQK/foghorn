# foghorn backend

Python 3.11+ backend for foghorn: per-venue scrapers, an ingest pipeline, a
SQLite store, and a FastAPI HTTP surface. This README is the authoritative
reference for the data model, scraper interface, ingest pipeline, and API
surface. Most sections are placeholders filled in over Phase 1.2 / 2.x — see
[`docs/PROJECT_PLAN.md`](../docs/PROJECT_PLAN.md) for sequencing.

## Overview

```
src/foghorn/
  scrapers/   per-venue scrapers → list[ScrapedShow]   (Phase 2.x)
  ingest/     normalize · dedupe · persist pipeline      (Phase 1.2)
  repo/       SQLite persistence layer                   (Phase 1.2)
  api/        FastAPI HTTP surface                        (Phase 2.x)
```

The data lifecycle is **scrape → normalize → persist → serve → render**. See
`AGENTS.md` → "Architecture Debugging Map" for where each kind of show-data
bug originates.

### Local development

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

The lint / type / test gate (also runnable from the repo root via
`make backend-gate`):

```bash
ruff check .
mypy src
pytest
```

## Storage

**Decision: stdlib `sqlite3`, not an ORM.** foghorn is single-user and
local-first through Phase 5 (see `AGENTS.md` → "Deferred Workstream"). The
query surface is small and well understood — filtered `SELECT`s over shows,
upsert-on-natural-key for idempotent scraper re-runs — so a hand-written SQL
layer in `repo/` carries less ceremony than SQLAlchemy and keeps the
dependency surface minimal. SQLite files are trivially inspectable with any
`sqlite3` client when debugging show-data issues.

`sqlite3` is in the standard library, so it adds no entry to `pyproject.toml`.
The repo layer wraps it behind typed functions returning Pydantic models, so
callers never touch raw rows or `Any`. If/when hosting forces Postgres (the
deferred unblock condition), the repo layer is the single seam to swap; nothing
above it issues SQL directly.

*Filled in Phase 1.2 with connection handling, migrations, and the repo
primitives.*

## Data Model

*Filled in Phase 1.2.* Tables: `venues`, `shows`, `performers`, and
`show_performers` (many-to-many for headliner + support acts). Natural key for
a show is `(venue_id, local_start_datetime, headliner_canonical)`; times stored
as UTC alongside the venue's IANA tz; performer names stored as both
`display_name` (verbatim) and `canonical_name` (normalized for search /
watchlist matching). See `AGENTS.md` → "Conventions" for the full rules.

## API Surface

*Filled in Phase 2.x.* FastAPI app serving filtered show queries
(`GET /api/shows` with date-range / region / performer-search params), a
scrape-health endpoint (`GET /api/health/scrape`), and the watchlist surface
(Phase 4).

## Scrapers

*Filled in Phase 2.x.* Each venue scraper lives in
`foghorn.scrapers.<venue_slug>` and returns `list[ScrapedShow]` (a frozen
Pydantic model). Scrapers are independently runnable
(`python -m foghorn.scrapers.<venue>`) with no DB write side effects — that's
the ingest pipeline's job. Seed venues: SFJAZZ, Keys Jazz Bistro, Bird &
Beckett, Mr. Tipple's.
