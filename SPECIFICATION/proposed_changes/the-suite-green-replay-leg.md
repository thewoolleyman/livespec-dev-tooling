---
topic: the-suite-green-replay-leg
author: claude-opus-5-5:implement-test-performance
created_at: 2026-11-02T06:56:12Z
---

## Proposal: Suite-green replay leg

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a governing `## Suite-green replay leg` section to contracts.md, stating as BCP14 clauses the leg's scope (full suite for a behaviour-preserving commit; staged test modules only for a test-only cleanup unless shared test support is staged; exit 0 the only green outcome), its progress bound (a 900 s stall window via LIVESPEC_SUITE_GREEN_STALL_SECONDS that kills the whole process group, with LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS demoted to an optional total ceiling, and a duration-independent output checksum), its failure detail (--tb=line, failure_detail beside failure_summary), and same-tree reuse of a passing full pre-commit aggregate. Add six Given/When/Then scenarios covering those clause groups.

### Motivation

The commit-msg `red_green_replay` check's suite-green leg (`livespec_dev_tooling/checks/_red_green_replay_suite.py`, `_red_green_replay_modes.py`) has no governing spec heading anywhere. Only its test-only selection rule appears, as one bullet in non-functional-requirements.md and three scenarios. Two factory items that change the leg were refused for want of a clause to implement against: livespec-dev-tooling-t4rx4t (replace the fixed 2400 s total timeout, which kills slow but still-progressing suites, with a no-progress stall bound) and livespec-dev-tooling-z5fwwn (stop running the full suite a second time at commit-msg when pre-commit has just run the full aggregate to green on the identical tree). Both belong to plan implement-test-performance (livespec-dev-tooling-sv6m5p). This section gives the leg one authoritative contract. It records the shipped scope rule and the shipped failure detail from PR #3096 as current behaviour, and it states the two pending changes as spec-first clauses that name their owning work items. Its shared-test-support definition matches the shipped code: any staged path under `tests/` that is not a `test_*.py` module. That is broader than the non-functional-requirements.md bullet, which names `conftest.py` or an imported module. The contracts clause is the precise wire-level statement, and it is the one the leg's tests assert. The in-flight survey found no open spec-touching PR. The three remote `spec/*` branches (agent-hook-foreground-gate-refusal, factory-sandbox-environment-naming, local-gate-concurrency-limit) do not touch this leg, so this proposal aligns with them.

### Proposed Changes

