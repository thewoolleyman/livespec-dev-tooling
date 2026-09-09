---
proposal: heading-coverage-convergence.md
decision: modify
revised_at: 2026-09-09T04:16:44Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Modify (not clean accept): the proposal's verbatim 5-bullet convergence clause is well-targeted at the ### Scenario-tier coverage subsection and is applied as-authored; but the proposal's second edit targeted a 'Release-gate targets' section that does not exist in this spec and named checks in CLI style rather than the spec's slug convention, so that paragraph is dropped as malformed AND redundant — every requirement it stated (register-absence failure, register-may-only-shrink, reason guard, age bound, liveness, retirement at zero) is already normative in the 5-bullet clause. The proposal's 8 required scenarios are added to scenarios.md with their 8 tests/heading-coverage.json rows (test: TODO, owned by the live mechanism children livespec-dev-tooling-0bse.1..4, each reason acknowledging the owed integration-tier test), so the change eats its own rule and stays in lockstep. Preserves both original decisions (spec-first transitional TODO; scope-to-authorship). Verified locally: heading_coverage exit 0 and no_todo_registry strict exit 0 (0 failing, 0 liveness_unverified). Independent read-only Fable ratification review returned NO BLOCKERS on the exact bytes.

## Modifications

1) In non-functional-requirements.md ### Scenario-tier coverage, replaced the single sentence 'A TODO entry is permitted during transition provided its reason explicitly acknowledges this tier requirement.' with the proposal's verbatim 5-bullet convergence clause (shrink-only debt register; reason acknowledges an owed test and no non-testable category; live-owner liveness at release tier; 30-day default age bound at release tier; retirement of the scope lever and reason slot at zero). 2) DID NOT add a 'Release-gate targets' section (it does not exist) and DROPPED the proposal's malformed release-tier paragraph whose CLI-style check names and target section were invalid and whose content the 5-bullet clause already subsumes. 3) Added the 8 required scenarios to scenarios.md and their 8 heading-coverage.json TODO rows owned by mechanism children 0bse.1..4. No new H2 heading was introduced in non-functional-requirements.md.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-09T04:15:30Z
verdict: NO BLOCKERS
proposal_stem: heading-coverage-convergence
content_digest: 3f94e8e994821be3b3e19780f433c345e3e6436359a6adef3d2b41dd63b08493
