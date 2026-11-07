---
proposal: orchestrator-build-explicit-adoption.md
decision: accept
revised_at: 2026-11-07T21:57:48Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:gmktec-factory-placement
---

## Decision and Rationale

Accepted by legacy-coordinator-agent's ruling under R301 (~18:40Z on 2026-11-07), on this seat's recommendation: stage the fleet plugin build record, with spec v150's record leaving the contract and returning as stage 2, carried by livespec-dev-tooling-5rer35. Three drafts of the record failed against live state; stage 1 has no record, fetch or version comparison, so most of that defect list goes away. DEPARTURE, stated plainly: the maintainer's direction was 'go with D and fix it everywhere'. For the interval until stage 2, no committed fact names the build a clone should be on, and a roll is an operator act. The coordinator reports that to the maintainer as decided and open to objection. It also departs from livespec core's plugin currency invariant for the orchestrator plugin, as v150 already did; livespec#3132 proposes the matching exception there, and that revise is core's decision. WHAT IT DOES NOT STOP. The session-reconcile rules reach a clone only when its livespec-dev-tooling pin names a release carrying them, so session starts keep moving builds until then; it must not be claimed stopped before a pin read shows it. Pins read at about 18:30Z ranged from v1.134.2 to v1.187.0. homelab, openbrain and resume run their own hooks and are not reached at all (hl-jq6ov3, ob-td6fup, li-z3ynyp). Orchestrator surfaces that push agents to update a lagging clone are not changed here; bd-ib-rfhnqf changes them and ships before the 7upzav release reaches a pin. Codex is out of scope: these rules govern Claude Code project-scope installs. REVIEW. Two read-only doctor passes against live state preceded this, read rather than run; they reshaped the draft (the required <build> argument, how a clone is resolved, repair scoping). The independent reviewer found one contradiction, fixed, then NO BLOCKERS on the v154 bytes. RE-CUT: first cut as v154 on livespec-dev-tooling#3723, which lost the version race to livespec-dev-tooling#3722 (merged 71a09785) and was not merged; these are the same contract bytes re-applied to the new master, where scenarios.md now also carries v154's homelab-worker scenarios, so the digest is new and a fresh independent review was taken.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-07T21:57:16Z
verdict: NO BLOCKERS
proposal_stem: orchestrator-build-explicit-adoption
content_digest: a2d895843aa94ab173922103bb8c8c03f701fcb332bae1a736e04264ec58a3a1
