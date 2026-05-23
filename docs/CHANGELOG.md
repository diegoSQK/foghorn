# {{PROJECT_NAME}} Changelog

Versioned releases of {{PROJECT_NAME}}. Each entry corresponds to a git tag on `main`. The release ritual and event-trigger rule live in [RELEASE_PROCESS.md](RELEASE_PROCESS.md). The chronological as-shipped history with full design narrative lives in [SHIPPED.md](SHIPPED.md); this file is the indexed cut-points.

Versions are semver, locked across the project's packages.

---

*First release entry goes here. Use a heading like `## v0.1.0 — YYYY-MM-DD`. Body should contain:*

- *A short paragraph framing what this release contains (the coherent set of changes that triggered the cut).*
- *A "Headline shipments" subsection bulleting the major changes since the previous release, each with an anchor link into SHIPPED.md.*
- *A "Known follow-ons" subsection listing open GitHub Issues scoped against the released work — things you noticed during the cut that aren't blocking but are worth tracking.*
- *Optionally a "Queued for the next minor" subsection naming the next coherent set if it's already in view.*

*For a worked example of a real CHANGELOG entry, see the project this template was derived from: [ficycle's v0.5.0 inaugural entry](https://github.com/diegoSQK/ficycle/blob/main/docs/CHANGELOG.md).*
