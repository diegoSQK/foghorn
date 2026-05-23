# foghorn — Agent Onboarding

You are working on foghorn, a Bay Area local music & jazz show aggregator that scrapes venue calendars and surfaces shows filtered by region, performer, and a personal friend-watchlist. The team is small: one user, a PM thread for strategy and doc maintenance, coding agents that pick up work from GitHub Issues or from ad-hoc dogfooding, and zero or more domain-agent roles described below. The "Roles and iteration loops" section below describes who does what and how work moves through the system; read that first if you're new to the repo. "Where things live" lists the canonical docs.

## Roles and iteration loops

Two dev-side roles operate on this repo, with clear handoffs. Project-specific domain-agent roles (if any) are described after them.

### PM thread

A long-running agent conversation that handles strategy, spec / ticket production, status sweeps, doc maintenance, and validation against the running app via any project-specific tooling. Reads from the local filesystem and the live system for verification. Doesn't write code, doesn't merge non-doc PRs.

For a fresh PM thread starting cold, see `docs/PM_THREAD_BOOTSTRAP.md` for the first-session reading list and project-specific strategic context.

**Edit policy.** The PM thread writes to repo files **only through the GitHub API** (`create_branch` → `push_files` → `create_pull_request` → `merge_pull_request`). Specifically, **do not use** local-filesystem write tools on anything under the repo — those tools write to the user's local clone, which is a live working directory where coding agents or the user may be operating at any time. Filesystem writes leave uncommitted edits there, which confuse `git status` for whoever is working in that tree and can conflict on `git pull` if anything else has touched those files. Reads through local-filesystem tools are fine; writes go through the GitHub API.

**Loop.** Read state (PROJECT_PLAN, recent PRs via GitHub access, live data via project-specific tooling) → identify gap or design question → propose / discuss with user → if the next step is work, file a GitHub Issue with a complete ticket body (Why / Scope / Acceptance / Test plan / Not in scope / When you ship) → coding agent picks it up. For doc-only changes (PROJECT_PLAN updates, SHIPPED.md compaction, AGENTS.md edits), the PM thread opens its own PR via the API workflow above and auto-merges once green.

### Coding agents

Agents that pick up work and ship via PRs. Two work sources:

1. **GitHub Issues** — the PM thread queues tickets here. The issue body is the spec; pick one matching the agent's scope.
2. **Ad-hoc dogfooding** — running the app surfaces friction or correctness bugs; the coding agent files a small precision-fix PR directly without going through an issue first.

**Claim signal.** When picking up a GitHub Issue, add the `claimed` label before starting implementation. This signals to other coding agents that the issue is already being worked — **don't pick up issues already labeled `claimed`** unless the user has explicitly told you to take over (e.g., the previous agent is stuck or has been told to stop). Ad-hoc dogfooding PRs skip this step since there's no issue to claim. Closing the issue via `Closes #N` on PR merge takes it out of the candidate pool naturally; the `claimed` label persists on the closed issue but doesn't matter at that point.

Coding agents may work in isolated git worktrees off `main`, or directly in the user's main working tree. The loop and conventions are the same either way. In the main tree, the working tree may be dirty between iterations by design — don't clean up aggressively.

**Loop.** Find an open issue (skip ones labeled `claimed`) or notice a friction → add the `claimed` label if claiming an issue → set up the workspace (worktree or main tree) → implement → run the full lint / type / test gate before every commit (project-specific — see Commands below) → push atomic commits (`git add` by file name, not `-A`) → open a PR with `Closes #N` in the description when an issue exists (so it auto-closes on merge) → auto-merge the PR once CI is green.

**Ship-time docs convention.** In the same PR that lands the feature, append the as-shipped narrative to `docs/SHIPPED.md` as a new section, and collapse the corresponding entry in `docs/PROJECT_PLAN.md` to a one-line `✅ Shipped <month year> — see [anchor](SHIPPED.md#anchor)` reference. Two files instead of one, same atomicity. **Don't restructure other docs** — cross-doc reorganization, compaction passes, and AGENTS.md edits are the PM thread's job, not the shipping agent's.

**Auto-merge.** Coding agents auto-merge their own PRs once CI is green. Adjust if your project requires manual review.

### Domain agent(s)

None at present. foghorn's surface is the website itself — users browse the show calendar directly rather than talking to an agent. If a "show concierge" role ever makes sense (e.g. "what's happening Friday night in the Mission that one of my watchlist names is playing?"), it'll get its own section here with system-prompt + tool surface in `docs/<role_name>/`.

