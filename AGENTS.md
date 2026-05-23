# {{PROJECT_NAME}} — Agent Onboarding

You are working on {{PROJECT_NAME}}, [one-sentence project description]. The team is small: one user, a PM thread for strategy and doc maintenance, coding agents that pick up work from GitHub Issues or from ad-hoc dogfooding, and zero or more domain-agent roles described below. The "Roles and iteration loops" section below describes who does what and how work moves through the system; read that first if you're new to the repo. "Where things live" lists the canonical docs.

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

*Optional. If your project has one or more agent roles that use the running system as a tool to help end-users — e.g. a financial advisor for a finance app, a tutor for a learning platform, a sales assistant for a CRM — describe them here. Each should get a brief description, a Loop, and Conventions. Delete this section entirely if your project doesn't have any.*

*If your domain agent has write access via its tooling, include a confirmation-discipline convention: writes that materially change persisted user state should require explicit user confirmation before being applied. A user talking to a domain agent should always know when their state is changing, not discover it after the fact. Per-role operating instructions (system prompt, tool surface, examples) should live in a dedicated file under `docs/` — e.g. `docs/<role_name>/SYSTEM_PROMPT.md` — that the role's runtime reads.*

## Where things live

- `docs/PROJECT_PLAN.md` — active roadmap (in flight, queued, deferred). The strategic narrative: phases, dependencies, sequencing, blockers. Shipped items are collapsed to one-line status pointers; the full as-shipped detail lives in SHIPPED.md.
- `docs/SHIPPED.md` — chronological history of completed work. Each entry preserves the as-shipped narrative as scar tissue (why-it-was-done context that informs new work). Read on demand when scoping similar work; not a daily-read file.
- `docs/CHANGELOG.md` — indexed version history. One section per release tag, with anchor links into SHIPPED.md. Cut at release events per `RELEASE_PROCESS.md`.
- `docs/RELEASE_PROCESS.md` — release cadence (event-triggered) + version policy (semver-locked) + the ritual the PM thread runs each release. Read once to internalize; reference at release-cut time.
- `docs/PM_THREAD_BOOTSTRAP.md` — bootstrap procedure for a fresh PM thread starting cold. Reading list, live-system sanity check, project-specific strategic context.
- `docs/SETUP.md` — environment configuration: repo + GitHub PAT + label creation + filling in template placeholders. One-time setup reference.
- `docs/EXAMPLES.md` — worked examples (issue ticket, SHIPPED entry, PROJECT_PLAN phase) drawn from a real project, with annotations on shape.
- **GitHub Issues** — the work-item tracker. Issues are queued/claimed/closed via labels and state. The issue body is the ticket spec; the PR closes the issue on merge via `Closes #N`. See the **GitHub Issue Labels** section below for the label set.
- *Project-specific architectural-reference docs: typically a `backend/README.md` or equivalent that's the authoritative reference for the API surface, data model, and other deep technical details. Add others as needed.*

## Project Shape

*TODO: Describe the monorepo layout, package structure, primary languages and frameworks. Example: "Two-package monorepo: `backend/` is FastAPI + SQLite, Python 3.11+; `frontend/` is Next.js 15 + React 19 + TypeScript + Tailwind."*

## Current State

*TODO: Brief summary of what's shipped and what the app currently does. Update as major milestones land. This section is for orientation, not a comprehensive feature list — point at PROJECT_PLAN.md and SHIPPED.md for the detailed view.*

## Commands

*TODO: How to run, test, lint, type-check. The full gate that coding agents run before commits. Project-specific — fill in.*

Example backend gate:

```bash
# Replace with your actual commands
ruff check . --no-cache
mypy src
pytest -p no:cacheprovider
```

Example frontend gate:

```bash
# Replace with your actual commands
npm run typecheck
npm run lint
```

## Architecture Debugging Map

*TODO: When something's wrong, what order to inspect files in. Example:*

*1. The relevant connector / data source*
*2. The ingestion service*
*3. The storage / repository layer*
*4. The display / view service*
*5. The frontend rendering page*

*Fill in with your actual layers.*

## Conventions

*TODO: Project-specific patterns. Examples: monetary precision rules, source-agnostic display, immutable data structures, error handling shape. Add as patterns emerge.*

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

The complete current set is whatever `gh label list` returns; the categories above are stable. New labels added on demand follow the same `dimension:value` shape (`priority:p0`, `type:phase`, etc.) for parseability — e.g. `area:backend`, `status:blocked`.

## Git Hygiene

- Commit atomically. `git add` by file name rather than `-A` — secrets and local artifacts can sneak in otherwise.
- Force-push only on feature branches you own — never on shared branches like `main`. Never `git reset --hard` without an explicit ask. Never skip hooks.
- The working tree can be dirty during iterative sessions by design — don't clean up aggressively.

## Deferred Workstream

*TODO: Things that are explicitly out of scope or deferred. Update as decisions accumulate.*
