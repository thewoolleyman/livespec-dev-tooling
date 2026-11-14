---
topic: the-ci-run-telemetry-exporter
author: claude-opus-5-5 (seat ci-runtime-and-cost)
created_at: 2026-11-13T23:21:56Z
---

## Proposal: The CI run-telemetry exporter names the failure that stopped an export and degrades an unreadable coverage reuse outcome to unobserved

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add an exporter failure paragraph under non-functional-requirements.md section "Runner-pool node telemetry". Every path that ends an export with a failure MUST write one stderr line naming that path and its cause: a gh read of the run or its jobs that exited non-zero, a non-200 POST status, or a non-zero rejectedSpans count. An unreadable check-coverage reuse outcome MUST NOT fail the export. The exporter reads the job log within a bound, and if no valid record arrives it posts the spans with ci.coverage_reuse.outcome set to unobserved and names why on stderr. Two scenarios state this. This is the behaviour livespec-dev-tooling-r6r3o2 implements.

### Motivation

On 2026-11-13, livespec-dev-tooling#4514 (ool7pj, 71220a770, 13:56Z) switched livespec-dev-tooling's CI to the Python exporter module. export-telemetry then failed on every master run until incident livespec-dev-tooling-ii557b reverted it (3324c2392); the failed runs include 43438119082, 43443559259, 43447438661, 43449972390, 43452777337, 43460830437 and 43463209699. Every failure path in livespec_dev_tooling/ci_run_telemetry.py main() returned 1 with NO output, so the job log said only "CI telemetry export to Honeycomb FAILED (exporter exit status 1)", while the bash exporter it replaced printed HTTP=, rejected= and trace=. The leading hypothesis is a log-availability race: the check-coverage job log is read about 7 s after the job completes, while the run is still in progress. An unreadable reuse outcome therefore failed the whole export, so the run's spans never reached Honeycomb: the silent-fallback shape the plan's assertion 6 forbids. livespec-dev-tooling-r6r3o2 (plan ci-runtime-and-cost, epic livespec-dev-tooling-ib3oe3) carries the fix. Its pre-dispatch screen refused it at 23:14:55Z at the spec-change tier, judging its asked-for behaviour UNSTATED and naming ## Runner-pool node telemetry as the heading to generalize. legacy-coordinator-agent checked origin/master, found no live text stating it, and refused a clause release. This proposal states it. It does not change whether a failed export fails the CI run: that question is the maintainer's and is carried by livespec-dev-tooling-jgkhr5. An export that fails still exits non-zero, as today's exporter does.

### Proposed Changes

In non-functional-requirements.md section "Runner-pool node telemetry", insert this paragraph directly after the paragraph beginning **One CI run-telemetry exporter.**:

> **Exporter failures name themselves.** Every path on which the CI run-telemetry exporter ends an export with a non-zero exit MUST first write one line to stderr naming that path and its cause. When the gh read of the run or of its jobs exits non-zero, the line MUST name that read and its exit status. When Honeycomb answers the POST with a status other than 200, the line MUST name that status. When Honeycomb's receipt reports a rejectedSpans count other than 0, the line MUST name that count. The exporter MUST NOT exit non-zero with no stderr output. A check-coverage reuse outcome the exporter cannot read MUST NOT fail the export. The exporter MUST retry a read of the check-coverage job log that yields no valid `LIVESPEC_COVERAGE_REUSE_OUTCOME` record until a read yields one or a bounded total time elapses, and MUST use the first valid record any read yields. When no read within the bound yields one, the exporter MUST still post the run's `ci.run` span and every `ci.job.<name>` span, with the check-coverage job's span carrying `ci.coverage_reuse.outcome` set to `unobserved`. It MUST then write one stderr line naming the job id, the number of log reads it made and the last read's failure. An `unobserved` outcome is a recorded fact about the export, never a coverage verdict, and it MUST NOT be read as reuse or as a full run.

In scenarios.md, add these two scenarios directly after "## Scenario: a fleet member's CI runs the CI run-telemetry exporter livespec-dev-tooling ships":

## Scenario: the CI run-telemetry exporter names the failure that stopped an export

Given a completed CI run of a fleet member

When the exporter's gh read of that run's jobs exits with status 1

Then the exporter MUST write one stderr line naming that read and its exit status 1

And it MUST exit non-zero

And when instead Honeycomb answers the POST with status 403, the exporter MUST write one stderr line naming status 403 and MUST exit non-zero

And when instead Honeycomb's receipt reports 2 rejected spans, the exporter MUST write one stderr line naming the count 2 and MUST exit non-zero

## Scenario: an unreadable check-coverage reuse outcome is exported as unobserved

Given a completed CI run whose check-coverage job log yields no valid LIVESPEC_COVERAGE_REUSE_OUTCOME record on any read within the exporter's bound

When the exporter exports that run

Then it MUST post the run's ci.run span and every ci.job.<name> span

And the check-coverage job's span MUST carry ci.coverage_reuse.outcome set to unobserved

And the exporter MUST write one stderr line naming the job id, the number of log reads it made and the last read's failure

And when a later read within the bound yields a valid record after an earlier read yielded none, the span MUST carry that record's outcome instead

The revise that ratifies this MUST add rows for both new scenario headings to tests/heading-coverage.json, owned by livespec-dev-tooling-r6r3o2, and regenerate the debt register in the revise commit.
