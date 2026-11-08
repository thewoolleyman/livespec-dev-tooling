---
proposal: no-fleet-check-compares-a.md
decision: accept
revised_at: 2026-11-08T17:09:13Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as proposed. A vendored livespec_runtime tree edited in place drifted from the release its .vendor.jsonc pins for five days (livespec-orchestrator-beads-fabro 4df0ec967, pinned v0.29.1), because the only byte comparison, dev-tooling/check-vendored-livespec-runtime-release.sh, is wired into nothing and needs the network. The new vendored-tree-matches-pin obligation row puts that comparison in fleet conformance, which already reads the network from one central vantage point, so the no-network constraint on checks/ modules is untouched. Differing, missing or extra files and an unknown pinned ref are distinct ERROR findings, and an unreadable manifest or tree is skipped under the can't-read-is-not-absent discipline. Following the 2026-11-08 lesson of livespec-dev-tooling-szjpez, the row MUST NOT exclude a member from a release dispatch through the fan-out preflight's per-member filter until every vendoring member satisfies it; until then it reports and fails the sweep and each member's own job. The independent read-only sonnet review found no blockers. Its low-severity notes, that the row's handling of a failed upstream fetch and the name of the preserved-file field are left to the implementation, belong to the implementation carrier livespec-dev-tooling-ngfaxq. No H2 heading changes, so tests/heading-coverage.json needs no co-edit.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T17:08:23Z
verdict: NO BLOCKERS
proposal_stem: no-fleet-check-compares-a
content_digest: d65c77c61086bfa36c272c5b7ea52442a3254c5e073e3a9112b5d3cba30d7884
