# foghorn Shipped Work

Chronological record of completed work — what landed, when, and why. Each entry preserves the narrative context that informed the design so it stays available as scar tissue when scoping new work.

`PROJECT_PLAN.md` is the active doc: what's in flight, queued, and deferred. When a new phase/feature ships, its spec moves here and the active doc collapses to a one-line status with a link into this file. Read this file on demand when you need detail on past work; the active doc is the daily read.

Ordering: newest at top. When adding a new entry, insert it at the top of the file. Older entries preserve their original recording order — when reorganizing, prefer "insert at top of recent block" over "deeply reorder existing history."

---

## Repo skeleton and CI gate (Phase 1.1, May 2026)

First code to land in foghorn — the two-package monorepo skeleton, the
lint/type/test gate, and CI. No application logic; this is the structure that
Phase 1.2 (data model) and Phase 2 (scrapers) fill in. Closes #2.

**Backend** (`backend/`). Python 3.11+, `src/` layout with `foghorn` as the
import root and empty-but-present `scrapers/`, `ingest/`, `repo/`, `api/`
subpackages. `pyproject.toml` uses hatchling and pins runtime deps (fastapi,
httpx, beautifulsoup4, apscheduler, pydantic v2) and dev deps (pytest, ruff,
mypy) to the exact versions resolved at scaffold time. APScheduler is held on
the 3.x line — 4.x is a different API. mypy runs in `strict` mode; one smoke
test (`tests/test_smoke.py`) imports all four subpackages so the gate has
something real to run.

**Storage decision: stdlib `sqlite3`, not SQLAlchemy.** The ticket left this to
the implementer. foghorn is single-user / local-first through Phase 5, the
query surface is small (filtered `SELECT`s plus upsert-on-natural-key for
idempotent scraper re-runs), and a hand-written SQL layer in `repo/` keeps the
dependency surface minimal and the DB trivially inspectable with any `sqlite3`
client. The repo layer (Phase 1.2) will wrap `sqlite3` behind typed functions
returning Pydantic models, so callers never touch raw rows or `Any`. If hosting
later forces Postgres, `repo/` is the single seam to swap. Documented in
`backend/README.md` § Storage.

**Frontend** (`frontend/`). `create-next-app` with TypeScript + Tailwind +
App Router (no `src/` dir, `@/*` import alias). The demo page is stripped to a
"foghorn — coming soon" placeholder and the layout metadata set to foghorn.
Added a `typecheck` script (`tsc --noEmit`) because the gate calls
`npm run typecheck` and create-next-app doesn't generate one.

**Gate + CI.** Root `Makefile`: `make gate` runs the backend half
(`ruff check . && mypy src && pytest`) then the frontend half
(`npm run typecheck && npm run lint && npm run build`), stopping at the first
non-zero exit; `make backend-gate` / `make frontend-gate` run the halves
individually; `make install` installs both. The backend targets assume the
project's tools are on PATH (an activated venv locally, or the CI runner's
setup-python environment after `make install`). `.github/workflows/gate.yml`
runs `make install && make gate` on ubuntu-latest with Python 3.11 + Node 20,
caching pip and npm. Root `.gitignore` covers Python, Node, and the
`*.db`/`*.sqlite*` files Phase 1.2 will start writing.

**Notes / gotchas (some for the PM thread):**

- **`create-next-app@latest` now installs Next.js 16 (16.2.6) + React
  19.2.4**, not Next 15. AGENTS.md, README, and PROJECT_PLAN still say
  "Next.js 15"; the ticket said use `@latest`, so 16 is what shipped. Those doc
  references should be reconciled (PM-thread territory). Next 16 uses Turbopack
  for `next build` by default and carries breaking changes vs. 15 — future
  frontend work should consult the bundled docs in `node_modules/next/dist/docs`.
- **Removed the `frontend/AGENTS.md` + `frontend/CLAUDE.md` stubs** that
  create-next-app now generates. The repo's model is one authoritative root
  `AGENTS.md`; a competing nested `AGENTS.md` is a footgun about which doc is
  canonical. The one useful nugget from the stub is preserved above (Next 16
  breaking changes / bundled docs).
- Filled the leftover `{{PROJECT_NAME}}` placeholder in this file's header
  while adding this entry. `docs/CHANGELOG.md` still carries the same
  placeholder, left for the PM thread / first release cut.
- mypy `strict` is on with no per-module overrides yet. A forward-looking
  `ignore_missing_imports` override for bs4/apscheduler produced an "unused
  section" note (nothing imports them yet), so it was omitted; Phase 2.x adds
  it when those libraries are actually imported.

Acceptance verified locally: `make install` and `make gate` both run clean on
the skeleton (backend ruff/mypy/pytest green; frontend typecheck/lint/build
green), and the four subpackages import cleanly. CI on the PR is the remaining
check.
