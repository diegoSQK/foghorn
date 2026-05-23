# PM thread bootstrap

If you are an agent conversation starting up as the PM thread for foghorn, read this first.

## What you're doing

You are the strategic / architectural / doc-maintenance role for foghorn. The role is described in `AGENTS.md` → "Roles and iteration loops" → "PM thread." Read that. This doc adds the project-specific bootstrap procedure.

## First-session reading list

In order:

1. `AGENTS.md` — agent onboarding. Names the roles, lists the canonical docs, codifies the edit policy.
2. `docs/PROJECT_PLAN.md` — active roadmap. Phases, in-flight work, deferred items.
3. Recent merged PRs in `diegoSQK/foghorn` — last 5–10 give a read on team rhythm and recent direction. Query: `repo:diegoSQK/foghorn is:merged` sorted by `updated`.
4. `docs/SHIPPED.md` — on demand. Read when scoping work that touches an area where something similar has already shipped.
5. `backend/README.md` *(once it exists)* — authoritative reference for the data model (shows, venues, performers), scraper interface, ingest pipeline, and API surface.

## Live-system sanity check

Once oriented, confirm the backend is reachable from your tooling. Concretely:

- Hit `GET /api/health/scrape` on the running backend. It should return `last_run_at`, per-venue counts, and any per-venue errors from the last nightly scrape.
- Spot-check `GET /api/shows?venue=sfjazz&from=<today>&to=<today+7d>` — should return a small list of upcoming shows. If it returns zero shows for the next week, that's a strong scraper-health signal worth surfacing to the user before producing other work.

If neither endpoint exists yet (pre-Phase 2.1), skip this step and confirm instead that the latest CI run on `main` is green — that's the closest equivalent for a project that doesn't have a live API surface yet.

## Strategic context

Worth knowing before proposing changes:

- **The four-jazz-venues MVP is load-bearing.** SFJAZZ, Keys Jazz Bistro, Bird & Beckett, Mr. Tipple's are the primary user's actual usage pattern, not a generic "starter set." Proposals to swap them out or de-prioritize them in favor of broader coverage should be argued for explicitly. Rock / indie venues come in Phase 5; jazz is the v0.1 product.
- **Hand-rolled scrapers first, LLM extraction later.** This was an explicit decision (not a default). LLM-assisted scraping is queued for Phase 6, after the hand-rolled approach has proven the model on ~10 venues. Don't propose flipping the order without a concrete reason that the hand-rolled path is failing.
- **Travel ETAs are deferred, not abandoned.** Original requirement, intentionally pushed to a later phase to avoid premature commitment to a map provider. Unblock condition is in `docs/PROJECT_PLAN.md` → "Deferred / still-outstanding."
- **Public-facing eventually, but local-first now.** Phases 1–5 run on the user's laptop. No hosting decision, no auth, no multi-user shape. Don't prematurely introduce account abstractions; single-tenant SQLite assumptions are fine until Phase 9+.
- **Performer-name normalization is the data-model spine.** The watchlist (Phase 4) hinges on it; if you're touching performer storage or matching, read the `Conventions` section of `AGENTS.md` first and don't quietly change the display/canonical split.

## How the user works

Diego (the user) prefers:

- **Surface concerns early.** If a spec or proposal looks off — wrong assumption, silent platform issue, scope creep, design that doesn't match the data — say so before producing more work. The PM thread's value is highest when it catches problems before tickets get filed.
- **One bundled decision per round.** When clarifying scope, batch related questions into a single round rather than drip-feeding. The `AskUserQuestion` tool exists for exactly this.
- **Concrete defaults with recommendations.** When offering options, name a recommended one and say why, rather than presenting a neutral menu.
- **Vendor-agnostic phrasing in the docs.** The template's `main` branch was chosen (not `claude`) — keep generic capability descriptions in `AGENTS.md` and PROJECT_PLAN rather than naming Claude Code / Cowork / specific MCP tools.

## When to surface concerns

If a spec or proposal doesn't look right, say so. The PM thread role is most valuable when it catches problems early — wrong assumptions, silent platform issues, scope creep, designs that don't match the data. Better to push back than ship a confused spec.
