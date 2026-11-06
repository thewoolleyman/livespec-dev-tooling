---
proposal: ensure-plugins-honours-orchestrator-roll-hold.md
decision: modify
revised_at: 2026-11-06T16:18:58Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified, in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn). Delegated decider: the gmktec-factory-placement seat session (plan epic livespec-dev-tooling-me5aqz), on the maintainer's ruling relayed by legacy-coordinator-agent at about 16:0xZ on 2026-11-06 ("7. Yes, I assume so? Seems to make sense, do it if you agree"), with the coordinator agreeing. Why: the fleet's orchestrator roll gate (proof matrix plus named canaries) was enforced only by operator timing, while every fleet clone's SessionStart hook runs `just ensure-plugins`, which installs the newest marketplace build with no hold. On 2026-11-06 v0.293.1 reached four clones between 06:07Z and 06:23Z with no operator roll. A gate that binds only launch-time dispatch while clones adopt the newest tag at session start is incoherent. The build-convergence rule of contracts.md §"Fleet-wide plugin adoption" made ensure-plugins-fleet fail on exactly the split a hold creates, so it is amended to report a hold-explained divergence as HELD. Other divergence still fails. No design record is cited by that section and none is contradicted. An independent read-only sonnet reviewer found NO BLOCKERS on these exact bytes (2026-11-06T16:17:37Z). Its non-blocking notes, left for a later propose-change: the route-through clause could name Claude Code plugin builds to exclude the Codex row explicitly; the scenario does not exercise the no-downgrade and absent-record clauses; a held plugin that is enabled but not yet installed is not spoken to (the natural reading is that nothing is installed); and 'at or above' relies on semver precedence. The implementation is carried by livespec-dev-tooling-7upzav (plan gmktec-factory-placement). The tests/heading-coverage.json row for the new scenario heading is co-edited in the revise commit as an integration-tier TODO owned by 7upzav.

## Modifications

Two modifications to the proposal as filed. (1) The Held install bullet's 'it MUST exit 0 for the held plugin' is restated as 'the held plugin MUST NOT make the recipe exit non-zero', because a recipe has one exit code. (2) The roll-hold rules are placed under a new '#### Orchestrator roll hold' subsection of contracts.md §"Fleet-wide plugin adoption" instead of further bullets after Success. Its introduction adds that any recipe or verb in this library that adopts a plugin build in a member MUST do so through that member's ensure-plugins recipe, so the hold binds SessionStart, the `just bootstrap` local reconcile and `just ensure-plugins-fleet` alike. This responds to the coordinator's measured observation that the livespec-dev-tooling clone's orchestrator registration moved at 16:12:51Z with no session start in that minute. The Build convergence and Success bullets are amended in place with the hold-explained exception. The scenario is as filed.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-06T16:17:37Z
verdict: NO BLOCKERS
proposal_stem: ensure-plugins-honours-orchestrator-roll-hold
content_digest: 7dfc50ead5f0cc2d71d6c41670265731c455fb9623b812b5b16ae21a215e4b12
