---
topic: bug-the-ci-run-telemetry
author: claude-opus-5-5 (seat ci-runtime-and-cost)
created_at: 2026-11-13T23:21:57Z
---

## Proposal: A CI job span is never exported with its end before its start

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Under the same section, require every exporter (the shared module and any interim script a member still runs) to post a ci.job.<name> span whose end is never before its start. A job that GitHub reports with a completion earlier than its start MUST be posted with its end equal to its start, so Honeycomb reads duration_ms 0 rather than a uint64-wrapped value. This is the behaviour livespec-dev-tooling-bt2cnw implements, which its pre-dispatch screen held for this topic.

### Motivation

Measured 2026-11-13 (Honeycomb github-ci, query 3LqgCqKjhLp): 242 ci.job spans over 7 d in 7 repositories carry a uint64-wrapped duration_ms of about 18.4 quintillion ms, because the exporters post a skipped job's span with its end before its start. An unfiltered CI-duration sum therefore reads about 1.24 billion job-hours a week. That is garbage data under the maintainer's 2026-11-13 garbage-data ruling, routed by legacy-coordinator-agent to livespec-dev-tooling-bt2cnw (plan ci-runtime-and-cost). No live spec text states the bound, and r6r3o2's refusal shows the screen holds an exporter behaviour that the spec does not state. Its pre-dispatch screen refused it at 23:21:00Z at the spec-change tier, holding it for the topic bug-the-ci-run-telemetry and judging its behaviour UNSTATED under ## Runner-pool node telemetry. This file is that topic. Its sibling the-ci-run-telemetry-exporter (r6r3o2) is filed in the same pull request.

### Proposed Changes

In non-functional-requirements.md section "Runner-pool node telemetry", insert this paragraph directly after the paragraph beginning **One CI run-telemetry exporter.** (when the-ci-run-telemetry-exporter's **Exporter failures name themselves.** paragraph is also ratified, it goes directly after that paragraph instead):

> **Job spans never end before they start.** Every `ci.job.<name>` span the exporter posts MUST have an end time no earlier than its start time. A job that the GitHub jobs API reports with a completion time earlier than its start time MUST be posted with its end time equal to its start time, so its `duration_ms` reads 0 and never wraps. This holds for every exporter a fleet member runs, including an interim script kept while the member adopts the shared module.

In scenarios.md, add this scenario directly after "## Scenario: a fleet member's CI runs the CI run-telemetry exporter livespec-dev-tooling ships" (after the-ci-run-telemetry-exporter's two scenarios when that topic is also ratified):

## Scenario: a CI job span whose completion precedes its start is exported with zero duration

Given a completed CI run whose jobs include one that the GitHub jobs API reports with a completedAt earlier than its startedAt

When the CI run-telemetry exporter exports that run

Then that job's ci.job.<name> span MUST be posted with an endTimeUnixNano equal to its startTimeUnixNano

And its duration_ms in the Honeycomb github-ci dataset MUST read 0

The revise that ratifies this MUST add a row for the new scenario heading to tests/heading-coverage.json, owned by livespec-dev-tooling-bt2cnw.
