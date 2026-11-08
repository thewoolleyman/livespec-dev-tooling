---
topic: no-fleet-check-compares-a
author: claude-opus-5-5
created_at: 2026-11-08T04:20:00Z
---

## Proposal: A fleet-conformance row compares each vendored livespec_runtime tree with the release it pins

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add a `vendored-tree-matches-pin` obligation row to the shared fleet obligation table. It fails a member whose vendored `livespec_runtime` tree differs in bytes from the release its `.vendor.jsonc` entry pins, and it reports a pinned ref the upstream repository lacks as a separate finding. The row MUST NOT exclude a member from a release dispatch until every member's vendored tree matches its pin.

### Motivation

On 2026-11-03, livespec-orchestrator-beads-fabro commit 4df0ec967 edited its vendored `.claude-plugin/scripts/_vendor/livespec_runtime/spec_stated.py`, adding `ClauseEvidence`, `SpecStatedVerdict.evidence` and an `_evidence` parser. None of it went upstream. Its `.vendor.jsonc` still pins `v0.29.1` and says the tree is byte-identical to that release. The script that would prove it, `dev-tooling/check-vendored-livespec-runtime-release.sh`, is wired into no recipe, workflow or hook, and it needs the network, which keeps it out of `just check`. The drift went unseen for five days. It surfaced only on 2026-11-08, when livespec-dev-tooling's `cross-repo-public-api-declared` row reported a name livespec-runtime "no longer binds", and that finding also excluded livespec-runtime from the v1.188.0 fan-out. The repair is livespec-runtime-rb2qpp (livespec-runtime#856) and livespec-runtime-bxbyko. livespec-dev-tooling-ngfaxq implements the row, and legacy-coordinator-agent ruled the defect class to be vendored-copy drift.

`check-vendor-manifest` validates only the manifest's shape and never compares bytes, so no wired check covers this today. Fleet conformance is the right home: it already reads the network from one central vantage point, and contracts.md's no-network constraint covers only Python check modules.

The dispatch clause is the 2026-11-08 lesson of livespec-dev-tooling-szjpez. A row armed as an excluding finding before the fleet satisfies it excluded every member from v1.188.0's fan-out. The orchestrator does not satisfy this row until rb2qpp and bxbyko land and it re-vendors.

FLEET SCOPE: on 2026-11-08 the members vendoring `livespec_runtime` are livespec, livespec-dev-tooling, livespec-orchestrator-beads-fabro and livespec-orchestrator-git-jsonl. The row reads its member set from each manifest at run time.

### Proposed Changes

In `SPECIFICATION/contracts.md`, "## Cross-repo coordination automation surface", "### Fleet surface — central conformance and reconcile", add this paragraph directly after the paragraph that begins "**Vacuous-pass closure (the `baseline-harnesses` obligation row).**":

**Vendored-tree pin fidelity (the `vendored-tree-matches-pin` obligation row).** For every manifest member whose master-tree `.vendor.jsonc` carries a `livespec_runtime` entry, the assert-mode row MUST fetch the `livespec_runtime/` tree of the release that entry's `upstream_url` and `upstream_ref` name and compare it byte for byte with the member's vendored tree. A file the entry itself declares preserved, such as a LICENSE, is excluded. Any differing, missing or extra file is an ERROR finding naming the member, the pinned `upstream_ref` and each such file. A pinned ref the upstream repository does not carry is its own ERROR finding, distinct from drift. A member whose manifest or vendored tree cannot be read is skipped under the can't-read-is-not-absent discipline, never judged as matching. The row MUST NOT exclude a member from a release dispatch through the fan-out preflight's per-member filter until every member that vendors `livespec_runtime` satisfies it. Until then its finding is reported, and it fails the scheduled sweep and each member's own fleet-conformance job, but the dispatch matrix keeps that member.

No other sentence of the section changes, and no `## ` heading is added or removed, so `tests/heading-coverage.json` needs no co-edit.
