---
proposal: factory-node-label-survives-registration.md
decision: modify
revised_at: 2026-10-16T17:38:31Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:factory-worker-nodes-gitops
---

## Decision and Rationale

Accepted with modifications under the maintainer's delegated authority recorded on livespec-dev-tooling-dfixhe (2026-10-15 ~16:40Z 'Make the decisions on my behalf', reaffirmed 2026-10-16 06:29Z), executed for freeze-driver ruling R69. No section of this specification stated the factory label. The 2026-10-16 control-plane reboot showed it surviving only on hp, because it was set only by a playbook apply. The clause and scenario state the label as a profile fact that survives registration, and they govern livespec-dev-tooling-izlx4g. The design record is livespec plan factory-worker-nodes-gitops research 001 ruling 3. Two independent read-only Fable reviews returned NO BLOCKERS, the second on these exact bytes.

## Modifications

Applied the first review's nits. (1) Added 'its factory posture' to the **One profile per node.** enumeration (clause-lockstep). (2) Replaced 'the control-plane boot converge', a term this spec does not define, with 'a mechanism that runs unattended at control-plane boot'. (3) Softened the datastore premise to 'MAY be rebuilt empty', so the MUST holds if a persistent datastore lands. (4) The scenario's When drops 'against the rebuilt datastore', consistent with (3). (5) The scenario's Given says 'every pool node' instead of the undefined inventory group name ci_pool. (6) The heading-coverage TODO row's reason names the integration-tier floor, which the second review found the debt-register check requires. The debt register entry was regenerated mechanically. The unresolvable 'R69' cite stays only in the archived proposal's motivation.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-16T17:37:12Z
verdict: NO BLOCKERS
proposal_stem: factory-node-label-survives-registration
content_digest: 820e25a176fd0f3a40ef41d8ca405cf61e7ba8366677bc9d61657435d20a91b0
