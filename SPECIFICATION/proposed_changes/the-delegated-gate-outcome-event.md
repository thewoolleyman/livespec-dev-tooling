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

Every delegated gate run's outcome event (`livespec.delegated-gate.outcome`) gains two double attributes taken from the cluster's own timestamps: `livespec.gate.queue_wait_seconds`, from the gate Job's creation to its admission by the queue, and `livespec.gate.duration_seconds`, from that admission to the Job's terminal condition. Each attribute is present only once the run reached that point and is never zeroed or guessed. The event stays a point event, and the verdict never depends on the values.

### Motivation

The maintainer approved a lead-time metric and a stage split for the fleet throughput track (one metric: PRs per repository per hour, merged to main and green), plus a dedicated Honeycomb throughput board built by kubernetes-observability. The board's gate-stage panels need how long a delegated gate queued and how long it ran. Today the outcome event is a point event that carries outcome, repository, tree hash, Job name, and the no-verdict cause and step. It records neither time, so the gate stage cannot be charted. The attribute names were agreed with kubernetes-observability on 2026-11-14, and its panels filter on the attribute existing, so they stay empty, not wrong, until this ships. The client deliberately counts its waits in polls rather than reading a wall clock, which is why the values come from cluster-recorded timestamps. Work item livespec-dev-tooling-7g45w6 owns the implementation.

### Proposed Changes

In `contracts.md` §"Delegated pre-push gate", in the **Telemetry** bullet, insert the following sentences directly after the sentence "The event MUST carry the repository's name, the gated tree's hash, and the gate Job's name as separate attributes.":

> The event MUST also carry the gate Job's queue wait and run duration, as the double-valued attributes `livespec.gate.queue_wait_seconds` and `livespec.gate.duration_seconds`, in seconds. The queue wait is the time from the gate Job's creation to its admission by the cluster's queue. The run duration is the time from that admission to the Job's terminal condition. Each value MUST be computed from timestamps the cluster recorded on the gate Job and its admission, never from the gate client's own clock or poll count. An event MUST carry the queue wait once the Job was admitted, and MUST carry the run duration once the Job reached a terminal condition. A run that stopped before its Job was admitted MUST carry neither attribute, and a run that stopped after admission but before a terminal condition MUST NOT carry the run duration. An absent value MUST NOT be replaced by zero or by an estimate. The event remains a point event, and its span timestamps MUST NOT be stretched to represent either duration. A timestamp the client cannot read MUST leave the corresponding attribute absent, and MUST NOT change the run's verdict or exit status.

In `scenarios.md`, add the following two scenarios directly after "## Scenario: a delegated gate verdict is unchanged when its outcome event cannot be delivered":

```
## Scenario: a delegated gate outcome event carries the gate Job's queue wait and run duration

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a pushing host where the pushing user can read the gates kubeconfig

When a git push of a tree that has no green token runs the pre-push gate, and its gate Job is admitted by the cluster's queue and reaches a terminal condition with a green verdict

Then the gate client MUST emit exactly one outcome event whose outcome is `passed`

And that event MUST carry `livespec.gate.queue_wait_seconds`, equal to the seconds between the gate Job's creation and its admission as the cluster recorded them

And that event MUST carry `livespec.gate.duration_seconds`, equal to the seconds between that admission and the Job's terminal condition as the cluster recorded them

## Scenario: a delegated gate run stopped before admission carries no queue wait or run duration

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a pushing host where the pushing user can read the gates kubeconfig

And a git push of a tree that has no green token whose pre-push gate has submitted its gate Job

When the gate client receives SIGTERM while the cluster's queue has not yet admitted that Job

Then the gate client MUST emit exactly one outcome event whose outcome is `no-verdict`

And that event MUST NOT carry `livespec.gate.queue_wait_seconds`

And that event MUST NOT carry `livespec.gate.duration_seconds`
```

At revise time, `tests/heading-coverage.json` MUST gain one row per new scenario heading, each naming work item livespec-dev-tooling-7g45w6 as its owner until the implementation's tests land.
