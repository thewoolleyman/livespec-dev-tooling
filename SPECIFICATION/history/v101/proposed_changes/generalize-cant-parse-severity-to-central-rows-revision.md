---
proposal: generalize-cant-parse-severity-to-central-rows.md
decision: modify
revised_at: 2026-10-30T20:12:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Lifts the can't-READ / can't-PARSE severity rule of §"Pin-currency severity policy" to a CLASS rule over every central conformance row that parses a committed member file, keeping the preflight-error / elsewhere-warning context scoping. Spec-led, not drift-origin: the proposal was filed ahead of the implementation. Decided under delegated revise_decision_mode by the delegated-gate-fleet-rollout seat.

## Modifications

Proposal step 3 called the tenant-connection row non-conformant; that is stale because livespec-dev-tooling-9hpu landed PR #2275 on 2026-09-12, so the row is named as a conforming second instance. A scenario is added for it (heading-coverage TODO owned by livespec-dev-tooling-kvvfo3, consumer-tier test owed). The first independent review measured further central rows that do not yet conform; the bullet names them as known departures brought into conformance by livespec-dev-tooling-s4gx7a, filed in this pass.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-30T20:12:02Z
verdict: NO BLOCKERS
proposal_stem: generalize-cant-parse-severity-to-central-rows
content_digest: ce19464471347bdc948f58738a646064e4019b8677c957f0cdf7df9cb2bd2749
