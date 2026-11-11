---
proposal: the-pre-push-gate-confirms.md
decision: accept
revised_at: 2026-11-11T18:27:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accept as filed, for livespec-dev-tooling-7uae5p (the hardening follow-up to 73ocxb, v186). Reused delegated pre-commit evidence is today a worktree-local file any process can write. It is now confirmed against evidence an agent cannot fabricate: the cluster's own record of the named gate Job, meaning its Complete condition, its livespec.gate/tree-hash label and its pod's LIVESPEC_GATE_MEMBERS line. A missing record or an unreachable cluster falls back to the ordinary gate, and a disagreeing record submits a Job after printing each disagreeing field. The cost is stated: about an hour of reuse window under the template's ttlSecondsAfterFinished. Ratified together with one-library-command-gives-every in one revise because both edit the same bullet (legacy-coordinator-agent, ~17:48Z, v195 slot). Decided by the implement-test-performance plan seat under delegated decision mode.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T18:25:27Z
verdict: NO BLOCKERS
proposal_stem: the-pre-push-gate-confirms
content_digest: 0112402f73718ebb017b41e2b5caec707801150b66e6e0affc49af8b35f24b84
