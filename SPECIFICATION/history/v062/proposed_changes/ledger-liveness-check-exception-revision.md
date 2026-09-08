---
proposal: ledger-liveness-check-exception.md
decision: accept
revised_at: 2026-09-08T02:10:04Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-5
---

## Decision and Rationale

Accepted as proposed. The amendment is required for livespec-dev-tooling-x7ml and the conflict it resolves is real: three gates (no_lloc_soft_warnings, no_todo_registry, and the unarmed_until arm of required_role_keys_declared) stand down on a named work-item id that nothing verifies, so a closed, superseded or mistyped id silences the gate forever while it reports green. The ratified Non-goal forbade the only lookup that could detect this, so the two clauses could not both stand unchanged. The exception is carved as narrowly as the defect requires: a liveness answer ABOUT an id the check already holds, never a retrieval OF anything under check. The determinism cost is admitted in the text rather than hidden, and is bounded so a liveness answer may only REMOVE a stand-down, never introduce, suppress or alter a finding about the tree. The honest-degradation clause is what keeps the amendment from re-creating the very defect it removes: an unreachable store must SKIP with a stated reason, never pass quietly and never red an offline tree. The no-lever clause matches this repository's standing prohibition on skip levers and severity knobs.

## Resulting Changes

- spec.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-08T02:07:48Z
verdict: NO BLOCKERS
proposal_stem: ledger-liveness-check-exception
content_digest: 90c4fdae7f1013431ce4b77c5bd631f119796afe14f49f603c757de49f90c6e5
