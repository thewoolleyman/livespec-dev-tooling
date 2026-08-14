---
proposal: adaptive-jit-admission-budget.md
decision: accept
revised_at: 2026-08-14T05:32:12Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: gpt-5.6
---

## Decision and Rationale

Maintainer-directed auto-revise accepts the corrected adaptive controller contract. It explicitly supersedes PR #1398's unconditional fixed positive inter-request-spacing design while retaining its useful installation-wide admission, response classification, shared circuit, finite retry, durability, and secret-free telemetry intent. The corrected arithmetic records approximately five REST points per content-generating POST and ten per complete mint pair, so the 450-point initial allowance is approximately 45 pairs.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: manual-spawn
reviewer_model: gpt-5.6
reviewer_identity: gpt-5.6
separate_reviewer: True
read_only: True
reviewed_at: 2026-08-14T05:30:58Z
verdict: NO BLOCKERS
proposal_stem: adaptive-jit-admission-budget
content_digest: 631fce1e9ec7565e7ca99c0c3218804b4cbba2286bdaa2b18d721686add3e6f4
