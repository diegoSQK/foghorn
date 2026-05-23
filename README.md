# foghorn

A Bay Area local music & jazz show aggregator. Scrapes venue calendars and surfaces upcoming shows filtered by region, performer, and a personal watchlist of friends to follow.

## What it does

- Aggregates the show calendars of a curated set of Bay Area music venues (jazz-leaning, expanding to rock/indie).
- Filters by date range, region (SF / East Bay / Peninsula / South Bay), neighborhood, and free-text performer search.
- A personal watchlist surfaces upcoming shows where any performer on the bill matches a name you're tracking — built for "where are my friends playing this week."
- Refreshes daily via per-venue scrapers; each show preserves its source URL and scrape timestamp for provenance.

## Status

Greenfield as of May 2026. Phase 1 scaffolding is the first work landing — see [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) for the roadmap and current state.

## Stack

Two-package monorepo:

- `backend/` — Python 3.11+, FastAPI, SQLite. Per-venue scrapers in `backend/scrapers/`. Scheduled refresh via APScheduler.
- `frontend/` — Next.js 15 + React 19 + TypeScript + Tailwind.

## How the project is run

foghorn uses an agent-driven development model documented in [`AGENTS.md`](AGENTS.md). A long-running PM thread maintains strategy and docs; coding agents pick up GitHub Issues and ship via PRs. The template that underpins this workflow lives at [diegoSQK/agent-team-template](https://github.com/diegoSQK/agent-team-template).

For developers (human or agent) joining the project:

- Read [`AGENTS.md`](AGENTS.md) for the roles, conventions, and gates.
- Read [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) for the active roadmap.
- Read [`docs/SHIPPED.md`](docs/SHIPPED.md) on demand when scoping new work in an area where something similar has shipped.
- For PM-thread bootstrapping specifically, see [`docs/PM_THREAD_BOOTSTRAP.md`](docs/PM_THREAD_BOOTSTRAP.md).
