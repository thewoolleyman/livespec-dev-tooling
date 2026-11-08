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

When the suite-green leg ends a run for stalling, its refusal event MUST say how far the run got and what held it. It names the seconds elapsed since the run started and how many tests had completed out of how many were collected. It names the last test the run reported complete and when, or says that no test had completed, which means the run ended during collection or worker start-up. It names every test still running, with its elapsed time and pytest-xdist worker, and says whether the run stalled mid-suite or after its last collected test had completed. It also carries the output the leg received from the run. A run that completes no test for the window MUST still be ended with the same failed verdict. A stall can then be diagnosed before anyone changes the bound.

### Motivation

A stall kill today says only that the window passed. On 2026-11-07 the gmktec factory's janitor killed the suite-green leg twice within ten minutes, both times on trees whose suites pass: bd-ib-ivm24w (run 01M6VRFX0CKFS6P47XXYHFRN42, janitor@2, killed 23:24:31Z) and bd-ib-t3bnab (run 01M6VRMWZM6SDYMJ746S4PKZJB, janitor@2, killed 23:16:03Z). Both ran `pytest --tb=line -q -n 4` over the full suite, chosen because the janitor's refresh merge staged default-branch product files.

The two stage logs carry no pytest output at all. On a kill, the leg logs its refusal event without the output it drained from the run, so every captured line is discarded. That loss is a defect of its own, and this proposal makes the refusal keep the drained output. Each kill came about 902.4 seconds after the run was spawned (23:09:28.876Z to 23:24:31.416Z, and 23:01:00.645Z to 23:16:03.023Z). The stall window is 900 seconds, measured from the latest chunk received. So the last chunk either run delivered arrived at most about 2.5 seconds after spawn, and no test-completion character reached the runner afterwards. That is arithmetic over the window, not an observation of the run.

Output buffering does not explain it. The runner already sets PYTHONUNBUFFERED=1. Plan seat dev-host-test-gate-load measured on the dev host, 2026-11-08 at about 01:20Z, that "pytest -q run through a pipe the way suite_pytest_argv runs it delivers one '.' per completed test as that test completes, serial and under -n 2. So a stall kill means the session completed no test for 15 minutes." At about 01:45Z the same seat measured that pytest -q writes nothing to that pipe until its first test completes. Under -n 2 even "bringing up nodes..." arrives only with the first '.'. Both kills therefore ended a run that had not finished collection and worker start-up, about 8,300 tests across 4 workers on a starved factory host. The fix for that cause is livespec-dev-tooling-6o3m6m (plan dev-host-test-gate-load). It is not part of this proposal. A stall can also be one long test, or a silent tail after the last test (teardown and the summary) outrunning the window. Today's refusal cannot tell any of these apart. Under `-q` a passing test prints no node id, so the refusal cannot name the test either, and the leg needs a per-test record rather than the pytest output stream.

Raising the window would hide the cause, so livespec-dev-tooling-h2i4u2 (owner plan fleet-flaky-tests, epic livespec-dev-tooling-zwveqp) makes the next kill diagnose itself first. The completed count and the last completed test separate "no test ever completed" from "the run stopped part-way". The running tests and their workers point at a hung or long test, and the post-last-test report isolates a stalled teardown or summary. The leg can learn all of this from a pytest hook that records each test's collection, start and finish. This library already loads such a plugin wherever the leg runs. This proposal also carries the three assertions of livespec-dev-tooling-3tzncf, which legacy-coordinator-agent closed on 2026-11-08 as a duplicate of h2i4u2. The cause fix stays a deferral in plan dev-host-test-gate-load.

FLEET SCOPE: the leg ships in livespec-dev-tooling (`_red_green_replay_suite_runner.py` and `_red_green_replay_suite.py`). Every consumer repository's commit hooks and factory janitor at a pin carrying livespec-dev-tooling-t4rx4t's progress bound get the richer refusal through a release and the consumer pin sweep, with no per-repository edit.

### Proposed Changes

In `SPECIFICATION/contracts.md`, "## Suite-green replay leg", in the "Progress bound" bullet, replace this sentence:

It MUST refuse the commit with an event that names the stall window and the variable that sets it, and it MUST NOT record any `TDD-Suite-Green-*` trailer.

with these sentences:

It MUST refuse the commit with a failed verdict whose event names the stall window and the variable that sets it, the seconds elapsed since the run started, how many tests had completed out of how many were collected (or that collection had not finished), the node id of the last test the run reported complete and the instant it completed, every test that was still running when the run was ended, with how long it had run and which pytest-xdist worker ran it, and the output the leg had received from the run. When no test had completed, the event MUST say so in place of a last test, which means the run was ended during collection or worker start-up. These facts MUST come from a per-test record the leg keeps, not from the pytest output stream, which under `-q` names no passing test and carries nothing until the first test completes. When every collected test had completed before the run was ended, the event MUST say that the run stalled after its last test rather than mid-suite. A run that completes no test within the window MUST be ended with that same failed verdict. The leg MUST NOT record any `TDD-Suite-Green-*` trailer.

No other sentence of the bullet changes. The stall window, its default of 900 seconds, its variable, and the optional total ceiling are unchanged. This proposal changes only what a stall refusal reports.

In `SPECIFICATION/scenarios.md`, add these three scenarios directly after "## Scenario: a suite-green run that stops printing output for the stall window is ended", in this order:

## Scenario: a stalled suite-green run names the tests that were still running

Given `LIVESPEC_SUITE_GREEN_STALL_SECONDS` is `60` and `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS` is unset

And the suite-green leg's pytest run collects three tests, one of which completes, and another keeps running past 60 seconds without printing output

When the commit-msg `red_green_replay` check ends the run for stalling

Then the refusal event MUST name the seconds elapsed since the run started and that 1 of 3 collected tests had completed

And the refusal event MUST name the node id of the completed test and the instant it completed

And the refusal event MUST name the still-running test, how long it had run and the pytest-xdist worker that ran it

And the refusal event MUST say that the run stalled mid-suite

And the refusal event MUST carry the output the leg had received from the run

## Scenario: a suite-green run that stalls after its last test is reported as a post-last-test stall

Given `LIVESPEC_SUITE_GREEN_STALL_SECONDS` is `60` and `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS` is unset

And every test the suite-green leg's pytest run collected has completed, and the run then prints no output for 60 seconds before it exits

When the commit-msg `red_green_replay` check ends the run for stalling

Then the refusal event MUST say that the run stalled after its last test rather than mid-suite

And the refusal event MUST name the node id of the last test the run reported complete and that all of its collected tests had completed

## Scenario: a suite-green run ended before any test completed says that no test had completed

Given `LIVESPEC_SUITE_GREEN_STALL_SECONDS` is `60` and `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS` is unset

And the suite-green leg's pytest run completes no test for 60 seconds, because its collection or worker start-up has not finished

When the commit-msg `red_green_replay` check ends the run for stalling

Then the commit MUST be refused with a failed verdict naming the 60-second stall window

And the refusal event MUST say that no test had completed, in place of a last completed test

And no `TDD-Suite-Green-*` trailer MUST be recorded

The existing scenario "a suite-green run that stops printing output for the stall window is ended" MUST keep its heading and text.

The revise pass adds all three new scenario headings to `tests/heading-coverage.json` in the revise commit. Each is a spec-first TODO row whose reason names the integration tier or above and whose `work_item` is livespec-dev-tooling-h2i4u2. The pass then regenerates `tests/heading-coverage-debt.json`.