Add the following new H2 section to `SPECIFICATION/contracts.md`, placed directly after §"Delegated commit-time replay test runs" (the section that governs WHERE the leg's tests run):

````markdown
## Suite-green replay leg

The commit-msg replay gate (`red_green_replay`) has three legs: the Red leg, the Green leg, and the suite-green leg (also called the green-verified leg). The suite-green leg runs when a commit stages product `.py` or test material and carries no Red awaiting a Green. It is realized by `livespec_dev_tooling/checks/_red_green_replay_suite.py`, dispatched from `red_green_replay.py` and `_red_green_replay_modes.py`. On a green outcome it records the `TDD-Suite-Green-Scope`, `TDD-Suite-Green-Output-Checksum` and `TDD-Suite-Green-Captured-At` trailers, which the commit-range validation accepts as the commit's verification evidence. This section is the governing contract of that leg. §"Delegated commit-time replay test runs" governs WHERE its test run executes. This section governs WHAT it runs, how a run is bounded, what a refusal reports, and when an earlier run on the same tree stands in for it. The progress-bound and same-tree-reuse bullets are spec-first: as of ratification the shipped leg bounds each run by a fixed total timeout (default 2400 s, `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS`) and always starts its own suite run.

- **Scope.** A behaviour-preserving commit, one that stages product `.py` with no Red awaiting a Green, MUST run the FULL pytest suite against the staged tree, and MUST record `TDD-Suite-Green-Scope: full-suite`. A test-only cleanup, one that stages test modules and no product `.py`, MUST run only its staged test modules and record `TDD-Suite-Green-Scope: staged-tests`, UNLESS the commit also stages shared test support. Shared test support is any staged path under `tests/` that is not a `test_*.py` test module, for example `conftest.py`, a package `__init__.py`, a fixture module or fixture data. A commit that stages shared test support MUST run the full suite, including a commit that stages shared test support and no test module. Exit `0` is the ONLY green outcome. Every non-zero exit MUST refuse the commit with a `suite-red` event. That includes pytest exit `5`, where no tests were collected, because an empty run proves nothing.
- **Progress bound.** The leg MUST end a run because the run has stopped making progress, never because the run is long. It MUST end the run only when the suite has printed no new output on stdout or stderr for a continuous stall window. The window defaults to 900 seconds and is overridden by `LIVESPEC_SUITE_GREEN_STALL_SECONDS`. An unset, non-numeric or non-positive value means the default. When the leg ends a run, it MUST kill the run's whole process group, pytest-xdist workers included. It MUST refuse the commit with an event that names the stall window and the variable that sets it, and it MUST NOT record any `TDD-Suite-Green-*` trailer. `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS` MUST no longer be a default bound. When it is set to a positive integer, it is an OPTIONAL total ceiling: a run that exceeds it ends the same way, and the refusal names that ceiling and its variable instead. When it is unset, no total ceiling applies. `TDD-Suite-Green-Output-Checksum` MUST NOT depend on how long the run took. It is computed over a canonical form of the output that drops xdist worker chatter and progress rows, normalizes pytest durations, and sorts the remaining lines, so a slow run and a fast run of the same green suite record the same checksum. This bullet is spec-first: the shipped leg still bounds each run by a fixed total timeout, `DEFAULT_TIMEOUT_SECONDS = 2400`, overridable by `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS`, and it ends a run that is still printing output when that timeout expires. Work item livespec-dev-tooling-t4rx4t owns the change.
- **Failure detail.** The leg MUST invoke pytest with `--tb=line`. A `suite-red` event MUST carry `failure_summary` and `failure_detail` side by side. `failure_summary` holds the failing node ids, or a bounded head of the output when pytest printed none. `failure_detail` holds the one-line traceback (`<path>.py:<line>: <exception text>`) of each failing test, bounded in size (4000 characters as shipped). A refused commit therefore names WHY each test failed, not only WHICH test failed. This bullet describes shipped behaviour (PR #3096).
- **Same-tree reuse.** When the pre-commit hook of the same commit has just run the FULL check aggregate to a passing result, on exactly the tree `git write-tree` names for the index when the commit-msg hook runs, the suite-green leg MUST record its `TDD-Suite-Green-*` trailers from that aggregate run, and MUST NOT start a second full suite run. The trailers MUST name the run that produced the evidence, so that a reader can tell reused evidence from a fresh run. The leg MUST run its suite in full, exactly as the Scope bullet states, in each of these cases: the aggregate run's tree differs from the tree being committed, the aggregate run was partial (it did not run the full suite), the aggregate run did not pass, or the leg cannot establish which tree the aggregate run judged. A reused result MUST NOT turn a failing or absent run into a green one. This bullet is spec-first: the shipped leg always starts its own suite run. Work item livespec-dev-tooling-z5fwwn owns the change.
````

Add the following six scenarios to `SPECIFICATION/scenarios.md`, placed directly after the existing "## Scenario: a test-only commit whose staged tests fail is refused" (the three existing test-only scope scenarios stay unchanged and continue to cover the test-only half of the Scope bullet):

````markdown
## Scenario: a behaviour-preserving commit runs the full suite, and an empty run is refused

Given a commit that stages `livespec_dev_tooling/foo.py` and no test file, whose `HEAD` carries no Red awaiting a Green

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST run the full pytest suite against the staged tree

And on pytest exit `0` it MUST record `TDD-Suite-Green-Scope: full-suite`, a `TDD-Suite-Green-Output-Checksum` and a `TDD-Suite-Green-Captured-At` trailer

And on any non-zero pytest exit, pytest exit `5` included, the commit MUST be refused with a `suite-red` event

## Scenario: a suite-green run that stops printing output for the stall window is ended

Given `LIVESPEC_SUITE_GREEN_STALL_SECONDS` is `60` and `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS` is unset

And the suite-green leg's pytest run prints no new output for 60 seconds

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST kill the run's whole process group, pytest-xdist workers included

And the commit MUST be refused with an event naming the 60-second stall window and `LIVESPEC_SUITE_GREEN_STALL_SECONDS`

And no `TDD-Suite-Green-*` trailer MUST be recorded

## Scenario: a long suite-green run that keeps printing output is not ended

Given `LIVESPEC_SUITE_GREEN_STALL_SECONDS` and `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS` are unset

And the suite-green leg's pytest run takes 3000 seconds, never going 900 seconds without new output, and exits `0`

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST NOT end the run

And it MUST record the same `TDD-Suite-Green-Output-Checksum` that a 300-second run of the same green suite records

## Scenario: a refused suite-green run names why each test failed

Given a commit whose suite-green leg selects `tests/test_alpha.py`, whose test `test_one` fails with `AssertionError: expected 2`

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST invoke pytest with `--tb=line`

And the `suite-red` event MUST carry a `failure_summary` naming `tests/test_alpha.py::test_one`

And the event MUST carry a `failure_detail` holding the line `tests/test_alpha.py:<line>: AssertionError: expected 2`

## Scenario: a suite-green leg reuses a passing full pre-commit aggregate on the same tree

Given the pre-commit hook of a behaviour-preserving commit has just run the full check aggregate to a passing result on tree `T`

And `git write-tree` names tree `T` for the index when the commit-msg hook runs

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST NOT start a pytest suite run

And it MUST record its `TDD-Suite-Green-*` trailers from the aggregate run, naming that run

## Scenario: a suite-green leg runs the full suite when the pre-commit aggregate judged a different tree or ran partially

Given the pre-commit hook of a behaviour-preserving commit ran the check aggregate on tree `T1`, or ran only part of the aggregate

And `git write-tree` names tree `T2` for the index when the commit-msg hook runs, or the aggregate run did not run the full suite

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST run the full pytest suite against the staged tree

And it MUST record its `TDD-Suite-Green-*` trailers only from that run
````

The revise commit that accepts this proposal MUST add one `tests/heading-coverage.json` entry per new `## ` heading above (seven: the contracts section and the six scenarios), each either linked to an exercising test or a spec-first `"test": "TODO"` row whose reason names the tier and the owning work item (livespec-dev-tooling-t4rx4t for the progress-bound rows, livespec-dev-tooling-z5fwwn for the same-tree-reuse rows), and regenerate `tests/heading-coverage-debt.json`.
