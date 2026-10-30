---
proposal: a-test-only-commit-s.md
decision: modify
revised_at: 2026-10-30T20:57:50Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratifies the red_green_replay check's test-only suite-green leg in §"Test-Driven Development discipline". A commit that stages only test files runs only its staged tests, runs the full suite when it stages shared test support, and is refused when those tests fail. The full suite still gates the merge at pre-push and in CI. Spec-led, not drift-origin: livespec-dev-tooling-h3gcs6 asks to narrow a leg that today runs the full suite. This releases h3gcs6's spec-change-tier hold. Decided under delegated revise_decision_mode by the delegated-gate-fleet-rollout seat, on the direction of coordinator gitops-fleet-capacity-monitoring, which took over propose PR #2942. The proposal's author seat, petri-factory-on-gmktec, agreed to the form-only shaping.

## Modifications

Form only. The bullet is added verbatim. The proposal's second and third scenarios lacked their `## Scenario:` heading markers, so each is now its own H2. The three Then clauses use BCP14 MUST: 'MUST run only the tests in tests/test_alpha.py, and MUST NOT run the full suite'; 'MUST run the full suite'; 'the commit MUST be refused'. Each scenario has a heading-coverage TODO row owned by h3gcs6, as the proposal requires. Non-blocking reviewer note for the implementer: the shared-support definition is silent on transitive imports, helpers imported only by non-test files, and __init__.py and fixture data. Treating every non-test-module file under tests/ as shared support is a safe reading.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-30T20:51:10Z
verdict: NO BLOCKERS
proposal_stem: a-test-only-commit-s
content_digest: bb0ab14dd464685606cf7a4fedda4a1b99c7f1dae9f9823a84bfd46693169072
