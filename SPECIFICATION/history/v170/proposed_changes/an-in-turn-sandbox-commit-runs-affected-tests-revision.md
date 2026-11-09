---
proposal: an-in-turn-sandbox-commit-runs-affected-tests.md
decision: modify
revised_at: 2026-11-09T18:37:11Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:implement-test-performance
---

## Decision and Rationale

Modified under delegated mode. The maintainer approved this proposal on 2026-11-09 at about 08:45Z (attended, plan implement-test-performance), satisfying coordinator-duties section 12 for a quality-gate narrowing. Every in-turn factory-sandbox commit still runs the whole suite at commit-msg (1079-1286 s each on 2026-11-06), after orchestrator Scenario 255 already narrowed its pre-commit to the affected-tests gate. The narrowing is gated on the sandbox-exemption marker, so every host commit keeps the full suite. The final tree is still judged in full by the janitor's aggregate and by PR CI. Carries plan assertions 2 and 6; implementation item livespec-dev-tooling-svjqbe. The independent read-only reviewer (sonnet) found no blockers on the exact bytes.

## Modifications

Reconciled with v166's Behaviour-preserving claim bullet, which merged after this proposal was filed. The bullet's "MUST run only the test paths" became "MUST run a suite run that covers only the test paths", and a sentence states that the Behaviour-preserving claim's parent-tree replay applies to such a commit unchanged and is not part of the narrowed suite run. A further sentence settles precedence, which the reviewer raised: when the Same-tree reuse bullet also applies, because a passing full aggregate recorded evidence for the same tree, that bullet governs and the affected-tests bullet does not. The commit-range validation accepts affected-tests "subject to the Behaviour-preserving claim bullet exactly as for any other scope". Scenario 1's "Then it MUST run only ... and MUST NOT run the full suite" became "Then its suite run MUST cover only ... and MUST NOT be the full suite". From the pre-merge doctor LLM pass: §"Delegated commit-time replay test runs", which closed-listed a suite-green leg's scopes as staged test modules or the full suite, now also names the affected tests a sandbox commit recorded. The Scope bullet's cross-reference clause, both headings and the other text are as proposed. The bullet sits after Local-aggregate evidence entry point, and the scenarios after the last scenario a-consumer-whose-pre-commit adds, as the proposal directs.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T18:36:42Z
verdict: NO BLOCKERS
proposal_stem: an-in-turn-sandbox-commit-runs-affected-tests
content_digest: eee9e0497fd89216c26abfb0fc693393f8ac5cb23767e23a30faa0cae7b85407
