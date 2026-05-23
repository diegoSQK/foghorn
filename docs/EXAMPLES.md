# Examples

Worked examples of the template's three core artifacts: a GitHub Issue ticket, a `SHIPPED.md` entry, and a `PROJECT_PLAN.md` phase block. All three are drawn from a real project ([ficycle](https://github.com/diegoSQK/ficycle), a personal-finance app) that uses this template. The specific domain doesn't transfer to your project but the structure does — use these as shape references for your own work.

---

## Example: GitHub Issue ticket

Filed by the PM thread as a GitHub Issue. The coding agent reads the body as the spec.

**Title:** MCP.1 — Fund composition writes via MCP

**Labels:** `priority:p1`, `type:mcp-parity`

**Body:**

```markdown
## Why

The MCP surface exposes `get_fund_compositions` but not the write
endpoints, so the PM thread (and any conversational client) can inspect
compositions but can't fix them. Today's Phase 2.4 verification pass
ran into exactly this: gate + divergence diagnostic shipped, but the
read-only MCP can't exercise either via a write call. Closes the
inspect-iterate loop established by goals (Phase 4.2) for the fund
look-through domain.

See `backend/README.md` → "MCP Server (AI Plugin)" → "Surface principle"
for the framing.

## Scope

Add three MCP tools wrapping the existing REST surface in
`backend/src/portfolio_api/api/funds.py`:

1. **`get_fund_composition_for_symbol(symbol: str, user_id: int | None)`**
   wraps `GET /api/v1/funds/compositions/{symbol}`. Returns the
   composition (user override if present, else the built-in default,
   else 404).

2. **`upsert_fund_composition(symbol: str, weights: list[CompositionComponent], note: str | None, user_id: int | None)`**
   wraps `PUT /api/v1/funds/compositions/{symbol}`. Returns the saved
   composition view (Phase 2.4 `diagnostics` field included). On
   rejection, surfaces the typed `fund_composition_weight_sum_out_of_range`
   body via the MCP error path so the caller gets the actual sum and
   bounds in `details`.

3. **`delete_fund_composition(symbol: str, user_id: int | None)`** wraps
   `DELETE /api/v1/funds/compositions/{symbol}`. Returns
   `{"deleted": true, "symbol": "..."}` on success; surfaces 404
   typed-body when no user override exists for the symbol.

`CompositionComponent` should mirror the REST request body shape. Match
whatever Pydantic shape the REST endpoint accepts; don't invent a
parallel taxonomy.

User scoping follows the established pattern: optional `user_id: int`
parameter that overrides the env default for the call.

## Acceptance

- Calling `upsert_fund_composition("XYZ", [...weights summing to 0.85])`
  surfaces the typed `fund_composition_weight_sum_out_of_range` error
  with `weight_total: "0.85"`, `min: "0.99"`, `max: "1.01"` in details.
- Calling `upsert_fund_composition("SPY", [{kind: "asset_class",
  value: "us_equity", weight: 0.97}, {kind: "asset_class", value:
  "cash", weight: 0.03}])` succeeds and the response carries
  `fund_composition_diverges_from_default` diagnostics on `us_equity`
  and `cash`.
- Calling `get_fund_composition_for_symbol("VTI")` returns the built-in
  default; calling on a user-authored override returns that one.
- Calling `delete_fund_composition` on a user override deletes it.
- User scoping: passing `user_id` targets the right user's compositions
  and doesn't leak across users.

## Test plan

- `tests/test_mcp_funds.py` (new): one test per tool covering the
  acceptance criteria above. Drive the MCP tool layer directly the way
  existing MCP tests do.
- Full `pytest` gate green.
- Update `backend/README.md` MCP surface list with the new tools.

## Not in scope

- Bulk-upsert of multiple compositions in one call.
- A peer-divergence MCP query helper.
- Composition history / audit log over MCP.

## When you ship

Per the doc convention in `AGENTS.md`: append the as-shipped narrative
to `docs/SHIPPED.md` (e.g. "MCP fund composition writes (MCP.1)"). In
`docs/PROJECT_PLAN.md`, collapse the `#### MCP.1` entry in the "MCP
surface parity" section to a one-line `✅ Shipped <month year> — see
[anchor](SHIPPED.md#anchor)` reference.
```

**Notes on the shape:**

- **Why** is a paragraph of context. Names the gap the work fills and (optionally) what surfaced it. The PR description often references back to it.
- **Scope** is concrete and granular. Numbered list of what to build, with signatures or shape sketches.
- **Acceptance** is testable. Each bullet is a check the agent runs to verify the work meets spec.
- **Test plan** is the gate the agent commits to running. Forces explicit thinking about how the work gets verified.
- **Not in scope** is as important as in-scope. Prevents scope creep and clarifies what's deferred.
- **When you ship** spells out the ship-time docs convention so the agent doesn't have to look it up.

---

## Example: `SHIPPED.md` entry

Appended to the top of the recent-ships block by the agent that lands the work, in the same PR that lands the feature.

```markdown
## MCP fund composition writes (MCP.1, May 2026)

Three new MCP tools wrapping the existing REST surface in
`api/routes/funds.py`, closing the inspect-iterate loop for the fund
look-through domain. Same pattern goals (Phase 4.2) established for
its own surface: read, propose, write, verify without leaving the
conversation. First issue picked up under the GitHub-Issues-driven
coding flow (closes #91).

- `get_fund_composition_for_symbol(symbol, user_id?)` wraps
  `GET /api/v1/funds/compositions/{symbol}`. Returns the resolved
  composition: user override if present, else built-in default, else
  404. Response carries the Phase 2.4 `diagnostics` field unchanged.
- `upsert_fund_composition(symbol, components, as_of_date?, note?,
  user_id?)` wraps `PUT /api/v1/funds/compositions/{symbol}`. On
  weight-sum rejection, catches `httpx.HTTPStatusError` for the typed
  Phase 2.4 body and returns `{"error": detail}` so the LLM caller can
  read structured fields without parsing an exception message. Other
  4xx re-raise so genuine bugs aren't silently swallowed.
- `delete_fund_composition(symbol, user_id?)` wraps
  `DELETE /api/v1/funds/compositions/{symbol}`. Returns
  `{"deleted": True, "symbol": ...}` on success. Built-in defaults are
  not deletable; attempting to delete a symbol with no user override
  404s, which the MCP layer surfaces rather than masks.

User scoping follows the established pattern: optional `user_id: int`
parameter on each tool overrides the `FICYCLE_MCP_USER_ID` default for
that single call.

Tests: `tests/test_mcp_funds.py` — one per acceptance criterion, plus
a regression test that confirms non-typed 400s still raise. Uses an
extended mock-transport helper that accepts `(status_code, body)`
tuples so the typed-400 case can be exercised without spinning up
uvicorn.

Surface-doc update: split the `Snapshot tools` bullet in
`backend/README.md` § "MCP Server (AI Plugin)" — `get_fund_compositions`
moved into a dedicated `Fund compositions` bullet alongside the three
write tools, symmetric with the existing `Goals (Phase 4.2)` bullet.
```

**Notes on the shape:**

- **Heading** is `## <Name> (<identifier>, <Month Year>)`. Both the version identifier (e.g. "MCP.1") and date matter — the identifier maps back to PROJECT_PLAN; the date orders chronologically.
- **Opening paragraph** frames what shipped and why (often a condensed version of the ticket's Why). Names the PR-closing issue.
- **Bulleted detail** captures technical decisions and gotchas the shipping agent learned. This is the scar-tissue value — six months later, another agent reading this knows the design rationale and edge cases.
- **Tests block** at the end names the test files and any clever helpers, so future maintenance can find the test coverage.
- **Surface-doc update note** captures companion edits in other docs.

The narrative is intentionally detailed. Six months from now, the value of SHIPPED.md is the depth of what's preserved.

---

## Example: `PROJECT_PLAN.md` phase block

A phase in the active roadmap. This is a cross-cutting phase (P1, not numbered like Phases 1–8) bundling related work. Mix of shipped (collapsed to one-line pointers) and queued (with detail).

```markdown
### MCP surface parity (cross-cutting, P1)

The architectural principle lives in `backend/README.md` → "MCP Server
(AI Plugin)" → "Surface principle." Briefly: MCP is the analytical and
conversational surface; operational endpoints (auth flows, syncs, CSV
imports) stay REST-only. Within the analytical surface, MCP should
reach REST parity on writes wherever there's a coherent inspect-
iterate loop.

Current coverage: full parity on goals (Phase 4.2's reference shape),
fund compositions (MCP.1), and all analytics endpoints. Read-only on
tracked-assets, cash-flow categorization, and account metadata — writes
go via REST only. Three operational domains are explicit non-goals.

#### MCP.1 Fund composition writes ✅

Shipped May 2026 — see
[MCP fund composition writes](SHIPPED.md#mcp-fund-composition-writes-mcp1-may-2026).

#### MCP.2 Cash-flow categorization writes

`patch_cash_flow_transaction`, `bulk_categorize_transactions`,
`reclassify_cash_flow`, `match_cash_flow_transfers`. Pairs with the
existing `get_uncategorized_merchants` and `list_cash_flow_transactions`
to close the inspect-iterate loop on transaction categorization.

#### MCP.3 Held-funds with resolved composition

Today `get_fund_compositions` appears to return user-authored overrides
only — defaults that silently apply to held tickers don't surface in
the response. The tool description claims defaults are included; the
response shape disagrees. Either extend `get_fund_compositions` to
include default-matched held funds, or add a `get_held_funds_resolved`
tool. Pick one as canonical; update the tool description.

#### MCP.4 Tracked-assets writes

`add_tracked_asset`, `remove_tracked_asset`, `sync_tracked_asset`.
Completes write symmetry for an existing read-only domain.

#### MCP.5 Account metadata writes (selective)

`set_account_tax_treatment`, `set_account_active_contributions`.
Manual account create/update stays UI-only — formalize that as a
non-goal in the MCP surface principle when this ships.

#### Cleanup

- Rename `get_return_covariance_inputs` → `get_optimizer_inputs` to
  match the REST path. One-release deprecation alias for the old name.
- Audit legacy endpoints — confirm they're still in use or remove.
- Surface-list housekeeping on `backend/README.md` as items ship.
```

**Notes on the shape:**

- **Phase intro** explains the framing (the architectural principle, the cross-cutting motivation) and current coverage. Just enough context that a new contributor reading this knows why the phase exists.
- **Shipped items collapse to one-line pointers** with an anchor link into SHIPPED.md. Preserves searchability without bloating PROJECT_PLAN.
- **Queued items get a paragraph of spec** — enough that a coding agent could turn the entry into a ticket without much elaboration. The Why / Scope / Acceptance shape from the ticket is implicit but compressed.
- **Cleanup section** at the end captures small adjacent work that doesn't merit a full sub-item.

When a queued item ships, the agent collapses it from a paragraph to a `✅ Shipped` one-line pointer, in the same PR that ships the feature. PROJECT_PLAN slowly shrinks even as SHIPPED.md grows.

---

## How these three artifacts relate

The lifecycle: **PROJECT_PLAN entry** (queued, paragraph of spec) → PM thread expands into **GitHub Issue ticket** (full body) → coding agent ships **PR closing the issue**, simultaneously **collapsing the PROJECT_PLAN entry** to a one-line pointer and **appending the as-shipped narrative to SHIPPED.md**. Three docs evolve in lockstep; the issue tracker holds the in-flight ticket, the docs hold the strategic narrative and history.

For a new project: seed PROJECT_PLAN with a few phase entries (one paragraph each), write your first ticket modeled on the Example issue above, file it, let the coding agent ship it. After the first PR you'll have a populated SHIPPED.md entry to use as a shape reference for everything that follows.
