.PHONY: gate backend-gate frontend-gate frontend-test install scrape mail-poll tag-origins tag-genres backend-run frontend-run

# Full lint / type / test gate across both packages. Runs the backend half
# then the frontend half; make stops at the first target that exits non-zero.
gate: backend-gate frontend-gate

# Backend gate. Assumes the project's tools are on PATH — i.e. an activated
# Python venv locally (see backend/README.md), or the CI runner's
# setup-python environment after `make install`.
backend-gate:
	cd backend && ruff check . && mypy src && pytest

# Frontend gate. `npm run build` is included because it surfaces type/config
# issues that lint misses.
frontend-gate:
	cd frontend && npm run typecheck && npm run lint && npm run build

# Playwright e2e suite. Deliberately NOT part of `make gate` — it's slower and
# needs a browser binary. Opt-in locally and a dedicated CI job. Installs the
# Chromium build if missing (no-op when cached), then runs frontend/tests/
# against a mock backend (see frontend/tests/README.md).
frontend-test:
	cd frontend && npx playwright install chromium && npm run test:e2e

# Install both halves' dependencies. Run inside an activated Python venv
# locally; CI installs into the runner's setup-python environment.
install:
	cd backend && pip install -e ".[dev]"
	cd frontend && npm install

# Run every registered scraper once through the ingest pipeline, printing
# per-venue counts. Writes to the SQLite DB (FOGHORN_DB_PATH or the default).
scrape:
	cd backend && python -m foghorn.cli.scrape

# Poll the IMAP folder of artist-newsletter emails into the review queue
# (Phase 8). Needs FOGHORN_IMAP_HOST/USER/PASSWORD (+ optional
# FOGHORN_IMAP_FOLDER, default "foghorn"); exits 0 with a hint when unset.
# Not on the in-process scheduler — run manually or from cron.
mail-poll:
	cd backend && python -m foghorn.cli.mail_poll

# Apply the local/touring origin heuristic to performers in the DB.
# Idempotent; run after scrapes as history accumulates. Manual tags are kept.
tag-origins:
	cd backend && python -m foghorn.cli.tag_origins

# Deterministic performer-genre bootstrap (Phase 7.4 stage 1). Idempotent;
# run after scrapes. Manual tags are kept.
tag-genres:
	cd backend && python -m foghorn.cli.tag_genres

# Run the backend API (http://localhost:8000) with autoreload.
backend-run:
	cd backend && uvicorn foghorn.api:app --reload

# Run the Next.js dev server (http://localhost:3000).
frontend-run:
	cd frontend && npm run dev
