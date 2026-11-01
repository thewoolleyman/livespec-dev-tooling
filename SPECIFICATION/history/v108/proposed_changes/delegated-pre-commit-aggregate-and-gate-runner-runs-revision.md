---
proposal: delegated-pre-commit-aggregate-and-gate-runner-runs.md
decision: modify
revised_at: 2026-11-01T23:28:38Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

MODIFY. Ratifies plan dev-host-test-gate-load's (epic livespec-dev-tooling-6vuiwe) carriers for DoD assertions 2 and 4: an opt-in delegated_pre_commit key under which `just check-pre-commit` runs as a gates Job keyed to the staged tree (replacing v105's 'the pre-commit aggregate is not delegated' bullet), and gate-start running full-suite commands as gates Jobs by default in delegated repositories with a recorded --local choice and a venue on every run. Four-plus-one new scenarios. Spec-led from measurement (plan research note 002: hand-commit pre-commit aggregate 0.90 and ad-hoc pytest/check 0.49 cores averaged over the 4.25 h v3 window 2026-11-01 16:25-20:51Z), not drift-origin; no design record contradicted. Decided under delegated revise_decision_mode by seat dev-host-test-gate-load (plan resume 2026-11-01). Re-landed as the next version because a concurrent revise (llm-spend-telemetry-pricing) took v107 first and PR #3047 conflicted; the spec diff against master is byte-identical to the one reviewed for v107, and a fresh separately spawned read-only sonnet review returned NO BLOCKERS on these exact bytes. Original review: separately spawned read-only sonnet agent, NO BLOCKERS after a first NO BLOCKERS round whose nits 1, 4 and a no-verdict gate-runner scenario were folded in; remaining nits (missing-recipe and sibling-clone rules for the pre-commit Job, a span attribute distinguishing pre-commit from pre-push no-verdict events so the pre-push no-verdict trigger is not tripped by benign commit fallbacks, both-keys-on behaviour, scenarios for tree mismatch / telemetry / authorization members / Not-converted) are left to the implementing items.

## Modifications

Each new contracts section states it is spec-first. Pre-commit 'What the Job runs': authorization-reading members run on the committing host and join the verdict (as pre-push), and commit-hook checks ahead of the aggregate such as staged_precheck stay on the committing host. Pre-commit telemetry: best-effort, never changes the verdict. Gate-runner: new 'What the Job runs' bullet (dispatched command only; authorization-reading members of a just recipe run on the dev host and join the verdict); the run's exit_code is the command's own exit code in the Job. Scenarios rewritten in the file's Given/And/When/Then/And style; added a gate-runner no-verdict scenario (DIED_WITHOUT_VERDICT, gate-wait 75, no local re-run); the pre-commit no-verdict scenario names an eligible host and asserts the commit is not refused.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-01T23:27:09Z
verdict: NO BLOCKERS
proposal_stem: delegated-pre-commit-aggregate-and-gate-runner-runs
content_digest: ca4972239d784bda0cb6f5948ad6d666b3733cde02ae46317168b99759490891
