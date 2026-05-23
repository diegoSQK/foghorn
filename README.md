# Agent team template

A working model for building software with a small AI-powered team. Use this template to scaffold a new project with the agent roles, doc structure, and iteration loops already in place.

This branch (`main`) is **vendor-agnostic** — works with any agent runtime that reads `AGENTS.md`-style instructions (Claude Code, OpenAI Codex CLI, Aider, etc.). For a Claude-specific variant with named MCP tools and Cowork-mode references, see the [`claude`](../../tree/claude) branch.

## What's here

- `AGENTS.md` — agent onboarding doc. Names the roles (PM thread, coding agents, optional domain agent), spells out the iteration loops, lists the canonical docs, codifies the edit policy and ship-time conventions. Section placeholders for project-specific content (stack, commands, conventions).
- `docs/PROJECT_PLAN.md` — active-roadmap skeleton. Where strategic phases, in-flight work, and deferred items live. Shipped items collapse to one-line pointers.
- `docs/SHIPPED.md` — chronological-history skeleton. Where as-shipped narratives accumulate as scar tissue.
- `docs/CHANGELOG.md` — indexed version-history skeleton. Cut-points referencing SHIPPED.md entries; one section per release tag.
- `docs/RELEASE_PROCESS.md` — release cadence + version policy + the ritual the PM thread runs each release. Event-triggered, semver-locked.
- `docs/PM_THREAD_BOOTSTRAP.md` — bootstrap procedure for an agent conversation starting up as the PM thread for the project.
- `docs/SETUP.md` — environment configuration walkthrough: spin up the repo, GitHub PAT scopes, label creation, fill in template placeholders.
- `docs/EXAMPLES.md` — worked examples (issue ticket, SHIPPED entry, PROJECT_PLAN phase) drawn from a real project, with annotations on shape.

## The working model in one minute

Two dev-side roles operate on the repo:

- **PM thread** — a long-running agent conversation (with file + tool access — e.g., a Claude Desktop / Cowork session, a ChatGPT session with code execution, or an equivalent) that handles strategy, ticket production, status sweeps, and doc maintenance. Writes through the GitHub API only — never dirties the local working tree.
- **Coding agents** — CLI-based or worktree-based agents (Claude Code, OpenAI Codex CLI, Aider, etc.) that pick up GitHub Issues, work in worktrees or directly in `main`, ship via PRs with `Closes #N`, auto-merge on green CI.

Work flows: PM thread files an issue → coding agent picks it up → ships PR with `Closes #N` → issue auto-closes on merge → ship-time docs convention appends as-shipped narrative to `docs/SHIPPED.md` and collapses the corresponding `docs/PROJECT_PLAN.md` entry.

Most projects also have one or more **domain-agent roles** that use the running system as a tool to help end-users (e.g. a financial advisor for a finance app, a tutor for a learning platform, a sales assistant for a CRM). Describe these in `AGENTS.md` alongside the dev-side roles. Delete the slot if your project doesn't have any.

At natural milestones (phase completes, cross-cutting arc completes, platform bug-class fix lands), the PM thread cuts a release per `docs/RELEASE_PROCESS.md` — versions bump, CHANGELOG.md gets a new entry, the repo gets a git tag. Releases are organizational anchors, not distribution mechanics; the doc-cadence and the tag form the milestone.

## Branch variants

- **`main`** (default) — vendor-agnostic. Generic descriptions of capabilities rather than specific product names. Compatible with any agent runtime that supports the `AGENTS.md` convention.
- **`claude`** — Claude-specific. Names Claude Code, Claude Desktop / Cowork, and the specific MCP tools by name. Use this if you're fully committed to Claude as your agent runtime; provides sharper concrete guidance.

To switch a project to the Claude-specific variant after using the template: `git fetch origin claude && git checkout claude` (or cherry-pick the differences manually).

## Using the template

1. Click **Use this template** to spin up a new repo (uses the default `main` / agnostic branch). To use the Claude-specific variant, after spinning up the repo: `git fetch origin claude && git checkout claude` or manually copy the `claude` branch's contents.
2. Edit `AGENTS.md`:
   - Replace `{{PROJECT_NAME}}` and the one-sentence project description.
   - Fill in the placeholder sections (`Project Shape`, `Current State`, `Commands`, `Architecture Debugging Map`, project-specific `Conventions`, `Deferred Workstream`).
   - Add domain-agent role(s) under “Roles and iteration loops” if relevant; delete the slot otherwise.
3. Replace this README with your project's README.
4. Seed `docs/PROJECT_PLAN.md` with the initial roadmap.
5. Edit `docs/PM_THREAD_BOOTSTRAP.md` to fill in project-specific strategic context, the live-system sanity-check call, and any notes about how the user prefers to work.
6. Set up the recommended GitHub Issue labels (see below).
7. Open your first GitHub Issue and let a coding agent take it.

`docs/SHIPPED.md` fills in as work ships. `docs/CHANGELOG.md` fills in as you cut releases per `docs/RELEASE_PROCESS.md`.

## Recommended GitHub Issue labels

Labels don't transfer when you use a template — they live on the repo itself. After creating your repo, set up these labels to support the agent workflow described above:

| Label | Color | Purpose |
| --- | --- | --- |
| `priority:p0` | red (#B60205) | fixes active correctness issues or unblocks high-value work |
| `priority:p1` | yellow (#FBCA04) | meaningfully improves practical usefulness |
| `priority:p2` | green (#0E8A16) | valuable enhancement, can wait |
| `type:phase` | blue (#1D76DB) | roadmap phase work (e.g. Phase 2.4) |
| `type:bug` | red (#B60205) | production bug fix |
| `type:cleanup` | gray (#C5DEF5) | refactor, doc cleanup, tech debt |
| `type:doc` | gray (#C5DEF5) | docs-only change |
| `claimed` | purple (#D4C5F9) | a coding agent has started work; informal coordination signal |

The `gh` CLI is the fastest way to create them in batch:

```bash
gh label create priority:p0 --color B60205 --description "Active correctness / blocking"
gh label create priority:p1 --color FBCA04
gh label create priority:p2 --color 0E8A16
gh label create type:phase --color 1D76DB
gh label create type:bug --color B60205
gh label create type:cleanup --color C5DEF5
gh label create type:doc --color C5DEF5
gh label create claimed --color D4C5F9
```

Add project-specific labels (e.g. `area:backend`, `type:mcp-parity`, `status:blocked`) as needs become clear.

## Provenance

Distilled from the working model developed for [ficycle](https://github.com/diegoSQK/ficycle), originally on Claude. The conventions evolved across several days of multi-agent collaboration in May 2026; the `main` branch generalizes them to be vendor-neutral, and the [`claude`](../../tree/claude) branch preserves the Claude-specific surface details.
