---
proposal: coverage-run-names-slowest-tests.md
decision: modify
revised_at: 2026-11-01T04:23:34Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratifies, in non-functional-requirements.md "## Enforcement-suite invocation", that `check-per-file-coverage` prints the thirty slowest test phases of each run with their durations. Spec-led, not drift-origin: research 003 of plan implement-test-performance (epic livespec-dev-tooling-sv6m5p) measured about 50 s of slow tests at the end of this repository's coverage run and could not name them, because no run records per-test durations. This is a contributor-only concern of this repository's own enforcement suite, so non-functional-requirements.md is the right home. It cites no design record and contradicts none. This revise releases the spec-change-tier hold on livespec-dev-tooling-tt4w7h, which implements it. Decided under delegated revise_decision_mode by the implement-test-performance plan session; the maintainer ruled on 2026-11-01 that this plan runs autonomously.

## Modifications

The proposal's paragraph is added verbatim. Under the authoring discipline (behavior => clause + scenario), the clause states observable output of a just target, so a scenario is added to scenarios.md: "## Scenario: the whole-suite coverage run prints its thirty slowest test phases" (Given a check-per-file-coverage run with more than thirty test phases, When its suite completes, Then the output MUST list the thirty slowest phases, each with its duration). The new H2 gets a spec-first heading-coverage TODO row owned by livespec-dev-tooling-tt4w7h and a debt-register entry, co-edited in the revise commit.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-01T04:23:27Z
verdict: NO BLOCKERS
proposal_stem: coverage-run-names-slowest-tests
content_digest: 92dd0770035c7ad2fecf681b68c8476a73b550403a5905b02df4581f985a4b9b
