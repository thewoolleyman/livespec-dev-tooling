---
topic: the-check-aggregate-s-tail
author: claude-opus-5-5 (dev-host-test-gate-load)
created_at: 2026-11-07T22:22:18Z
---

## Proposal: The check aggregate's tail digest names a failed target's failing tests

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a contracts.md H2, Check aggregate tail digest, requiring the tail failure-mode digest of just check to report a failed target whose output carries a pytest test summary as failing tests, naming each failing test. A check-per-file-coverage refusal with every test passing is reported as coverage, naming each file below threshold. Add one scenario. Today a coverage target that fails because tests failed is reported only as having failed without a structured failure_mode.

### Motivation

livespec-dev-tooling-nvh3dl (plan dev-host-test-gate-load) carries this behaviour, and its spec-change-tier record links this topic. The only digest clause today (contracts.md `## Shared check inventory`, Tail digest) is specific to one check's non_canonical_body findings. Measured by sandbox-commit-gate-ceiling from run exports: livespec-dev-tooling-js3cum's run 01M6V7SGBQXF reported its coverage target as failed without a structured failure_mode after 3358.6 s; the cause was 3 failed tests in test_gate_runner_delegate.py. check-per-file-coverage runs the whole pytest suite, so a coverage refusal is usually failing tests, and the mislabel sent a failure class costing $70.63 to the wrong reading. The digest is livespec-dev-tooling's own (check_failure_digest.py via parallel_check_dispatcher.py); no other fleet repository routes its aggregate through it, so this clause governs this repository's just check only.

### Proposed Changes

Add this H2 to contracts.md, after `## Gate-surface severity levers` (or after `## Delegated gate-runner runs` if that heading is not present):

## Check aggregate tail digest

The `just check` aggregate restates each failed target's failure at the tail of its output, because the target's own findings scroll off. This section states what that digest reports for a target whose failure is failing tests.

- **Failing tests are named.** When a target of the aggregate fails and its captured output carries a pytest test summary naming failed tests, the tail digest MUST report that target's failure as failing tests and MUST name each failing test's node id.
- **Coverage is named.** When `check-per-file-coverage` fails with every test passing because one or more files are below their coverage threshold, the tail digest MUST report that target's failure as coverage and MUST name each such file.
- **Order.** When a target's output carries both failed tests and files below threshold, the tail digest MUST report the failing tests first.
- **No invented cause.** A failed target whose output carries neither a structured finding nor a pytest test summary MUST still be reported as having failed without a structured `failure_mode`. The digest MUST NOT change any target's verdict, and every name it prints MUST come from that target's own output.

Add this scenario to scenarios.md:

## Scenario: a coverage target that fails on failing tests is reported as failing tests in the tail digest

```gherkin
Given a tree on which three tests fail when check-per-file-coverage runs the suite
When just check runs on that tree
Then the tail failure-mode digest MUST report check-per-file-coverage as failing tests
And it MUST name the node id of each of the three failing tests
And it MUST NOT report that target as having failed without a structured failure_mode
```
