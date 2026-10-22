---
proposal: worktree-reap-liveness.md
decision: accept
revised_at: 2026-10-22T00:42:43Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted on the merits as a conformance gap: the pack's reap verb had no ratified selection rule, and a measured 2026-10-21 dry run would have removed three live factory runs' source trees (work-item livespec-dev-tooling-7i2z5j, coordinator R512 hold). Liveness fails safe and factory-owned source worktrees are skipped by name, both as the proposal argues. Decided by the delegated-gate-fleet-rollout plan owner under R202 (spec drafting never blocks on a human) with independent fable ratification review NO BLOCKERS. The resulting files co-edit the two scenario headings' heading-coverage TODO rows (work_item 7i2z5j, integration-tier) and the regenerated debt register, as the proposal stated.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-22T00:42:42Z
verdict: NO BLOCKERS
proposal_stem: worktree-reap-liveness
content_digest: 2ab87a213a4e1687e5758c3b91925da79a3518a3150e0e4c9e6f693c8eec98de
