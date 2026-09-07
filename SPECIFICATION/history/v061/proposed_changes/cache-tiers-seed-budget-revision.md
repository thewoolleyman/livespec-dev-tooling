---
proposal: cache-tiers-seed-budget.md
decision: accept
revised_at: 2026-09-07T02:16:24Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: fable
---

## Decision and Rationale

Accepted as filed, single-topic (--only-topic cache-tiers-seed-budget; the other pending proposal, pin-uses-ref-template-scan-set, is another item's and is left in place). The proposal replaces exactly two sentences of the Tiers paragraph in §"Runner-pool build cache tiers" of non-functional-requirements.md: the start-burst premise grounded in a hardware figure ("about six simultaneous job starts saturate the array", a 2026-09-02 measurement of a storage array the host no longer has) is re-based onto the media-independent rule the pool now enforces — every byte and file a seed adds to a job start is overhead on any medium, so a host-served realization is preferred, a seeded tree's per-start cost is capped by one byte budget and one file budget stated in exactly one committed place that governs both the populator's refusal and the node's lifecycle sweep's judgement, the populator refuses to publish an over-budget generation leaving the previous one live, the sweep reports over-budget generations and seeds as lifecycle findings with gauges, and a per-start byte copy of a cache MUST NOT ship in any tier; the six-starts figure is retired as measurement history held in livespec's plan record (plan ci-runner-pod-lifecycle-reliability, research note 005) with no replacement concurrency figure and no array identity. The target-directory sentence now defers to that prohibition so it has one home. Both replace targets existed verbatim exactly once at line 157; no `## ` heading changes, so no tests/heading-coverage.json co-edit. Placement is correct (contributor-facing pool infrastructure in non-functional-requirements.md); the text names the property, not the shipped ConfigMap or script names. No design record is contradicted: the shipped mechanism it describes (populator budget refusal, livespec-41w4; lifecycle-sweep classes warm-cache-oversize and start-seed-cost, livespec-44qx) closed with live evidence on 2026-09-06. Accepted after an independent read-only Fable review: the first filing drew two blockers (an over-claimed post-rebuild concurrency figure and a write-source ranking), corrected in livespec-dev-tooling PR 1893 (9e293e2d); the second review of the merged text returned NO-BLOCKERS. The maintainer decided the accept, with the doctor's v060 out-of-band backfill (contracts.md edit 9c52a7d7) committed on the same branch immediately before this revision. On behalf of livespec work-item livespec-1qpt, Carrier F4c of the 2026-09-04 scope amendment on epic livespec-ifwnqj.

## Resulting Changes

- non-functional-requirements.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-06T17:50:00Z
verdict: NO BLOCKERS
proposal_stem: cache-tiers-seed-budget
content_digest: dd17339a729d946a82b7ee45a32fa273d9135cbd7c66ce65bcc7d73fcdf5d716
