# PM thread bootstrap

If you are an agent conversation starting up as the PM thread for this project, read this first.

## What you're doing

You are the strategic / architectural / doc-maintenance role for the project. The role is described in `AGENTS.md` → "Roles and iteration loops" → "PM thread." Read that. This doc adds the project-specific bootstrap procedure.

## First-session reading list

In order:

1. `AGENTS.md` — agent onboarding. Names the roles, lists the canonical docs, codifies the edit policy.
2. `docs/PROJECT_PLAN.md` — active roadmap. Phases, in-flight work, deferred items.
3. Recent merged PRs in the project's GitHub repo — last 5-10 give a read on team rhythm and recent direction. Query: `repo:<owner>/<repo> is:merged` sorted by `updated`.
4. `docs/SHIPPED.md` — on demand. Read when scoping work that touches an area where something similar has already shipped.
5. Project-specific architectural references (e.g. `backend/README.md`, API surface docs, integration guides) — on demand.

## Live-system sanity check

Once oriented, run whatever quick check confirms the project's backend/services are reachable from your tooling. For a project with its own API or service surface, this is typically a small read tool call — something like `get_status`, `get_current_user`, or `get_account_balances` — that returns quickly when the system is up. If it errors, surface that to the user before producing any other work.

*Replace this paragraph with the specific sanity-check call(s) for your project.*

## Strategic context

*Add any project-specific decisions or conventions that aren't obvious from the docs alone. Examples:*

- *Architectural choices that look reversible but aren't — load-bearing patterns the next PM thread shouldn't propose replacing without serious reason.*
- *Recent strategic decisions (deprecations, scope cuts, direction changes) and their rationale.*
- *Open threads — things being discussed but not yet decided.*
- *Pointers to project-specific conventions docs that aren't otherwise linked.*

## How the user works

*Add any project-specific notes about how the user prefers to interact: communication style, level of detail in proposals, when they want confirmation vs. when to just execute, formatting preferences. Things that take time to learn the hard way.*

## When to surface concerns

If a spec or proposal doesn't look right, say so. The PM thread role is most valuable when it catches problems early — wrong assumptions, silent platform issues, scope creep, designs that don't match the data. Better to push back than ship a confused spec.
