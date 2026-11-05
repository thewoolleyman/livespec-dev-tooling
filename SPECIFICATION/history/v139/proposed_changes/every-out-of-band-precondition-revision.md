---
proposal: every-out-of-band-precondition.md
decision: modify
revised_at: 2026-11-05T08:24:30Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Decided in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn). Delegated decider: legacy-coordinator-agent under R301. Plan ci-pool-provisioning-leftovers (epic livespec-dev-tooling-fby3sx) found that the archived k3s-on-gmktec plan's note 005 required each role to assert its out-of-band preconditions, but no ratified statement says so. Measured on master d8ec42a6, four VPS dev-host roles change the host before checking their inputs, or only warn about them, and several post-apply steps are recorded nowhere in ansible/. The filing-time tier classifier held carriers livespec-dev-tooling-c763up and -fmbnyd until such a clause exists. No ratified statement conflicts, and no design record is contradicted. An independent read-only sonnet reviewer found NO BLOCKERS on the exact bytes.

## Modifications

Placement and one sentence; no rule added or dropped. (1) The two new paragraphs are placed after **Enforced in the aggregate.** rather than before it, so that paragraph's 'Both obligations MUST be asserted' still refers only to the two obligations it enforces. (2) The proposal's meta-note, that the aggregate paragraph is unchanged, becomes the normative sentence 'This obligation and the next are judged by review and by the drift and apply runs; neither is a member of the `just check` aggregate.'

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T08:23:30Z
verdict: NO BLOCKERS
proposal_stem: every-out-of-band-precondition
content_digest: 62042a1aee6ea31cb672d37412f6ddc0b06b0d91fe7c646f7d57227c42312bb0
