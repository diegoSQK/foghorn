# Release Process

This project uses an event-triggered release cadence with semver-locked versioning. This doc defines what counts as a release event, the ritual that creates each release, and the semantic version policy.

Releases exist as an organizational anchor — they may or may not also be a distribution mechanism, depending on whether your project ships binaries or packages. The purpose is to make "where are we now?" and "what changed between v0.5 and v0.6?" answerable at a glance.

## What counts as a release event

Cut a release when any of the following lands on `main`:

- A phase or sub-phase completes (e.g., a coordinated set of related issues all merged).
- A coherent cross-cutting arc completes (multiple related items shipped as a set).
- A platform-level bug-class fix lands that changes how something fundamental works.
- A new top-level user-facing surface launches.

Do **not** cut a release for:

- Individual small features that belong with the next coherent set.
- Pure refactors with no behavior change.
- Doc-only PRs (including PROJECT_PLAN.md updates, design commits, and CHANGELOG.md edits between releases).
- Single bug fixes (unless they're the platform-level bug-class kind above).

When in doubt: would someone looking back in six months treat this as a meaningful milestone in the project's history? If yes, cut. If no, wait.

## Version policy

Semver, locked across packages if your project has multiple. (For a single-package project, just one version file to bump.)

- **Minor bump** (`0.5.0` → `0.6.0`) — a release event landed.
- **Patch bump** (`0.5.0` → `0.5.1`) — a critical hotfix or follow-on cut between minor releases. Rare; most small fixes just live in the next minor.
- **Major bump** (`0.x` → `1.x`) — deferred until there's a stability promise that justifies the major-version contract. Pre-1.0 means breaking changes between minors are allowed as long as they're called out in the CHANGELOG entry.

## Release ritual

The PM thread runs steps 1–4. Steps 5–6 are typically a manual handoff today (see note below).

1. **Decide we're cutting.** Trigger is one of the events above. Date the release in ISO format.
2. **Compose the `docs/CHANGELOG.md` entry.** New section at the top of the file under the new version heading. Pull bullets from `docs/SHIPPED.md` entries that landed since the previous release. Each bullet should be one line with an anchor link to the corresponding SHIPPED.md section. Include a "Known follow-ons" subsection listing open GitHub Issues scoped against the released work.
3. **Bump versions.** Update the version field in each of your project's version files (e.g., `backend/pyproject.toml`, `frontend/package.json`, `Cargo.toml`, `package.json` at root, etc.). Always together if locked across packages.
4. **Open the release PR.** Title: `Release v0.X.Y`. Body: copy of the CHANGELOG entry. PM auto-merge once green.
5. **Tag the merge commit.** From a local terminal: `git fetch origin && git tag v0.X.Y origin/main && git push origin v0.X.Y`.
6. **Mirror to GitHub Releases** (optional). Extract the version's CHANGELOG section and feed it to `gh release create`:

   ```bash
   gh release create v0.X.Y --title "v0.X.Y" --notes-file <(
     awk '/^## v0\.X\.Y/{p=1; print; next}
          p && /^## v[0-9]+\.[0-9]+\.[0-9]+/{exit}
          p' docs/CHANGELOG.md
   )
   ```

   (Substitute the actual version for `v0\.X\.Y`.) The awk starts printing at the version heading and stops at the next `## vX.Y.Z` heading; works on macOS and Linux. **Don't use `head -n -1`** — that's GNU-only and silently produces empty notes on macOS / BSD (`head: illegal line count -- -1`), and `gh release create` will still create the release with no description.

   If you're editing an existing release whose notes ended up wrong, swap `create` for `edit` and the rest of the command works unchanged. Alternative: just paste the CHANGELOG section into the GitHub Releases UI on github.com.

Steps 5 and 6 happen outside the PM thread today because most agent-runtime GitHub tooling doesn't include tag/release creation. The `gh` CLI handles both in two seconds from any terminal where the user is authenticated. If your runtime gains a tag-create tool, fold these steps back into the ritual.

## What's intentionally not part of this

- No release branches. Cut directly off `main`.
- No release candidates / betas.
- No automated release-from-CI.
- No deprecation policy for the API surface while pre-1.0 (breaking changes allowed between minors as long as they're called out in the CHANGELOG entry).
- Distribution mechanics (signed binaries, package publishing, deploy steps) are out of scope for this doc. If your project ships such artifacts, add them as a follow-on step after the tag creation.

## Retrospective hook

Each release is a natural moment to look back and re-prioritize. The PM thread should treat the release PR's merge as an invitation to:

- Read the prior release's CHANGELOG and ask: did we ship the things we expected to? Anything surprising?
- Re-scan `docs/PROJECT_PLAN.md` → "Suggested sequencing" — does it still match the strategic priority?
- Decide if the next coherent feature set has a clear lead candidate, or if multiple parallel arcs are active.

This is informal; if there's nothing to update, the retrospective is "nothing to update." But the moment exists.
