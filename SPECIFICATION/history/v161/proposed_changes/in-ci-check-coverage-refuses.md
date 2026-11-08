---
topic: in-ci-check-coverage-refuses
author: claude-opus-5-5
created_at: 2026-11-07T20:33:16Z
---

## Proposal: In CI, check-coverage refuses a missing or stale coverage receipt

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

The GitHub Actions coverage consumer reuses the producer's data or fails by name, and never falls back to a full test run.

### Motivation

From 2026-11-04 every livespec-dev-tooling CI run silently re-ran the whole suite in check-coverage, because the consumer treated a failed reuse as a green path. The verdict was correct and the cost was about 15 times higher, with one log line as its only trace (research note plan/ci-runtime-and-cost/research/006-coverage-fallback-post-mortem-2026-11-06.md on livespec-dev-tooling). A local run keeps measuring, since it has no producer to reuse. Carries work item livespec-dev-tooling-s2esff.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "## Code coverage thresholds", add this paragraph:

**The CI coverage consumer never falls back to a full run.** When `scripts/just/check-coverage.sh` runs as the GitHub Actions coverage consumer it MUST read the producer's `.coverage` and the `.livespec-coverage-reuse-token` receipt beside it, and MUST NOT start a pytest process. A missing receipt, a receipt whose data digest differs from the sha256 of the downloaded `.coverage`, and a receipt whose tree digest differs from the checkout's tracked-tree digest MUST each exit non-zero with a message naming that cause. With a matching receipt it MUST exit zero at a 100 percent total and non-zero below it. Outside GitHub Actions with no reusable data, `just check-coverage` MUST still run and measure the clean suite.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario: a CI coverage consumer with no usable receipt fails by name and starts no test run

Given the GitHub Actions coverage consumer is running
And the receipt is missing, or its data digest or tree digest does not match

When `scripts/just/check-coverage.sh` runs

Then it MUST exit non-zero with a message naming the cause
And it MUST NOT start a pytest process

## Scenario: a CI coverage consumer with a matching receipt judges the producer's data

Given the GitHub Actions coverage consumer is running
And the receipt matches the downloaded data and the checkout

When `scripts/just/check-coverage.sh` runs

Then it MUST read the producer's data without starting a pytest process
And it MUST exit zero at a 100 percent total and non-zero below it

## Scenario: a local coverage run with no reusable data still measures

Given `just check-coverage` runs outside GitHub Actions
And no reusable coverage data is present

When it runs

Then it MUST run and measure the clean suite
