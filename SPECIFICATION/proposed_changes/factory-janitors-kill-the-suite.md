---
topic: factory-janitors-kill-the-suite
author: claude-opus-5-5
created_at: 2026-11-08T01:17:10Z
---

## Proposal: A stalled suite-green run names the tests that were still running

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When the suite-green leg ends a run for stalling, its refusal event MUST also name every test still running, with its elapsed time and pytest-xdist worker, and the instant the most recent test finished, so a stall can be diagnosed before anyone changes the bound.

### Motivation

A stall kill today says only that the window passed. On 2026-11-07 the gmktec factory's janitor killed the suite-green leg twice within ten minutes, both times on trees whose suites pass: bd-ib-ivm24w (run 01M6VRFX0CKFS6P47XXYHFRN42, janitor@2, killed 23:24:31Z) and bd-ib-t3bnab (run 01M6VRMWZM6SDYMJ746S4PKZJB, janitor@2, killed 23:16:03Z). Both ran `pytest --tb=line -q -n 4` over the full suite, chosen because the janitor's refresh merge staged default-branch product files. Neither refusal can say whether a test hung, all four workers were inside long tests, the sandbox was starved of CPU, or tests finished while their output did not reach the runner. The runner already sets PYTHONUNBUFFERED=1, so Python output buffering is not the cause; the rest is unknown.

Raising the window would hide the cause, so livespec-dev-tooling-h2i4u2 (owner plan fleet-flaky-tests, epic livespec-dev-tooling-zwveqp) makes the next kill diagnose itself first. The instant the most recent test finished is what separates "no test progressed" from "tests progressed but the output did not arrive". The running tests and their workers point at a hung or long test. The leg can learn both from a pytest hook that records each test's start and finish, which this library already loads as a plugin wherever the leg runs.

FLEET SCOPE: the leg ships in livespec-dev-tooling, so every consumer repository's commit hooks and factory janitor at a pin carrying livespec-dev-tooling-t4rx4t's progress bound get the richer refusal through a release and the consumer pin sweep, with no per-repository edit.

### Proposed Changes

In `SPECIFICATION/contracts.md`, "## Suite-green replay leg", in the "Progress bound" bullet, replace this sentence:

It MUST refuse the commit with an event that names the stall window and the variable that sets it, and it MUST NOT record any `TDD-Suite-Green-*` trailer.

with this sentence:

It MUST refuse the commit with an event that names the stall window and the variable that sets it, every test that was still running when the run was ended with how long it had run and which pytest-xdist worker ran it, and the instant the most recent test finished (or that none had finished), and it MUST NOT record any `TDD-Suite-Green-*` trailer.

No other sentence of the bullet changes. The stall window, its default of 900 seconds, its variable, and the optional total ceiling are unchanged; this proposal changes only what a stall refusal reports.

In `SPECIFICATION/scenarios.md`, add this scenario directly after "## Scenario: a suite-green run that stops printing output for the stall window is ended":

## Scenario: a stalled suite-green run names the tests that were still running

Given `LIVESPEC_SUITE_GREEN_STALL_SECONDS` is `60` and `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS` is unset

And the suite-green leg's pytest run has one test that keeps running past 60 seconds without printing output, after another test has finished

When the commit-msg `red_green_replay` check ends the run for stalling

Then the refusal event MUST name the still-running test, how long it had run and the pytest-xdist worker that ran it

And the refusal event MUST name the instant the most recent test finished

The existing scenario "a suite-green run that stops printing output for the stall window is ended" MUST keep its heading and text.

The revise pass adds the new scenario heading to `tests/heading-coverage.json` in the revise commit, as a spec-first TODO row at the integration tier whose `work_item` is livespec-dev-tooling-h2i4u2, and regenerates `tests/heading-coverage-debt.json`.
