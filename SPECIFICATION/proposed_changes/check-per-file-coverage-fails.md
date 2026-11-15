---
topic: check-per-file-coverage-fails
author: claude-opus-5-5
created_at: 2026-11-15T17:15:10Z
---

## Proposal: check-per-file-coverage names each failing test and its assertion in its own output

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

State that the whole-suite coverage target's own output (local, sandbox and CI job log) names every failing test's node id and assertion text, beside the existing clause that makes the same target print its thirty slowest test phases. Today's behaviour already does this; the spec does not require it, so nothing stops a later change (a quieter -q/--tb/-r) from removing it. The existing §"Check aggregate tail digest" covers only the `just check` aggregate's tail, not the standalone CI job.

### Motivation

Work item livespec-dev-tooling-mpyqqb, DoD bullet 1. Evidence: livespec-dev-tooling#4720 (diff: .ai/fleet-and-secrets.md only), CI run 43643600106, attempt-1 job 132596436429 (check-per-file-coverage, 2026-11-14 21:36-22:08Z). The item records that the log carried no test name, traceback or short summary. The job log read through the jobs API shows otherwise: a FAILURES section for tests/livespec_dev_tooling/test_incident_observer_reconcile.py::test_a_retry_with_no_landed_effect_starts_exactly_one_revert (AssertionError at line 202: status 'pending', expected 'completed'), a FLAKE-RETRY-WITHHELD block for the same node id (reason: an indeterminable path in a closure module), and a short test summary FAILED line, ending '1 failed, 12546 passed'. The '99 percent' total is that failure's own consequence: the only file below 100 percent is the failing test module, lines 203-204, the two asserts after the failed one. The pytest-cov fail-under ERROR line prints before the FAILURES section and a 1,600-line coverage table separates the failure from the log tail, which is the likely reason the reporter missed it. The behaviour is therefore present but unratified; this finding ratifies it so a regression is caught. DoD bullet 2 (a docs-only pull request passes whenever master passes) is deliberately not proposed: it is a guarantee that no test is flaky, which no check can make; the failure was a load-dependent incident test whose untouched-test retry was withheld, and that belongs to the test root-fix items (livespec-dev-tooling-vm4vcn, livespec-dev-tooling-vzfxlg, livespec-dev-tooling-hzhw6y) and the existing §"Untouched-test retry" rule.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, under ## Enforcement-suite invocation, insert the following immediately AFTER the sentence that reads: "The `just` target that runs the whole test suite with coverage (`check-per-file-coverage`) MUST print the thirty slowest test phases of that run with their durations, so that the run's slow tail is named in every local, sandbox and CI log."

```
The same target MUST keep pytest's failure reporting in that output: when a test of the run fails, the output MUST carry pytest's failure section for that test, with its node id and its assertion or exception text, and a short test summary line naming that node id, in every local, sandbox and CI log. This MUST hold whether or not the run's coverage total is also below its threshold, because a failing test leaves its own later lines unexecuted and so can lower the total by itself. The target MUST NOT pass pytest an option that removes either part, such as `--tb=no`, `-p no:terminal` or a `-r` value without `f`.
```

In `SPECIFICATION/scenarios.md`, add the following new section immediately AFTER `## Scenario: the whole-suite coverage run prints its thirty slowest test phases`:

```
## Scenario: a whole-suite coverage run whose test fails names that test and its assertion

Given a tree on which exactly one test fails on an assertion when `just check-per-file-coverage` runs the suite

And that failure leaves the run's coverage total below 100 percent

When the run completes

Then the run MUST exit non-zero
And its output MUST carry pytest's failure section naming that test's node id and its assertion text
And its short test summary MUST name that test's node id
And the coverage total MUST NOT be the only failure its output names
```

Co-edit in the revise commit (outside the spec target): add an entry for the new scenario heading. The behaviour already holds, so map it to a real integration-tier test that runs the recipe's pytest argv over a fixture tree with one failing test; a spec-first TODO row would need a tier-naming reason, a work_item key and a regenerated tests/heading-coverage-debt.json.
