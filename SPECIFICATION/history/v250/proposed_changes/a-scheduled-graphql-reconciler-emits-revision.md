---
proposal: a-scheduled-graphql-reconciler-emits.md
decision: accept
revised_at: 2026-11-18T20:38:39Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Plan throughput-metric's only remaining blocker: livespec-dev-tooling-gaetnq was refused at the spec-change tier because no ratified text describes the merged-green reconciler. The proposal states the fleet's one throughput metric, the reconciler, its event shape, awaiting and dead-man triggers, and the board panels, with seven scenarios; it was filed against the maintainer's 2026-11-13/14 throughput directions. Independent review found no contradiction with ratified clauses. Non-blocking notes (scenarios for the first-pass lookback, writer retirement, awaiting event, dead-man and stalled list; ci.covering_run_id empty-vs-omitted) go to livespec-dev-tooling-gaetnq.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-18T20:37:48Z
verdict: NO BLOCKERS
proposal_stem: a-scheduled-graphql-reconciler-emits
content_digest: b050dc4d91b172c287ecf92de78e9454081525ada84d345a93102ee556b21b89
