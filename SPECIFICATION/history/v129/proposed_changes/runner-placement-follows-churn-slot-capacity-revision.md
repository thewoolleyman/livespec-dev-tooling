---
proposal: runner-placement-follows-churn-slot-capacity.md
decision: accept
revised_at: 2026-11-04T10:10:01Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5 (session kubernetes-sandbox-backend)
---

## Decision and Rationale

Accepted as proposed. The specification fixes each node's declared churn-slot capacity (CI-facilities posture; Admission capacity sums to the cohort quota) but not how runners are spread across it. Measured 2026-11-04 (livespec-dev-tooling-mtvxde): the default scheduler's LeastAllocated scoring on cpu/memory requests placed zero runners on gmktec-xubuntu (94% requested by factory pods while about 55% idle) and filled 16-core hp-xubuntu before 72-core poweredge-xubuntu, so declared slots went unused by construction. The clause places runners by churn-slot use through a runner-only scheduler profile and leaves the default profile, and every other pod's placement, unchanged; the scenario states the observable placement; the heading-coverage TODO is owned by mtvxde.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T10:09:08Z
verdict: NO BLOCKERS
proposal_stem: runner-placement-follows-churn-slot-capacity
content_digest: 77b7fc14f5dd57de630cd36863bced43fb1b71b437774001ec0815a8ce372ecc
