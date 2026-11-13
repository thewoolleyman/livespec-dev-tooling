---
proposal: a-bump-to-a-livespec.md
decision: modify
revised_at: 2026-11-13T02:19:54Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:ci-runtime-and-cost
---

## Decision and Rationale

Plan ci-runtime-and-cost, work item livespec-dev-tooling-7crrkb (the 2026-11-12 ErrImagePull of livespec-console-beads-fabro#1356 after a direct sibling-released dispatch). The sandbox-image readiness rule moves from the release fan-out alone into reusable-bump-pin-from-dispatch.yml, the workflow every dispatch path passes through, with the non-waiting form in reusable-pin-freshness.yml; both reference the layer set the fan-out's readiness paragraph already names rather than restating it. Two scenarios carry the behavior. Modified to carry the coordinator-directed gate-flavor wording fix in non-functional-requirements.md (see Modifications). Decided under delegated revise_decision_mode in revise slot 11, opened by legacy-coordinator-agent for the ci-runtime-and-cost plan seat (epic livespec-dev-tooling-ib3oe3), which made the dispositions. Spec-led, not drift-origin; no design record is contradicted.

## Modifications

Relative to the proposal, this decision also carries one wording change in non-functional-requirements.md section 'Sandbox image gate toolchain', directed by legacy-coordinator-agent for this slot. The sentence that required a gate member's non-Python tool to be on PATH in 'the sandbox image that consumer's CI container pins' now names the gate flavor's image: the image of the gate flavor, at the one container image version the consumer's CI declares, under the same section's ratified 'Every consumer's CI declares one container image version' rule. A closing sentence says a layered flavor's image is off the gate path and this rule does not require it to carry the tool. Under the one-image-version rule a consumer's CI may name a layered flavor beside the gate flavor, so 'the sandbox image' no longer named one image. The proposal's own contracts.md and scenarios.md text is unchanged.

## Resulting Changes

- contracts.md
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
proposal_stem: a-bump-to-a-livespec
content_digest: 75a9b71967119340da32c6829d274feb6d1af6ee34673f25a3b209c3f1f33f29
