# foghorn — Agent Onboarding

You are working on foghorn, a Bay Area local music & jazz show aggregator that scrapes venue calendars and surfaces shows filtered by region, performer, and a personal friend-watchlist. The team is small: one user, a PM thread for strategy and doc maintenance, coding agents that pick up work from the work tracker (GitHub Issues by default — the tracker is pluggable; see `docs/TRACKER.md`) or from ad-hoc dogfooding, and zero or more domain-agent roles described below. The "Roles and iteration loops" section below describes who does what and how work moves through the system; read that first if you're new to the repo. "Where things live" lists the canonical docs.

## Roles and iteration loops

Two dev-side roles operate on this repo, with clear handoffs. Project-specific domain-agent roles (if any) are described after them.

### PM thread

A long-running agent conversation that handles strategy, spec / ticket production, status sweeps, doc maintenance, and validation against the running app via any project-specific tooling. Reads from the local filesystem and the live system for verification. Doesn't write code, doesn't merge non-doc PRs.

For a fresh PM thread starting cold, see `docs/PM_THREAD_BOOTSTRAP.md` for the first-session reading list and project-specific strategic context.

**Edit policy.** The PM thread writes to repo files **only through the GitHub API** (`create_branch` → `push_files` → `create_pull_request` → `merge_pull_request`). Specifically, **do not use** local-filesystem write tools on anything under the repo — those tools write to the user's local clone, which is a live working directory where coding agents or the user may be operating at any time. Filesystem writes leave uncommitted edits there, which confuse `git status` for whoever is working in that tree and can conflict on `git pull` if anything else has touched those files. Reads through local-filesystem tools are fine; writes go through the GitHub API.

**Loop.** Read state (PROJECT_PLAN, recent PRs via GitHub access, live data via project-specific tooling) → identify gap or design question → propose / discuss with user → if the next step is work, file a ticket in the work tracker (a GitHub Issue by default; see `docs/TRACKER.md`) with a complete ticket body (Why / Scope / Acceptance / Test plan / Not in scope / When you ship) → coding agent picks it up. For doc-only changes (PROJECT_PLAN updates, SHIPPED.md compaction, AGENTS.md edits), the PM thread opens its own PR via the API workflow above and auto-merges once green.

### Coding agents

Agents that pick up work and ship via PRs. Two work sources:

1. **The work tracker** (GitHub Issues by default) — the PM thread queues tickets here. The ticket body is the spec; pick one matching the agent's scope.
2. **Ad-hoc dogfooding** — running the app surfaces friction or correctness bugs; the coding agent files a small precision-fix PR directly without going through an issue first.

**Claim signal.** Claiming is an *optimistic-concurrency protocol*, not a single label. Adding a label is idempotent and non-atomic, so two agents can both read an issue as unclaimed, both add the `claimed` label (both adds "succeed," neither gets a "you lost" signal), and both work the same issue. Making a double-claim *visible* isn't enough — you also need a deterministic way to resolve the race. Since the tracker offers no compare-and-swap on labels, the protocol is claim → re-read → fixed-rule tiebreak:

1. **Identity.** At startup each agent generates a short random id (e.g. `a7f3`), stable for its session, and uses it in every claim.
2. **Stake the claim.** Confirm the issue has no winning claim (per step 3), then post a claim comment — `claim: <agent-id> @ <ISO-8601 timestamp>` — and add the `claimed` label. The comment is the authoritative ownership record; the label is just an at-a-glance filter.
3. **Re-read before starting.** Wait ~30–60s, re-fetch the issue's comments, and apply **earliest claim wins** (tiebreak: timestamp, then lowest comment id). The winner proceeds; everyone else posts `release: <agent-id>` and picks another ticket. **The re-read plus deterministic tiebreak is the part that makes this safe — don't simplify it back to just adding a label.**
4. **Respect winning claims.** Don't pick up an issue with a winning, un-released claim unless the human lead says to take over (e.g. the previous agent is stuck or was told to stop).
5. **Release on abandon.** If you stop without merging, post `release: <agent-id>` and drop the `claimed` label if no other claim remains. Closing via `Closes #N` on PR merge removes the issue from the pool naturally.

