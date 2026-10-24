---
proposal: local-gate-concurrency-limit.md
decision: accept
revised_at: 2026-10-24T03:30:55Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted, both proposals in this file. (1) `## Local gate concurrency limit`: work item livespec-dev-tooling-c62xtb needed a ratified heading for its Definition of Done. A 2026-10-24 R316 preflight refused it because `## Hooks and CI` governs hook ordering only. The maintainer approved turning the limit on, relayed by coordinator gitops-fleet-capacity-monitoring on 2026-10-24: "Yes go ahead and turn it on. Hopefully we won't need it much longer, right?" Measured on vmi3006760 (18 cores) at 01:34Z: 95.8% busy, load 78, with 4-5 concurrent pytest -n 4 aggregates. It is a stopgap until plan delegated-gate-fleet-rollout delegates the heavy gates. (2) `## Sandbox image gate toolchain`, added at the coordinator's direction: console's cluster gate Job gate-livespec-console-beads-fabro-bc28m failed only on four tests needing jq, because the Job runs the consumer's pinned sandbox image without `mise install`. livespec-dev-tooling-jxepvj carries the fix. Seven TODO coverage rows (c62xtb, jxepvj) and the regenerated debt register land in the same change. Ratification by Fable: R1 (finding 1 only) BLOCKERS 1, because the registry co-edit was missing; R2 NO BLOCKERS once it was added; R3 (both findings) NO BLOCKERS on these exact bytes, digest b36b533d. Reviewer: claude-fable-5-1, a separate read-only claude -p process limited to Read, Grep and Glob.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-24T03:27:36Z
verdict: NO BLOCKERS
proposal_stem: local-gate-concurrency-limit
content_digest: 5b6ebdc24d6ac0db6b7f3d4650047f8b07b18412f4d88113666f9d05b20b10c4
