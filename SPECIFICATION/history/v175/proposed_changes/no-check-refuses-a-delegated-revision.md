---
proposal: no-check-refuses-a-delegated.md
decision: modify
revised_at: 2026-11-10T01:05:33Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified and accepted under delegated decision mode. livespec-dev-tooling-zqrg7d was refused at dispatch as spec-change tier for this topic (spec-stated judgement: partial, generalize ## Shared check inventory). The ratified text states the invariant (an authority-reading member does not run in a gate Job), but no clause admits the check that traces a delegated Job recipe for the skip read. That check now lands as a warn-default shared check with its own lever and one governing scenario. A 2026-11-08 fleet sweep measured the defect class: livespec-orchestrator-beads-fabro's pre-commit path, owned by bd-ib-oxx6eo. No design record is contradicted, and the proposal is not drift-origin. Independent sonnet ratification review: NO BLOCKERS on the final bytes.

## Modifications

Pre-merge doctor LLM findings applied. (1) Added the canonical-check wiring sentence, mirroring no_ambient_environment_loops, with the waiver path. (2) Added a Terms bullet. It defines a declared authority member, read from the same source as the delegated client. It also defines the skip variable by the client's exact resolution rule: the single variable named by the check recipe's read -ra lines whose array name contains 'skip', and none when zero match or more than one distinct variable is named. It says the check reports no finding where the client refuses locally, and reports a finding when the declarations are unreadable or no check recipe exists, because the client then skips nothing. (3) Added a fourth honouring shape: the aggregate runner skips authority members when LIVESPEC_GATE_CONTEXT is set (scripts/just/check.sh). (4) Scoped Arming order to repositories that maintain a committed severity-lever source.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T01:03:51Z
verdict: NO BLOCKERS
proposal_stem: no-check-refuses-a-delegated
content_digest: 832977cc62410d13b8be45ab58f84d30c8055bb3c76116dbb1536820ed7daf6d
