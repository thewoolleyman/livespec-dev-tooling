---
topic: a-test-only-commit-s
author: claude-opus-5-5:petri-factory-on-gmktec
created_at: 2026-10-29T09:39:36Z
---

## Proposal: State the test-only suite-green leg of the red_green_replay check

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend ## Test-Driven Development discipline so the red_green_replay check's leg for a commit that stages only tests is ratified: it runs only the staged tests unless shared test support changed, runs the full suite when it did, and refuses the commit when the touched tests fail.

### Motivation

Work-item livespec-dev-tooling-h3gcs6 asks to narrow the test-only suite-green leg, which today runs the FULL suite on the host at commit-msg time. A seat's canary commit sat over 21 minutes in commit-msg check-red-green-replay, past the harness's 20-minute background move, where such runs have historically been killed with no verdict. The orchestrator's spec-change-tier gate held h3gcs6 at dispatch on 2026-10-29 (topic a-test-only-commit-s) because the ratified text states the Red-Green pair is enforced at commit-msg time but says nothing about a test-only commit's suite-green leg; the item itself records that the leg is unratified. Ratifying the rule lets the item be implemented. The full suite still runs at pre-push (delegated where the repository opts in) and in CI, so narrowing the commit-time leg removes duplicated host work without reducing what gates a merge. The shared-support rule exists because a change to a conftest.py or a fixture module can break tests the commit does not name.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, under ## Test-Driven Development discipline, after the bullet that begins 'The Red → Green commit pair is enforced by the `red_green_replay` check at commit-msg time', add:

- For a commit that stages only test files, the `red_green_replay` check's suite-green leg MUST run only the tests in the staged test files, unless the commit also stages a shared test-support file. A shared test-support file is a `conftest.py` or any module under `tests/` that another test module imports. When the commit stages one, the leg MUST run the full suite. A test-only commit whose run tests fail MUST be refused. The full suite still runs at pre-push and in CI, so this leg narrows commit-time work and does not narrow what gates a merge.

In SPECIFICATION/scenarios.md, append:

## Scenario: a test-only commit runs only its staged tests unless shared test support changed

Given a commit that stages only `tests/test_alpha.py` and no implementation file and no shared test-support file

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it runs only the tests in `tests/test_alpha.py`, not the full suite

Scenario: a test-only commit that changes shared test support runs the full suite

Given a commit that stages only test files, one of which is `tests/conftest.py`

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it runs the full suite

Scenario: a test-only commit whose staged tests fail is refused

Given a commit that stages only `tests/test_alpha.py`, one of whose tests fails

When the commit-msg `red_green_replay` check runs its suite-green leg

Then the commit is refused

The revise that accepts this proposal MUST add a tests/heading-coverage.json entry for the new scenario heading, with test "TODO" and a reason naming livespec-dev-tooling-h3gcs6 as the implementing item.