Identity lives in the claim *comment* because when all agents authenticate as the same git-host user, the assignee field can't tell them apart. If your setup gives each agent a distinct tracker account, the assignee field becomes a viable claim record instead — and some trackers (e.g. Linear) collapse the whole race into a single native field; see `docs/TRACKER.md`. Ad-hoc dogfooding PRs skip claiming entirely since there's no issue to claim.

**Coding agents work in an isolated git worktree off `main` by default — set one up before starting, every time, and do not begin work in the user's main working tree.** The shared main tree is single-HEAD: concurrent `git checkout`s in it collide, and a branch switch under another agent can land your commit on the wrong branch or leave their work stranded. The main tree is a narrow exception, used only when you're certain you're the only agent active *and* the user has explicitly asked you to work there directly; in that case the working tree may be dirty between iterations by design — don't clean up aggressively.

**Worktree placement and teardown.** Prefer your runtime's managed worktree location when it has one (Claude Code, for example, keeps its worktrees under `.claude/worktrees/` inside the repo and prunes unchanged ones automatically). If you create a worktree manually, put it under a single dedicated parent directory — not as an ad-hoc sibling of the repo, and never under `/tmp`, where directories get reaped unpredictably while their registrations live on. When the work has merged or is abandoned, tear the worktree down with `git worktree remove <path>` and delete the merged branch — deleting the directory by hand strands a stale registration that `git worktree list` keeps reporting. `git worktree prune` clears stranded registrations; a locked one needs `git worktree unlock` first.

**Loop.** Find an open issue (skip ones with a winning claim) or notice a friction → claim it per the claim-signal protocol above (stake, then re-read tiebreak) → set up an isolated worktree (the default — see the workspace rule above) → implement → run the full lint / type / test gate before every commit (project-specific — see Commands below) → push atomic commits (`git add` by file name, not `-A`) → open a PR that resolves the ticket on merge (GitHub: `Closes #N` in the description; other trackers map this differently — see `docs/TRACKER.md`) → auto-merge the PR once CI is green → refresh the live test deployment: `fleet sync foghorn` (see **Live test deployment (fleet)** below).

**Ship-time docs convention.** In the same PR that lands the feature, append the as-shipped narrative to `docs/SHIPPED.md` as a new section, and collapse the corresponding entry in `docs/PROJECT_PLAN.md` to a one-line `✅ Shipped <month year> — see [anchor](SHIPPED.md#anchor)` reference. Two files instead of one, same atomicity. **Don't restructure other docs** — cross-doc reorganization, compaction passes, and AGENTS.md edits are the PM thread's job, not the shipping agent's.

**Auto-merge.** Coding agents auto-merge their own PRs once CI is green. Adjust if your project requires manual review.

### Domain agent(s)

**Show concierge.** Operates foghorn on the user's behalf through the MCP server (`backend/src/foghorn/mcp/server.py`): answers "what's worth catching this week," maintains the performer and venue watchlists, and hand-enters shows the scrapers miss. System prompt and tool surface: `docs/show_concierge/SYSTEM_PROMPT.md`.

The website remains foghorn's primary surface. The concierge is a conversational surface over the same data, so its job is selection rather than enumeration — the reason to ask it instead of browsing is that it narrows.

**Write tiers.** The distinction is load-bearing and the role doc enforces it:

- **Personal** — `add_watchlist_performer`, `remove_watchlist_performer`, `watch_venue`, `unwatch_venue`. User-scoped, idempotent on the canonical form, trivially reversed. Applied on clear intent with an echo-back, no confirmation round-trip.
- **Global** — `add_event`, `remove_event`, `set_event_type`, `clear_event_type`. Admin-scoped and visible to every user. These require explicit user confirmation, with the exact values stated, before being applied.

The server exposes no dry-run and no undo, so that confirmation discipline is the only safeguard on global writes. If undo lands later, revisit this.

**Known gap.** `scraped_at` is persisted per the lineage convention below, but is not projected into the MCP row shape — so the concierge cannot assess listing freshness the way the website can. The role doc instructs it to cite `source_url` and never assert currency. Worth closing if "why does foghorn say this" should hold on the conversational surface too.

## Where things live

