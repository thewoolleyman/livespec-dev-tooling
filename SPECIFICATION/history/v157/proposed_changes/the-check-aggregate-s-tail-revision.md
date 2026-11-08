---
proposal: the-check-aggregate-s-tail.md
decision: modify
revised_at: 2026-11-08T02:31:06Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted with one modification. The proposal states that the tail digest reports a failure 'as failing tests' and 'as coverage' but never names the structured failure_mode, and check_failure_digest.py groups and prints findings by that token, so the behaviour was not testable as written (post-step doctor finding of 2026-11-07). The modification names the tokens failing_tests and coverage_below_threshold, in the snake_case convention of this repository's checks, and carries them into the Order bullet and the scenario's Then-line. Nothing else changes. Implementation is carried by livespec-dev-tooling-nvh3dl, which must introduce both tokens; neither exists in livespec_dev_tooling today.

## Modifications

Named the two failure_mode tokens: 'as failing tests' became 'with failure_mode failing_tests', and 'as coverage' became 'with failure_mode coverage_below_threshold'. The Order bullet now reads 'the failing_tests finding first', and the scenario's Then-line reads 'with failure_mode failing_tests'.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T02:29:59Z
verdict: NO BLOCKERS
proposal_stem: the-check-aggregate-s-tail
content_digest: 7d6df6b5652be8773fd0d2c469a112f7509074f911b3d64feadc349465b8abfa
