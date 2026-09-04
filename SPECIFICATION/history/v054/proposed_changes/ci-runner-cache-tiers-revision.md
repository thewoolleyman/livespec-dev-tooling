---
proposal: ci-runner-cache-tiers.md
decision: accept
revised_at: 2026-09-04T08:54:39Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-fable-5-1
---

## Decision and Rationale

Accepted as filed and amended 2026-09-04. The three proposals state the runner pool's build-cache obligations (transparent, trust-tiered by construction, host-served over per-start copies, label-addressed storage, keyed-cache posture), the Honeycomb emission contract every tier must satisfy, and the six scenarios that make the behaviors testable. Placement: pool infrastructure this repository owns -> non-functional-requirements.md, beside the JIT admission budget; behaviors -> scenarios.md; the fleet-level host requirements in the livespec repository are untouched. Aligned with the ci-runner-pod-lifecycle-reliability and poweredge-raid-array-maintenance plans (research/004) before ratification.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-04T08:54:18Z
verdict: NO BLOCKERS
proposal_stem: ci-runner-cache-tiers
content_digest: d7c194d5ebe970a501450ea3a98376e30261a6c615ffa52cff15ed3fd0da044c
