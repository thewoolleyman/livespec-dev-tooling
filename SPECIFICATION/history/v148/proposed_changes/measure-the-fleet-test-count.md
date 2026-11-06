---
topic: measure-the-fleet-test-count
author: claude-opus-5-5
created_at: 2026-11-06T17:07:28Z
---

## Proposal: Rule-26 test-suite baseline: on-demand `just fleet-test-baseline`

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a **Test-suite baseline** bullet to contracts.md §"Rule-26 mutation kill matrix", after the Advisory-only bullet, and one scenario to scenarios.md. Together they govern an on-demand `just fleet-test-baseline` recipe in livespec-dev-tooling. Given the paths of sibling repository clones, it measures each repository's exact test count and its test-only wall-clock by one stated method, and emits one JSON document with per-repository values and fleet totals. The rule-26 section today governs the kill matrix that selects tests for removal, but nothing governs the before-and-after measurement that shows the removal shrank the suite.

### Motivation

Plan fleet-mutation-testing-rule-26 (epic livespec-dev-tooling-oi2two) must report each fleet repository's test count and test-suite runtime before and after the tests that the kill matrices prove redundant are removed, measured the same way both times (plan assertions A6, A7 and A8). No test-only runtime baseline exists anywhere in the fleet. The consuming work item livespec-dev-tooling-phakbp was ticketed on 2026-11-06 and refused before listing as spec-change tier. The judgement linked this topic and named §"Rule-26 mutation kill matrix" as the heading to generalize, because no ratified text describes the recipe, the counting methods, the timing method or the totals. The measurement belongs in that section because it exists to evaluate rule-26 pruning. Like the kill-matrix recipe, it must stay out of every gate.

### Proposed Changes

Add the following bullet to `SPECIFICATION/contracts.md` §"Rule-26 mutation kill matrix", immediately after the **Advisory only.** bullet:

- **Test-suite baseline.** livespec-dev-tooling MUST expose a `just fleet-test-baseline` recipe. Given the paths of one or more repository clones, it measures each repository's exact test count and test-only wall-clock, so that rule-26 pruning can be judged before and after by one method. The count MUST be taken per ecosystem: the collected-test total of `pytest --collect-only -q -p no:cacheprovider` for a Python repository, the test count reported by `cargo nextest list --message-format json` for a Rust workspace, and one per executed `*.test.sh` script for a repository whose tests are shell scripts. The wall-clock MUST be the elapsed time of that repository's own test-only command, never of the `just check` aggregate. The recipe MUST emit one machine-readable JSON document carrying, per repository, the test count, the wall-clock, the counting command and the test command it timed. The document MUST also carry the timing method, the host identity and the toolchain versions used, and a fleet total test count and a fleet total wall-clock equal to the sums of the per-repository values. The recipe MUST be on demand only, under the same exclusions as `just mutation-kill-matrix`: it MUST NOT be a member of the `just check` aggregate, MUST NOT run from any commit-time or push-time hook, and MUST NOT be a required per-PR CI job.

Add the following scenario to the end of `SPECIFICATION/scenarios.md`:

## Scenario: the fleet test baseline reports per-repository counts and fleet totals

Given a Python repository whose pytest suite collects 5 tests, a Rust workspace whose `cargo nextest list --message-format json` reports 3 tests, and a repository with 2 `*.test.sh` scripts

When `just fleet-test-baseline` runs over those three clones

Then the JSON document MUST report test counts of 5, 3 and 2 for those repositories, each with its counting command, its timed test command and its wall-clock

And the document MUST report a fleet total test count of 10 and a fleet total wall-clock equal to the sum of the three wall-clocks

And the document MUST name the timing method, the host identity and the toolchain versions