## Where things live

- `docs/PROJECT_PLAN.md` — active roadmap (in flight, queued, deferred). The strategic narrative: phases, dependencies, sequencing, blockers. Shipped items are collapsed to one-line status pointers; the full as-shipped detail lives in SHIPPED.md.
- `docs/SHIPPED.md` — chronological history of completed work. Each entry preserves the as-shipped narrative as scar tissue (why-it-was-done context that informs new work). Read on demand when scoping similar work; not a daily-read file.
- `docs/CHANGELOG.md` — indexed version history. One section per release tag, with anchor links into SHIPPED.md. Cut at release events per `RELEASE_PROCESS.md`.
- `docs/RELEASE_PROCESS.md` — release cadence (event-triggered) + version policy (semver-locked) + the ritual the PM thread runs each release. Read once to internalize; reference at release-cut time.
- `docs/PM_THREAD_BOOTSTRAP.md` — bootstrap procedure for a fresh PM thread starting cold. Reading list, live-system sanity check, project-specific strategic context.
- `docs/SETUP.md` — environment configuration: repo + GitHub PAT + label creation + filling in template placeholders. One-time setup reference.
- `docs/EXAMPLES.md` — worked examples (issue ticket, SHIPPED entry, PROJECT_PLAN phase) drawn from a real project, with annotations on shape.
- `backend/README.md` *(planned)* — authoritative reference for the backend's data model (shows, venues, performers), scraper interface, ingest pipeline, and API surface. Added in Phase 1 scaffolding.
- **GitHub Issues** — the work-item tracker. Issues are queued/claimed/closed via labels and state. The issue body is the ticket spec; the PR closes the issue on merge via `Closes #N`. See the **GitHub Issue Labels** section below for the label set.

## Project Shape

Two-package monorepo, both intended to live in the repo root:

- `backend/` — Python 3.11+. FastAPI for the HTTP surface, SQLite for storage (Postgres deferred until hosting is decided), per-venue scrapers in `backend/scrapers/<venue_slug>.py`. Scraping primarily with `httpx` + `beautifulsoup4`; reserve `playwright` for venues that require it (JS-rendered calendars). Daily scrape scheduled via a small in-process scheduler (APScheduler) when the backend is the long-running process; switch to cron / systemd timer if/when we add a separate worker.
- `frontend/` — Next.js 15 + React 19 + TypeScript + Tailwind. Server components fetch from the backend API; client components for filtering / search interactivity. No database / auth in the frontend itself.

Neither package is realized yet — see PROJECT_PLAN Phase 1 for scaffolding.

## Current State

Greenfield. Repo bootstrapped from `diegoSQK/agent-team-template` (May 2026). No code shipped yet. Phase 1 scaffolding (backend skeleton, frontend skeleton, CI gate) is the next thing to land; the four-jazz-venue end-to-end milestone follows in Phase 2.

## Commands

Backend gate (run from `backend/`):

```bash
ruff check .
mypy src
pytest
```

Frontend gate (run from `frontend/`):

```bash
npm run typecheck
npm run lint
npm run build  # surfaces type / config issues that lint misses
```

Phase 1 scaffolding ticket pins exact versions and adds these commands to a `Makefile` at the repo root so `make gate` runs both.

## Architecture Debugging Map

When a show is wrong (missing, duplicated, mis-attributed, wrong time), inspect in this order:

1. **The venue scraper** — `backend/scrapers/<venue_slug>.py`. Run it standalone (`python -m backend.scrapers.<venue>`) and inspect its raw output. 90% of show-data issues originate here (venue changed their markup, calendar paginated, performer name embedded in a non-obvious element).
2. **The ingest pipeline** — `backend/ingest/pipeline.py`. Where scraper output is normalized (timezone, performer-name canonicalization) and deduped against existing rows. Wrong-time / duplicate issues that survive (1) live here.
3. **The repository / storage layer** — `backend/repo/shows.py`. Persists normalized shows. Schema-shape problems and "missing because never written" issues live here.
4. **The API view layer** — `backend/api/shows.py`. Filters (date range, region, performer search) applied here. "Show exists in DB but doesn't appear in API response" issues live here.
5. **The frontend page** — `frontend/app/page.tsx` (and sub-routes for filter views). Rendering / formatting / display-timezone issues live here.

## Conventions

