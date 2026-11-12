---
topic: red-green-replay-runs-a
author: claude-opus-5-5
created_at: 2026-11-12T04:17:53Z
---

## Proposal: A test-only commit's staged tests run once, delegated when the repository delegates replay runs

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a Suite-green replay leg bullet: for a test-only commit with no Red intent, the run that decides between the Red and suite-green legs is the suite-green leg's run, so the staged tests run once in total; when commit-time replay runs are delegated and the host can read the gates kubeconfig, that one run is the gate Job, no pytest starts on the committing host, and the suite-green trailers name the Job. Add two scenarios, local and delegated.

### Motivation

livespec-dev-tooling-fjpqqq (a child of plan dev-host-test-gate-load, filed on legacy-coordinator-agent's ruling (ii) of 2026-11-10) removes a doubled dev-host test run. `red_green_replay` decides between the Red and suite-green legs for a test-only commit with no Red intent by running the staged tests through a raw local pytest (`_staged_tests_pass`, livespec_dev_tooling/checks/red_green_replay.py), never through the delegated replay client, and on a pass the suite-green leg runs the same modules again on the identical tree. Measured 2026-11-10 on one staged module (gate run 20261110T140715Z-3669640): about 670 s in the probe plus 283 s re-running the same module, all on the dev host. At the 0.320.0 pre-dispatch wall (2026-11-12T04:15:16Z, spec v199) the spec-change-tier judgement found the asked-for behaviour partial: the ratified text states that a test-only commit runs only its staged modules and that a delegated suite-green leg runs as a gate Job, but it does not state that the deciding probe is delegated too, nor that the staged tests run only once. It named ## Suite-green replay leg as the heading to generalize and linked this topic, red-green-replay-runs-a. This proposal ratifies the one-run rule there, so fjpqqq can dispatch. The existing **Same-tree reuse** bullet covers reuse of a full pre-commit aggregate and is unchanged.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Suite-green replay leg", insert this bullet directly after the "**Same-tree reuse.**" bullet:

- **One run of a test-only commit's staged tests.** For a test-only commit whose subject declares no Red intent, the run of its staged test modules that decides between the Red leg and the suite-green leg MUST also be the suite-green leg's run: the replay gate MUST run those staged test modules once in total for that commit, in whichever venue it runs them, and MUST NOT run them a second time on the identical staged tree. When the repository delegates its commit-time replay test runs and the committing host can read the gates kubeconfig (§"Delegated commit-time replay test runs"), that one run MUST be the delegated gate Job, so no pytest process starts on the committing host, and the commit's `TDD-Suite-Green-*` trailers MUST name that Job. The commit records `TDD-Suite-Green-Scope: staged-tests` in either venue.

In SPECIFICATION/scenarios.md, add these two scenarios directly after "## Scenario: a suite-green leg reuses a passing full pre-commit aggregate on the same tree" (each heading preceded and followed by a blank line, matching the surrounding scenarios):

## Scenario: a passing test-only commit with no Red intent runs its staged tests once on the committing host

Given a repository that does not delegate its commit-time replay test runs

And a test-only commit whose subject declares no Red intent and whose staged test modules pass

When the commit-msg replay gate runs

Then it MUST run the staged test modules exactly once for that commit

And it MUST record `TDD-Suite-Green-Scope: staged-tests`

## Scenario: a passing test-only commit with no Red intent runs its staged tests once in one delegated gate Job

Given a repository that delegates its commit-time replay test runs, on a committing host that can read the gates kubeconfig

And a test-only commit whose subject declares no Red intent and whose staged test modules pass

When the commit-msg replay gate runs

Then the staged test modules MUST run exactly once, in one gate Job

And no pytest process MUST start on the committing host

And the commit MUST record `TDD-Suite-Green-Scope: staged-tests` with `TDD-Suite-Green-*` trailers that name that gate Job

The revise that accepts this MUST add a `tests/heading-coverage.json` row for each new scenario in the same commit, as a spec-first `"test": "TODO"` row at the integration tier owned by `"work_item": "livespec-dev-tooling-fjpqqq"`, and regenerate the heading-coverage debt register.
