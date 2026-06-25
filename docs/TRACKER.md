# Tracker adapter

The working model needs five things from whatever tool tracks work items. `AGENTS.md` describes the loops in terms of these abstract operations; this doc maps each to a concrete tracker. **GitHub Issues is the default. Linear is a first-class, documented swap.** Pick one and read only that section — onboarding never requires reading both.

Tracker choice is independent of agent-runtime choice, so it lives in its own doc: swapping trackers is a one-doc change, and nothing else in the model moves.

foghorn uses **GitHub Issues** as-default. No extra configuration is required; the Linear section is here for documented optionality, not because a swap is planned.

## The five operations

1. **File a ticket** — create a work item whose body is the spec (Why / Scope / Acceptance / Test plan / Not in scope / When you ship).
2. **Triage** — attach priority and type (plus any project-specific dimensions).
3. **Claim** — signal in-progress + ownership so two coding agents don't collide on the same item.
4. **Link work → ticket** — a merged PR resolves its ticket automatically; no manual close.
5. **Query the candidate pool** — list open, unclaimed tickets matching an agent's scope.

## Quick map

| Operation | GitHub Issues (default) | Linear |
| --- | --- | --- |
| File a ticket | `create_issue`, body = spec | `create_issue` (Linear MCP), description = spec |
| Triage | `priority:*` + `type:*` labels | native **Priority** field + issue **label/type** |
| Claim | `claim:` comment + `claimed` label, then re-read tiebreak | **assignee** (single-valued → one winner) if agents have distinct identities; else the same `claim:` comment protocol |
| Link → resolve | `Closes #N` in PR body | `Fixes ENG-123` in PR body or branch name; status auto-advances |
| Query pool | issue search, skip `claimed` | saved view or `list_issues` filter |

## GitHub Issues (default)

Behaves exactly as `AGENTS.md` describes. Triage and coordination ride on labels (`priority:p0/p1/p2`, `type:phase/bug/cleanup/doc`, `claimed`); set them up once via `docs/SETUP.md` § "Set up labels". Claiming uses the optimistic-concurrency protocol in `AGENTS.md` → Coding agents → **Claim signal** (`claim:` comment + `claimed` label + re-read tiebreak), because GitHub offers no compare-and-swap on labels. A merged PR with `Closes #N` in its body auto-closes the issue. Nothing else to configure.

## Linear

**One-time setup.** Connect the official Linear MCP (`mcp.linear.app/mcp`, remote, OAuth) to the PM-thread runtime so it can file and query tickets. Inside Linear, enable the **GitHub integration** (Settings → Integrations → GitHub) so PRs link to and drive issues. Code stays on GitHub; only the tracker moves.

How the five operations work:

- **File / query.** The PM thread calls the Linear MCP — `create_issue` (team + title required; description, priority, assignee, state, labels optional) and `list_issues` to sweep the backlog. The ticket spec goes in the description, same Why / Scope / Acceptance / … shape.
- **Triage.** Use Linear's native **Priority** field (Urgent / High / Medium / Low ≈ the `p0`/`p1`/`p2` tiers) and a label or issue type for `phase` / `bug` / `cleanup` / `doc`. These are structured fields, not parsed label strings.
- **Claim.** The two-agent race exists on any tracker, so a race-safe protocol is still required — but Linear's **single assignee** (one owner per issue, by design) collapses it into one native field *if* your agents have distinct identities:
  - **Distinct agent identities** — separate member seats, or Linear's `actor=app` agent users carrying the `app:assignable` scope (they show up in the assignee dropdown). Set the **assignee** to yourself and move the issue to **In Progress**, then re-read: because the field is single-valued it holds exactly one owner, so if you're no longer the assignee you lost the race — pick another ticket. No `claimed` label, no claim comment, no timestamp tiebreak; the field itself enforces a single winner. The GitHub PR link then advances state (In Progress → In Review → Done) automatically.
  - **Shared identity** — all agents on one OAuth user (the common case). The assignee can't tell them apart, so fall back to the comment protocol exactly as in `AGENTS.md`: `claim: <agent-id> @ <ISO-8601 timestamp>`, re-read, earliest-claim-wins. Native state/assignee still help as filters but aren't the ownership record.
- **Link → resolve.** Put the issue ID in the branch name, or `Fixes ENG-123` / `Closes ENG-123` in the PR body. The integration then advances the issue on its own: **In Progress** when the PR opens → **In Review** on review → **Done** on merge. A per-team setting controls whether merge closes the issue or just moves it to Done.

**What changes vs. GitHub Issues.** With distinct agent identities the `claimed`-label + claim-comment protocol disappears entirely — the single-valued assignee *is* the claim, and the PR link drives state transitions with zero bookkeeping. With shared identity you keep the claim-comment protocol but drop the label (Linear filters by assignee/state instead). Triage labels become native fields either way; the docs system, roles, ship-time convention, and releases are unchanged.

**Free-tier note.** Linear's free plan covers this model (unlimited members, the GitHub integration, the MCP) but caps *non-archived* issues at 250 and omits custom workflows. Closed issues archive out of the count, so a fast-closing agent project stays well under the cap; you're on Linear's default workflow states.
