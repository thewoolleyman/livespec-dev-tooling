---
topic: the-delegated-gate-outcome-event
author: claude:implement-test-performance
created_at: 2026-11-14T02:19:02Z
---

## Proposal: The delegated gate outcome event carries the gate Job's queue wait and run duration

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Every delegated gate run's outcome event (`livespec.delegated-gate.outcome`) gains two double attributes computed from named API-server timestamps on the gate Job: `livespec.gate.queue_wait_seconds`, from the Job's `metadata.creationTimestamp` to its last admission (`status.startTime`), and `livespec.gate.duration_seconds`, from that admission to the `lastTransitionTime` of its Complete or Failed condition. Each attribute is present once the client observed that point and is never zeroed or guessed. The delegated pre-commit outcome span carries the same two attributes under the same names. The event stays a point event, and the verdict never depends on the values.

### Motivation

The maintainer approved a lead-time metric and a stage split for the fleet throughput track (one metric: PRs per repository per hour, merged to main and green), plus a dedicated Honeycomb throughput board built by kubernetes-observability. The board's gate-stage panels need how long a delegated gate queued and how long it ran. Today the outcome event is a point event that carries outcome, repository, tree hash, Job name, and the no-verdict cause and step. It records neither time, so the gate stage cannot be charted. The attribute names were agreed with kubernetes-observability on 2026-11-14, and its panels filter on the attribute existing, so they stay empty, not wrong, until this ships. The client deliberately counts its waits in polls rather than reading a wall clock, which is why the values come from cluster-recorded timestamps. Work item livespec-dev-tooling-7g45w6 owns the implementation.

### Proposed Changes

In `contracts.md` §"Delegated pre-push gate", in the **Telemetry** bullet, insert the following sentences directly after the sentence "The event MUST carry the repository's name, the gated tree's hash, and the gate Job's name as separate attributes.":

> The event MUST also carry the gate Job's queue wait and run duration, in seconds, as the double-valued attributes `livespec.gate.queue_wait_seconds` and `livespec.gate.duration_seconds`. Both values MUST be computed from timestamps the cluster's API server recorded on the gate Job, never from the gate client's own clock or poll count. Because they are API-server timestamps, the values are comparable across nodes, and they have the one-second resolution of those timestamps. The Job's creation is its `metadata.creationTimestamp`. Its admission is its `status.startTime`, which is set when the Job is no longer suspended, as **Admission wait** defines admission. When the cluster's queue evicts and re-admits the Job, the Job is suspended again and `status.startTime` is reset, so the admission that counts is the LAST one. The Job's terminal condition is the `lastTransitionTime` of its `Complete` or `Failed` condition; `status.completionTime` MUST NOT be used, because it is set only on success. The queue wait is the time from the Job's creation to its admission, so it includes any time the Job ran before an eviction. The run duration is the time from that admission to the terminal condition, so it includes pod scheduling, image pull and container start as well as the gate's own run. `livespec.gate.duration_seconds` is the gate Job's run time on the cluster; it is not `suite_green.duration_seconds`, which §"Suite-green replay leg" **Outcome telemetry** defines for the suite-green replay leg. An event MUST carry the queue wait once the client observed the Job's admission, and MUST carry the run duration once the client observed the Job's terminal condition. A run that stopped before the client observed admission MUST carry neither attribute. A run that stopped after the client observed admission but before it observed a terminal condition, including a run the client interrupted and a run whose poll budget ran out after admission, MUST carry the queue wait and MUST NOT carry the run duration. An absent value MUST NOT be replaced by zero or by an estimate. The event remains a point event, and its span timestamps MUST NOT be stretched to represent either duration. Computing these values MUST NOT change the run's verdict or exit status.

In `contracts.md` §"Delegated pre-commit aggregate", in the **Telemetry** bullet, append:

> The span MUST carry `livespec.gate.queue_wait_seconds` and `livespec.gate.duration_seconds` under the rules §"Delegated pre-push gate" **Telemetry** states for them, with the same names and definitions. It MUST name the pre-commit stage in an attribute of its own, so that a reader can tell it apart from a pre-push outcome in the same dataset. Work item livespec-dev-tooling-cicjhe owns that span.

In `scenarios.md`, add the following three scenarios directly after "## Scenario: a delegated gate verdict is unchanged when its outcome event cannot be delivered":

```
## Scenario: a delegated gate outcome event carries the gate Job's queue wait and run duration

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a pushing host where the pushing user can read the gates kubeconfig

When a git push of a tree that has no green token runs the pre-push gate, and its gate Job is admitted by the cluster's queue and reaches its Complete condition with a green verdict

Then the gate client MUST emit exactly one outcome event whose outcome is `passed`

And that event MUST carry `livespec.gate.queue_wait_seconds`, equal to the seconds from the Job's `metadata.creationTimestamp` to its `status.startTime`

And that event MUST carry `livespec.gate.duration_seconds`, equal to the seconds from the Job's `status.startTime` to the `lastTransitionTime` of its Complete condition

## Scenario: a delegated gate run stopped before admission carries no queue wait or run duration

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a pushing host where the pushing user can read the gates kubeconfig

And a git push of a tree that has no green token whose pre-push gate has submitted its gate Job

When the gate client receives SIGTERM while the cluster's queue has not yet admitted that Job

Then the gate client MUST emit exactly one outcome event whose outcome is `no-verdict`

And that event MUST NOT carry `livespec.gate.queue_wait_seconds`

And that event MUST NOT carry `livespec.gate.duration_seconds`

## Scenario: a delegated gate run stopped after admission carries its queue wait and no run duration

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a pushing host where the pushing user can read the gates kubeconfig

And a git push of a tree that has no green token whose pre-push gate has submitted its gate Job, which the cluster's queue has admitted

When the gate client stops waiting before that Job reaches a terminal condition, because it receives SIGTERM or because its poll budget runs out

Then the gate client MUST emit exactly one outcome event whose outcome is `no-verdict`

And that event MUST carry `livespec.gate.queue_wait_seconds`, equal to the seconds from the Job's `metadata.creationTimestamp` to its `status.startTime`

And that event MUST NOT carry `livespec.gate.duration_seconds`
```

The revise that accepts this proposal MUST, in the same commit, add one row to `tests/heading-coverage.json` for each of the three new `## Scenario:` headings above. Each row is `"test": "TODO"`, with a `reason` that names the integration tier as the tier the owed test runs at and names livespec-dev-tooling-7g45w6 as its owner, and with `"work_item": "livespec-dev-tooling-7g45w6"`. The commit MUST also carry `tests/heading-coverage-debt.json` regenerated by `just generate-heading-coverage-debt-register`. The edit to §"Delegated pre-commit aggregate" adds no heading and needs no row.
