---
proposal: honeycomb-board-and-trigger-appliers.md
decision: modify
revised_at: 2026-11-05T03:07:19Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:kubernetes-observability
---

## Decision and Rationale

Accepted in delegated mode by the kubernetes-observability plan seat (epic livespec-dev-tooling-s2aqob). The proposal states the read-only drift mode that plan assertion 6 needs for boards and triggers. Today only the collector has a drift report, and a hand edit to a board or trigger is overwritten unreported on the next apply. Implementation item livespec-dev-tooling-4vopaj is held as spec-change tier on this topic. The new paragraph sits after the node section's Board and triggers paragraph, which it leaves untouched, so it composes with the pending alert-thresholds-match-packed-fleet proposal that rewrites that paragraph's trigger list.

## Modifications

Wording only. The paragraph merges the proposal's sentences on included definitions, ignored service-assigned fields and missing-definition reporting into fewer sentences. In the scenario, the proposal's 'neither run MUST send' becomes 'neither run MAY send', the negated-MAY prohibition form the same section already uses ('No node-telemetry emitter MAY run'). No rule was added or dropped.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T03:06:05Z
verdict: NO BLOCKERS
proposal_stem: honeycomb-board-and-trigger-appliers
content_digest: e647351811cfc6143b673c2ff56521be92c3d2308a240d3bb07cf64b7be0d1b0
