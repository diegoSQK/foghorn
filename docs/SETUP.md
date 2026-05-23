# Setup

This template is vendor-agnostic. To use it, you need:

1. A GitHub repo spun up from this template.
2. Agent runtimes (PM thread + coding agents) with the required capabilities.
3. GitHub access for the PM thread (Personal Access Token or equivalent).
4. Issue labels configured on the repo.

This guide covers items 1, 3, and 4 — items that are vendor-neutral. For agent runtime setup, see the vendor-specific guides at the bottom (or contribute one for your runtime).

## 1. Spin up your repo

Click **Use this template** on the template repo's page. Choose `main` (vendor-agnostic, default) or `claude` (Claude-specific variant) as the starting branch.

After creating, run the label creation commands (see [Set up labels](#4-set-up-labels) below).

## 2. Required agent-runtime capabilities

The template's working model assumes two agent roles with specific tool access. Whatever runtime you choose, the PM thread and coding agents need these capabilities. If your runtime doesn't expose one of them, you'll need to substitute or work around.

### PM thread

- **Long-running conversation surface** that retains state across many turns within a session. Cross-session continuity is a nice-to-have; if the runtime doesn't support it, `docs/PM_THREAD_BOOTSTRAP.md` handles cold starts.
- **Filesystem read access** to the local repo (for reading project state on demand).
- **GitHub API write access** with scopes `Contents: write`, `Pull requests: write`, `Issues: write`. Optional but useful: `Administration: write` for repo creation via the API.
- **No filesystem write access to the local repo.** Per the AGENTS.md edit policy, the PM thread writes through the GitHub API only — never edits the user's local working tree directly. If the runtime exposes filesystem write tools, AGENTS.md tells the PM not to use them on repo files.

Examples of runtimes that fit:

- **Claude Desktop / Cowork mode** with the github and filesystem MCPs configured (see the `claude` branch's SETUP.md for concrete steps).
- **ChatGPT with code execution + GitHub plugin/tools.**
- **Custom orchestration via the Anthropic API or OpenAI API** with appropriate tool definitions.

### Coding agents

- **CLI or IDE-integrated** runtime with `git`, the project's language toolchain, and shell execution.
- **Filesystem write access** to a git worktree or main working tree.
- **Git access** for branch creation, commits, push, and PR opening (either via the GitHub API or via local `git` CLI + `gh`).
- **Ability to run the project's full lint / type / test gate** before commits.

Examples of runtimes that fit:

- **Claude Code CLI**
- **OpenAI Codex CLI**
- **Aider**
- **Cline / Continue** (VS Code extensions)
- **Cursor's background agents**
- Any agent runtime with shell + git access.

## 3. Set up GitHub access

The PM thread needs a GitHub Personal Access Token (or equivalent OAuth scope set) configured with the right permissions.

### Required scopes

- `Contents: write` — for creating branches and pushing files
- `Pull requests: write` — for opening and merging PRs
- `Issues: write` — for filing tickets

### Optional scopes

- `Administration: write` (account-level for fine-grained PATs) — needed only if the PM thread will create new repos or configure repo settings via API. Otherwise, use the `gh` CLI for these one-time setups.
- `Commit statuses: read` — needed only if the PM thread will pre-check CI before merging. Without this, the PM merges optimistically and GitHub's branch protection (if configured) provides the gate.

### Fine-grained PAT vs. classic

- **Fine-grained PATs** scope tokens per repo. Cleaner permission model per-repo, but you have to explicitly add new repos to the token's selected-repositories list as you create them. Some scope-management gotchas: regenerating an existing token after expanding scopes is sometimes required for the new scopes to take effect.
- **Classic PATs** with the `repo` scope cover everything for any repo in your account. Simpler one-time setup but more blast radius.

For most users I'd recommend classic with `repo` scope unless there's a specific security reason to scope tighter.

## 4. Set up labels

Labels don't transfer when you use a template — they live on the repo itself. Run from your repo's directory (with `gh` CLI authenticated):

```bash
gh label create priority:p0 --color B60205 --description "Active correctness / blocking"
gh label create priority:p1 --color FBCA04 --description "Meaningfully improves practical usefulness"
gh label create priority:p2 --color 0E8A16 --description "Valuable enhancement, can wait"
gh label create type:phase --color 1D76DB --description "Roadmap phase work"
gh label create type:bug --color B60205 --description "Production bug fix"
gh label create type:cleanup --color C5DEF5 --description "Refactor, doc cleanup, tech debt"
gh label create type:doc --color C5DEF5 --description "Docs-only change"
gh label create claimed --color D4C5F9 --description "A coding agent has started work; coordination signal"
```

Add project-specific labels (e.g. `area:backend`, `status:blocked`) as needs become clear.

If any command errors with "already exists," that's fine — it just means the label was created previously.

## 5. Fill in the template

After the structural setup, customize the template content:

1. Edit `AGENTS.md` — replace `{{PROJECT_NAME}}` and the one-sentence description. Fill in the placeholder sections (`Project Shape`, `Current State`, `Commands`, `Architecture Debugging Map`, project-specific `Conventions`, `Deferred Workstream`).
2. Edit `docs/PM_THREAD_BOOTSTRAP.md` — fill in project-specific strategic context, the live-system sanity-check call, and any notes about how the user prefers to work.
3. Seed `docs/PROJECT_PLAN.md` with the initial roadmap (phases, in-flight work, deferred items).
4. Replace `README.md` with your project's README.

## 6. Vendor-specific runtime setup

This template's `main` branch keeps the agent-runtime layer abstract. Concrete setup for specific runtimes lives in vendor-specific guides:

- **Claude users** — switch to the `claude` branch (`git fetch origin claude && git checkout claude`) for concrete Claude Desktop + Claude Code + MCP setup steps in that branch's `docs/SETUP.md`.
- **OpenAI Codex CLI / Aider / other runtimes** — no vendor-specific guide yet. If you set this up against this template, consider opening a PR with a `docs/SETUP_OPENAI.md` (or equivalent) so the next user has a reference.

## 7. Open your first issue

With the template structure in place and labels configured, you're ready to start. Open a GitHub Issue with a complete ticket body (Why / Scope / Acceptance / Test plan / Not in scope / When you ship), apply the appropriate `priority:` and `type:` labels, and direct a coding agent to pick it up.

The coding-agent loop documented in `AGENTS.md` handles the rest: claim the issue, implement, gate, PR, auto-merge.

## Common pitfalls

- **PAT scope changes don't always propagate to existing tokens.** If you expand scopes on a fine-grained PAT and still get 403s, regenerate the token.
- **Fine-grained PATs scoped to "Only select repositories" need updates per new repo.** Easy to forget after creating a new repo.
- **The PM thread should not use filesystem write tools on repo files.** See `AGENTS.md` → "Edit policy" for the failure mode (dirty working tree, `git status` drift, potential `git pull` conflicts).
- **Auto-merge depends on CI being configured.** If your repo has no CI workflow, the coding agent's auto-merge call still works because there are no required status checks. If you add CI later with required checks, the auto-merge call waits until they pass.