- **Show identity.** Natural key is `(venue_id, local_start_datetime, headliner_canonical)`. Deduping uses this; scraper re-runs are idempotent.
- **Time handling.** All show times stored as UTC in the DB with the venue's `IANA tz` (`America/Los_Angeles` for all current venues, but the column exists for future flexibility). Display always renders in the user's local timezone, defaulting to `America/Los_Angeles`.
- **Performer names — display vs. search.** Store both: `display_name` is the venue's original string ("Joshua Redman Quartet"); `canonical_name` is the lowercased / accent-stripped / punctuation-removed form used for free-text and watchlist matching ("joshua redman quartet"). Never overwrite the display string; never search the display string.
- **Scraper output is typed.** Each scraper returns `list[ScrapedShow]`, a frozen Pydantic model with required fields (venue_slug, headliner_raw, support_raw, start_local, doors_local?, ticket_url?, price_text?). Optional fields are explicit `None`, not missing.
- **Scrapers are independently runnable.** `python -m backend.scrapers.<venue>` prints structured output and exits. No DB write side effects in the scraper module itself — that's the ingest pipeline's job.
- **Source-of-truth lineage.** Every persisted show row carries `source_url` and `scraped_at`. If anyone asks "why does foghorn say this," the answer is one click away.

## GitHub Issue Labels

Issues in this repo are triaged along two label dimensions plus a coordination signal. The PM thread applies priority and type at ticket-filing time; coding agents add the `claimed` signal when starting work and typically don't touch priority or type.

**Priority** — what each tier means (the README's `Recommended GitHub Issue labels` table has the color codes used at setup time):

- `priority:p0` — fixes active correctness issues or unblocks high-value work. Drop other work to ship.
- `priority:p1` — meaningfully improves practical usefulness. The strategic-priority queue; pick first when scanning the backlog.
- `priority:p2` — valuable enhancement, can wait.

**Type** — the work-shape category telling a coding agent at a glance what kind of work the ticket asks for:

- `type:phase` — planned roadmap deliverable from `docs/PROJECT_PLAN.md`. Ships something from the plan: a numbered Phase X.Y or a cross-cutting workstream sub-item. The proactive category; strategic queue priority applies directly.
- `type:bug` — production defect fix in already-shipped code. Reactive; may warrant pickup ahead of `type:phase` at the same priority tier when user impact is meaningful.
- `type:cleanup` — polish or refactor without changing functionality. Pickup when there's room between strategic work.
- `type:doc` — doc-only change. Optional; some projects file doc-only tickets, others handle doc changes via PM-thread PRs without an issue and skip this label entirely.

**Coordination signal:**

- `claimed` — a coding agent has started implementation. Don't pick up issues already labeled `claimed` unless the user has explicitly told you to take over (see the Coding agents section above for the full claim flow). Ad-hoc dogfooding PRs skip this label since there's no issue to claim.

The complete current set is whatever `gh label list` returns; the categories above are stable. New labels added on demand follow the same `dimension:value` shape (`priority:p0`, `type:phase`, etc.) for parseability — e.g. `area:backend`, `area:scraper`, `status:blocked`.

## Git Hygiene

- Commit atomically. `git add` by file name rather than `-A` — secrets and local artifacts can sneak in otherwise.
- Force-push only on feature branches you own — never on shared branches like `main`. Never `git reset --hard` without an explicit ask. Never skip hooks.
- The working tree can be dirty during iterative sessions by design — don't clean up aggressively.

## Deferred Workstream

Explicitly deferred to keep early phases focused:

- **Travel-time ETAs from home/work/studio.** Deferred to a later phase. Decision on map provider (Google / Mapbox / ORS / coarse neighborhood lookup) deferred with it.
- **Hosting / deployment.** Phases 1–N run locally. Decision on Vercel + Python host vs. single VPS deferred until the app is usable enough to deploy.
- **Multi-user accounts.** Watchlist is local / single-user-shaped in early phases. Real accounts wait until the app goes public.
- **Alerts / notifications** (email or push when a watchlist performer is announced). Deferred until the watchlist proves valuable in the manual-check shape.
- **Postgres / non-SQLite storage.** SQLite is fine through Phases 1–N at single-user scale. Migrate when hosting requires it.
- **LLM-assisted scraping.** Hand-rolled parsers for the seed venues first; LLM-assisted extraction (with hand-tuned overrides) added in a later phase to scale venue count without per-venue parser work.
- **Mobile app.** Web-first. Native app only if the web experience has obvious mobile-specific friction that responsive design can't solve.
