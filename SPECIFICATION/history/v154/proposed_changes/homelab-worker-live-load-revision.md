---
proposal: homelab-worker-live-load.md
decision: modify
revised_at: 2026-11-07T20:00:41Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Adopts the maintainer direction (2026-11-07T19:22Z, epic livespec-dev-tooling-ko26ez): container workers enroll automatically per workload class their architecture can run, select nodes by architecture from one declared list, derive per-class capacity from measured resources, carry live production load from the normal queues, and lose no work when they leave. Modified so the derived worker churn-slot capacity reconciles with the runner-pool rules (it stands in for the per-node profile, counts in the cohort-quota sum and is the only per-node placement limit, and enrolling or removing a worker reconciles the quota in the same operation), per the independent reviewer's blocker. The proposal's guidance to the pending spec/homelab-factory-sandbox proposal is not spec text and is carried to that proposal's revise instead.

## Modifications

Derived per-class capacity bullet: added that a worker's derived churn-slot capacity is its declared admission capacity under the runner-pool rules (stands in for the per-node profile, counts in the cohort churn-slot quota sum, only per-node placement limit) and that enrolling or removing a worker MUST reconcile the cohort quota in the same operation, standing in for the committed quota update. Wording: 'A workload MUST NOT be scheduled'; the class taint key named; 'the same queues' defined as the CI runner scale sets and their churn-slot cohort, the gate job queue and the factory dispatch path. The paragraph addressed to the pending Factory sandboxes on a worker bullet is not inserted.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-07T20:00:25Z
verdict: NO BLOCKERS
proposal_stem: homelab-worker-live-load
content_digest: d0d6d33c1c372f7357a3b5318938421c44cee2f47c0b32c81b50f0ff8129765e