- `docs/PROJECT_PLAN.md` — **canonical source for current status**: what's shipped, in flight, queued, and deferred. The strategic narrative: phases, dependencies, sequencing, blockers. Shipped items are collapsed to one-line status pointers; the full as-shipped detail lives in SHIPPED.md. If you need to know "where is foghorn now?" the answer lives here, not in this file.
- `docs/SHIPPED.md` — chronological history of completed work. Each entry preserves the as-shipped narrative as scar tissue (why-it-was-done context that informs new work). Read on demand when scoping similar work; not a daily-read file.
- `docs/CHANGELOG.md` — indexed version history. One section per release tag, with anchor links into SHIPPED.md. Cut at release events per `RELEASE_PROCESS.md`.
- `docs/RELEASE_PROCESS.md` — release cadence (event-triggered) + version policy (semver-locked) + the ritual the PM thread runs each release. Read once to internalize; reference at release-cut time.
- `docs/PM_THREAD_BOOTSTRAP.md` — bootstrap procedure for a fresh PM thread starting cold. Reading list, live-system sanity check, project-specific strategic context.
- `docs/TRACKER.md` — tracker adapter. The five operations the working model needs from a work tracker, mapped to GitHub Issues (default) and Linear. Read the section for your tracker; you don't need both. foghorn uses GitHub Issues as-default; no extra configuration required.
- `docs/SETUP.md` — environment configuration: repo + GitHub PAT + label creation + filling in template placeholders. One-time setup reference.
- `docs/EXAMPLES.md` — worked examples (issue ticket, SHIPPED entry, PROJECT_PLAN phase) drawn from a real project, with annotations on shape.
- `backend/README.md` — authoritative reference for the backend's data model (shows, venues, performers), scraper interface, ingest pipeline, and API surface.
- **The work tracker** — where work items live (GitHub Issues by default; pluggable — see `docs/TRACKER.md`). Tickets are queued / claimed / resolved; the ticket body is the spec; a merged PR resolves its ticket. The default GitHub-Issues mechanics use labels + `Closes #N` (see the **GitHub Issue Labels** section below); Linear and other trackers map the same operations to native fields and PR linking.

## Project Shape

Two-package monorepo, both in the repo root:

- `backend/` — Python 3.11+. FastAPI for the HTTP surface, stdlib `sqlite3` for storage, per-venue scrapers in `backend/scrapers/<venue_slug>.py` plus a separate aggregator-tier that runs after them. Scraping primarily with `httpx` + `beautifulsoup4`; `playwright` reserved for venues that require it (JS-rendered calendars or anti-bot challenges). Daily scrape scheduled via a small in-process scheduler (APScheduler) when the backend is the long-running process; switch to cron / systemd timer if/when we add a separate worker.
- `frontend/` — Next.js 16 + React 19 + TypeScript + Tailwind. Server components fetch from the backend API; client components for filtering / search interactivity. No database / auth in the frontend itself.

See `backend/README.md` for the data-model + storage details. **Current phase status, in-flight work, and deferred items live in `docs/PROJECT_PLAN.md`** — don't infer them from anything in this file.

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

Root `Makefile` wraps both halves: `make gate` runs backend then frontend; `make backend-gate` / `make frontend-gate` run the halves individually; `make install` installs both sides' deps.

## Live test deployment (fleet)

The foghorn instance Diego actually uses — laptop and phone via Tailscale — is not served from any working tree. It runs under PM2 from a detached serve worktree at `~/fleet/serve/foghorn`, managed by the fleet CLI (github.com/diegoSQK/fleet): API on **:8100**, web on **:3100**, pointed at the fleet-owned DB at `~/fleet-data/foghorn/foghorn.db` via `FOGHORN_DB_PATH`, set in fleet's `ecosystem.config.js`. The DB deliberately lives outside `~/Documents` (PM2 runs under launchd, where reads of protected folders silently fail) and outside the fleet repo itself, so it survives a re-clone. The root `Makefile` defaults every DB-writing target to that same path — keep them in agreement: if a CLI writer and the API disagree nothing errors, because `repo/db.py`'s `connect()` runs `init_schema()`, so a wrong path silently creates a fresh empty DB and forks the data.

- **After your PR merges, run `fleet sync foghorn`** — deploys `origin/main`, reinstalls deps only if lockfiles/pyproject changed, rebuilds the frontend (`next build` — the web process runs `next start`, not `next dev`), restarts both processes. Idempotent and conflict-free; this is the last step of shipping.
- **To demo unmerged work:** push your branch, then `fleet preview foghorn <branch>`; `fleet sync foghorn` returns the deployment to main.
- **Never edit files under `~/fleet/serve/`** — serve trees change only via the fleet CLI.
- Ad-hoc dev runs from a working tree must not bind :8100/:3100 — use alternate ports (fleet port + 1000). Check `~/fleet/PORTS.md` before binding anything; something off? Run `fleet doctor` first.

