.PHONY: gate backend-gate frontend-gate frontend-test install scrape mail-poll tag-origins tag-genres backend-run frontend-run auth-bootstrap invite users

# Where the live foghorn database lives. fleet's PM2 manifest points the API
# at this same path; the targets below are the other writers, and they must
# agree with it. If they disagree nothing errors: repo/db.py's connect() runs
# schema.init_schema(), so a wrong path yields a fresh empty DB and a silently
# forked second copy of the data.
#
# This cannot live in backend/.env — load_local_env() is called lazily from
# scrapers/_ticketmaster.py, well after db.connect() has read os.environ. It
# has to be in the process environment before python starts.
#
# An existing FOGHORN_DB_PATH in your environment wins.
FOGHORN_DB_PATH ?= $(HOME)/fleet-data/foghorn/foghorn.db

# Full lint / type / test gate across both packages. Runs the backend half
# then the frontend half; make stops at the first target that exits non-zero.
# Deliberately does NOT get FOGHORN_DB_PATH: the test suite should never be
# aimed at the live database.
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
# per-venue counts. Writes to the SQLite DB at FOGHORN_DB_PATH (above).
scrape:
	cd backend && FOGHORN_DB_PATH="$(FOGHORN_DB_PATH)" python -m foghorn.cli.scrape

# Poll the IMAP folder of artist-newsletter emails into the review queue
# (Phase 8). Needs FOGHORN_IMAP_HOST/USER/PASSWORD (+ optional
# FOGHORN_IMAP_FOLDER, default "foghorn"); exits 0 with a hint when unset.
# Not on the in-process scheduler — run manually or from cron.
mail-poll:
	cd backend && FOGHORN_DB_PATH="$(FOGHORN_DB_PATH)" python -m foghorn.cli.mail_poll

# Apply the local/touring origin heuristic to performers in the DB.
# Idempotent; run after scrapes as history accumulates. Manual tags are kept.
tag-origins:
	cd backend && FOGHORN_DB_PATH="$(FOGHORN_DB_PATH)" python -m foghorn.cli.tag_origins

# Deterministic performer-genre bootstrap (Phase 7.4 stage 1). Idempotent;
# run after scrapes. Manual tags are kept.
tag-genres:
	cd backend && FOGHORN_DB_PATH="$(FOGHORN_DB_PATH)" python -m foghorn.cli.tag_genres

# Run the backend API (http://localhost:9100) with autoreload. Points at the
# live DB, as it did before the path moved — this is the dev counterpart of
# fleet's foghorn-api, not an isolated sandbox.
#
# The port is fleet's foghorn-api port + 1000, per the ad-hoc-dev convention
# in ~/fleet/PORTS.md. Explicitly NOT uvicorn's default 8000 — that is
# ficycle-api's fleet port on this machine, so binding it collides with a
# running ficycle. next.config.ts carries the same warning about its own
# default; this target was the one place still ignoring it.
backend-run:
	cd backend && FOGHORN_DB_PATH="$(FOGHORN_DB_PATH)" uvicorn foghorn.api:app --reload --port 9100

# Which backend the dev web server proxies /api/* to. Defaults to fleet's
# foghorn-api on :8100, so `make frontend-run` on its own still works against
# live data exactly as before. To pair it with `make backend-run` instead:
#   make frontend-run BACKEND_URL=http://127.0.0.1:9100
# An existing BACKEND_URL in your environment wins.
BACKEND_URL ?= http://127.0.0.1:8100

# Run the Next.js dev server (http://localhost:4100). Same rule as backend-run:
# fleet's foghorn-web port + 1000, NOT Next's default 3000 — that is
# ficycle-web's fleet port.
frontend-run:
	cd frontend && BACKEND_URL="$(BACKEND_URL)" npm run dev -- --port 4100

# Ensure an admin account exists in the live DB and print its login link
# (multi-user, August 2026). Safe to re-run.
auth-bootstrap:
	cd backend && FOGHORN_DB_PATH="$(FOGHORN_DB_PATH)" python -m foghorn.cli.auth bootstrap

# Create a friend's account and print their invite link: make invite NAME="Ada"
invite:
	cd backend && FOGHORN_DB_PATH="$(FOGHORN_DB_PATH)" python -m foghorn.cli.auth invite "$(NAME)"

# List all accounts in the live DB.
users:
	cd backend && FOGHORN_DB_PATH="$(FOGHORN_DB_PATH)" python -m foghorn.cli.auth list
