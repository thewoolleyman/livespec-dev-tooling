---
proposal: the-flake-retry-plugin-decides.md
decision: modify
revised_at: 2026-11-13T02:19:54Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:ci-runtime-and-cost
---

## Decision and Rationale

Plan ci-runtime-and-cost, work item livespec-dev-tooling-5y3luz, held by the dispatcher at spec-change tier on this topic. The two sentences state the parse-once rule as a work bound (module reads and parses per session) rather than a wall-clock bound, so the item grades against ratified text without conflicting with host-independent verdicts, and they state the one-decision-per-test-file rule the touched/untouched clause already implies. The new scenario carries the behavior. Modified with one clarifying sentence on pytest-xdist (see Modifications). Decided under delegated revise_decision_mode in revise slot 11, opened by legacy-coordinator-agent for the ci-runtime-and-cost plan seat (epic livespec-dev-tooling-ib3oe3), which made the dispositions. Spec-led, not drift-origin; no design record is contradicted.

## Modifications

Relative to the proposal, one sentence follows the two inserted ones: 'Under pytest-xdist, each worker's session is one session for this bound.' The pre-merge doctor pass found that under pytest-xdist, which the same bullet already governs, every worker runs its own pytest session and parses its own modules, so a count taken across a whole xdist run would exceed the number of distinct modules and the Definition of Done could not be graded. The bound is per worker session, as the shipped per-process parse cache (livespec-dev-tooling-pprfq2) already measures it.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T02:14:33Z
verdict: NO BLOCKERS
proposal_stem: the-flake-retry-plugin-decides
content_digest: ef5537d05f62d8b5e9fec874dc4ddb83ecbd1735b07c5522fcdaf3c585f9ac5d
