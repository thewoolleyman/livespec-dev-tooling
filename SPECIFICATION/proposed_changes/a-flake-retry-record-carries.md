---
topic: a-flake-retry-record-carries
author: claude-opus-5-5
created_at: 2026-11-07T23:15:46Z
---

## Proposal: A flake-retry record carries each failed attempt's failure text

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Each re-run node id's JSON record under `tmp/flake-retries/` MUST carry a `failures` list holding each failed attempt's failure text, cut to at most 4000 characters, and the `FLAKE-RETRIED` block MUST show the first line of each failed attempt's failure text, so a retried flake in CI can be diagnosed from its own record and job log.

### Motivation

A re-run that passes leaves no trace of WHY the first attempt failed. The record and the `FLAKE-RETRIED` block name only the node id, attempts and outcome, and the job log of a passing retry shows only `2 attempts, passed`. So every root-fix item filed from a retry reaches its owner with no cause.

Measured on 2026-11-07, from the first three `flake-retries` artifacts of this repository: livespec-dev-tooling-vzfxlg could not be reproduced in 144 isolated runs, so its cause is still unknown. livespec-dev-tooling-gokm2v, a repeat flake of the gate renderer's exit suite after five root fixes, cannot name the shell case that failed, although the wrapping test's own assertion message prints it; the retry dropped it. gokm2v now depends on this change before any fix is attempted. livespec-dev-tooling-wacdfl's first attempt most likely hit a 600 s bound, which the record cannot confirm.

FLEET SCOPE: the plugin is a `pytest11` entry point of livespec-dev-tooling, so it loads in every pytest session of every repository that installs the package. As of 2026-11-07 that is livespec-dev-tooling itself, livespec, livespec-runtime, livespec-orchestrator-beads-fabro, livespec-orchestrator-git-jsonl, livespec-overseer, livespec-driver-claude, livespec-driver-codex, livespec-driver-pi, livespec-console-beads-fabro, dolt-server, hetzner-xubuntu-info and livespec-tdd-proof. They receive the change through a release of livespec-dev-tooling and the consumer pin sweep, with no per-repository edit.

Why a bound: the records are uploaded as a CI artifact (livespec-dev-tooling-mngdtf, and the consumer delivery of consumer-ci-delivers-no-flake) and read by the host-side reader (livespec-dev-tooling-h77qmw). 4000 characters per failed attempt is enough for an assertion message and its nearest frames, and caps a record at about 16 KB even when all four attempts fail. Why the first line in the block: the block is read in a CI log, and the first line of pytest's long representation is normally the failing assertion or exception.

Implementation carrier: livespec-dev-tooling-b7l6it, whose Definition of Done states these two assertions. Owner plan: fleet-flaky-tests (epic livespec-dev-tooling-zwveqp).

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, "## Testing approach", in the "Untouched-test retry" bullet, replace this sentence:

Every re-run test MUST be reported loudly: a `FLAKE-RETRIED` block in the terminal summary naming the node id, attempts and final outcome; one JSON line per node id under `tmp/flake-retries/`; and, under GitHub Actions, a `::warning` annotation naming the node id.

with this sentence:

Every re-run test MUST be reported loudly: a `FLAKE-RETRIED` block in the terminal summary naming the node id, attempts and final outcome, and beneath them the first non-empty line of each failed attempt's failure text; one JSON line per node id under `tmp/flake-retries/` carrying the node id, attempts, final outcome and a `failures` list that holds, in attempt order, one entry per failed attempt with that attempt's failure text, which is pytest's long representation of the failure cut to at most 4000 characters and marked as cut when it was; and, under GitHub Actions, a `::warning` annotation naming the node id.

No other sentence of the bullet changes, and the sibling "Flake-retry record delivery" bullet proposed by consumer-ci-delivers-no-flake is unaffected: the records it publishes simply carry the new field.

In `SPECIFICATION/scenarios.md`, add this scenario directly after "## Scenario: an untouched test that fails every attempt still fails the session":

## Scenario: a re-run test's record and summary carry each failed attempt's failure text

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a failing test the run's change set does not touch, whose first attempt fails with a failure text longer than 4000 characters and whose second attempt passes

When the session ends

Then the test's JSON line under `tmp/flake-retries/` MUST carry a `failures` list with exactly one entry, holding the first 4000 characters of that attempt's failure text, marked as cut

And the `FLAKE-RETRIED` block MUST show, beneath the test's node id, the first non-empty line of that attempt's failure text

The revise pass adds that scenario heading to `tests/heading-coverage.json` in the revise commit, as a spec-first TODO row at the integration tier whose `work_item` is livespec-dev-tooling-b7l6it, and regenerates `tests/heading-coverage-debt.json`.

The existing scenarios "a failing test the run did not touch is retried on its own and reported as a flake" and "an untouched test that fails every attempt still fails the session" MUST keep their headings and text; the new scenario states the added reporting on its own.