## Architecture Debugging Map

When a show is wrong (missing, duplicated, mis-attributed, wrong time), inspect in this order:

1. **The venue scraper** — `backend/scrapers/<venue_slug>.py`. Run it standalone (`python -m foghorn.scrapers.<venue>`) and inspect its raw output. 90% of show-data issues originate here (venue changed their markup, calendar paginated, performer name embedded in a non-obvious element).
2. **The ingest pipeline** — `backend/src/foghorn/ingest/pipeline.py`. Where scraper output is normalized (timezone, performer-name canonicalization) and deduped against existing rows. Wrong-time / duplicate issues that survive (1) live here.
3. **The repository / storage layer** — `backend/src/foghorn/repo/shows.py`. Persists normalized shows. Schema-shape problems and "missing because never written" issues live here.
4. **The API view layer** — `backend/src/foghorn/api/shows.py`. Filters (date range, region, performer search) applied here. "Show exists in DB but doesn't appear in API response" issues live here.
5. **The frontend page** — `frontend/app/page.tsx` (and sub-routes for filter views). Rendering / formatting / display-timezone issues live here.

## Conventions

- **Show identity.** Natural key is `(venue_id, start_local_date, start_local_time, headliner_canonical)`. Deduping uses this; scraper re-runs are idempotent.
- **Time handling.** All show times stored as UTC (`start_utc`) plus the venue's local date + time (`start_local_date` / `start_local_time`) in the venue's IANA tz (`America/Los_Angeles` for all current venues, but the column exists for future flexibility). Display always renders in the user's local timezone, defaulting to `America/Los_Angeles`. The ingest pipeline applies venue tz via stdlib `zoneinfo` to compute `start_utc` from the scraper's naive local datetime.
- **Performer names — display vs. search.** Store both: `display_name` is the venue's original string ("Joshua Redman Quartet"); `canonical_name` is the NFKD-stripped / lowercased / punctuation-as-separator form used for free-text and watchlist matching ("joshua redman quartet"). Never overwrite the display string; never search the display string.
- **Scraper output is typed.** Each scraper returns `list[ScrapedShow]`, a frozen Pydantic model with required fields (venue_slug, headliner_raw, support_raw, start_local, doors_local?, ticket_url?, price_text?, source_url). Optional fields are explicit `None`, not missing.
- **Scrapers are independently runnable.** `python -m foghorn.scrapers.<venue>` prints structured output and exits. No DB write side effects in the scraper module itself — that's the ingest pipeline's job.
- **Source-of-truth lineage.** Every persisted show row carries `source_url` and `scraped_at`. If anyone asks "why does foghorn say this," the answer is one click away.

## GitHub Issue Labels

*The labels below are the GitHub-Issues mechanism for triage and coordination. On a tracker with native fields (e.g. Linear), the equivalents aren't labels — see `docs/TRACKER.md` for the mapping.*

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

- `claimed` — an at-a-glance filter showing an issue has an active claim. It is **not** the authoritative ownership record — the `claim: <agent-id> @ <timestamp>` comment is, because label-adds are idempotent and non-atomic and so can't resolve a two-agent race. See Coding agents → **Claim signal** for the full optimistic-concurrency protocol (identity → stake → re-read tiebreak). Don't pick up an issue with a winning, un-released claim unless the human lead says to take over. Ad-hoc dogfooding PRs skip this label since there's no issue to claim.

The complete current set is whatever `gh label list` returns; the categories above are stable. New labels added on demand follow the same `dimension:value` shape (`priority:p0`, `type:phase`, etc.) for parseability — e.g. `area:backend`, `area:scraper`, `status:blocked`.

## Git Hygiene

- Commit atomically. `git add` by file name rather than `-A` — secrets and local artifacts can sneak in otherwise.
- Force-push only on feature branches you own — never on shared branches like `main`. Never `git reset --hard` without an explicit ask. Never skip hooks.
- The working tree can be dirty during iterative sessions by design — don't clean up aggressively.
