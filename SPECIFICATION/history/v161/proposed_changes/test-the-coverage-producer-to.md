---
topic: test-the-coverage-producer-to
author: claude-opus-5-5
created_at: 2026-11-07T20:33:34Z
---

## Proposal: The coverage producer-to-consumer handoff is tested, and ci.yml-reading tests run on workflow commits

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Tests pin the coverage handoff in ci.yml and the stamp over the final bytes, and the pre-commit gate runs ci.yml-reading tests when a commit changes a workflow or a script it invokes.

### Motivation

Commit 34f370e1 changed the consumer's precondition while ci.yml kept shipping `.coverage` alone, and no test read ci.yml for the receipt wiring. A second defect stamped the receipt before the data was rewritten, which passed a green proof and was only caught when master fell back. A workflow-only commit also skipped the tests that would have caught the first (research note plan/ci-runtime-and-cost/research/006-coverage-fallback-post-mortem-2026-11-06.md on livespec-dev-tooling). Carries work item livespec-dev-tooling-cj5dg5.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "## Hooks and CI", add this paragraph:

**The coverage handoff is tested, and workflow commits run the tests that read ci.yml.** A test MUST fail, naming the missing step, when the check-per-file-coverage job does not upload `.livespec-coverage-reuse-token` together with `.coverage`, with hidden files included and a missing file an error, or when the check-coverage job does not download both before it runs `just check-coverage`. A test MUST run the real per-file coverage report over a fixture that measures a source file deleted before report time, and MUST assert that the stamped receipt equals `scripts/just/coverage-reuse-id.sh` over the final rewritten `.coverage`. When a commit stages a change under `.github/workflows/` or `scripts/just/` and no `.py` file, the pre-commit gate MUST run the test files that read `.github/workflows/ci.yml` and MUST refuse the commit when one fails.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario: a commit that changes only a workflow runs the tests that read ci.yml

Given a commit stages a change under `.github/workflows/` or `scripts/just/` and no `.py` file
And a test that reads `.github/workflows/ci.yml` fails on the staged tree

When the pre-commit gate runs

Then it MUST run the test files that read `.github/workflows/ci.yml`
And it MUST refuse the commit

## Scenario: the coverage receipt is stamped over the final rewritten data

Given a coverage fixture that measures a source file deleted before report time

When the per-file coverage report runs over it

Then the stamped receipt MUST equal `scripts/just/coverage-reuse-id.sh` over the final rewritten `.coverage`
