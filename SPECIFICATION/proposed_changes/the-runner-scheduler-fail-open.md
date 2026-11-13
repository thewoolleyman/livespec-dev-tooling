---
topic: the-runner-scheduler-fail-open
author: claude-opus-5-5 (ci-runtime-and-cost)
created_at: 2026-11-13T04:07:18Z
---

## Proposal: Runner placement also fails open while the runner scheduler's leader-election lease is stale or absent

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

MODIFIES the paragraph "Runner placement fails open while its scheduler is down." under "## Runner-pool node rebuild recipe". The scheduler counts as down on a second trigger: its leader-election lease is absent or was last renewed more than 60 seconds ago, even while its replicas read ready. The existing zero-ready trigger, the 30-second rescue, the alert and the failed-read rule are kept. A failed lease read other than not-found changes nothing. The paragraph states the 60-second bound's basis and the one gap it leaves, a leader that renews while binding nothing. Adds four scenarios: stale lease, absent lease, fresh lease, and failed lease read.

### Motivation

Work item livespec-dev-tooling-hqbbff, ordered by legacy-coordinator-agent on 2026-11-13 in its PASS grade of livespec-dev-tooling#4443. That PR (mtvxde widen) moves every churn-slot runner set onto the committed runner scheduler, so one scheduler now binds all churn-slot runner pods. The ratified fail-open text triggers only on zero ready replicas. kube-scheduler's readiness does not require leadership, so a state where no replica holds the lease while both read Ready strands every churn-slot runner pod, and the reconciler never fires. The coordinator held hqbbff at spec-change tier, verdict partial, target "## Runner-pool node rebuild recipe", linked topic the-runner-scheduler-fail-open, because the staleness trigger is behaviour the ratified text does not state. The bound and its basis were measured: the live lease has leaseDurationSeconds 15 with renewDeadline 10 s and retryPeriod 2 s, and at the 2026-11-13 03:20Z kine checkpoint stall the leader lost its lease at 03:20:00.80Z and the standby acquired it at 03:20:02.14Z (1.3 s), with its first bind 8.1 s later. Four lease durations, 60 s, sits far above a healthy handover and equals the existing readiness grace, so both triggers rescue on one clock.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Runner-pool node rebuild recipe", REPLACE the whole paragraph that begins "**Runner placement fails open while its scheduler is down.** While the scheduler that realizes the rule above has had no ready replica for 60 seconds, a runner pod that names it" with:

**Runner placement fails open while its scheduler is down.** The scheduler that realizes the rule above is down while EITHER it has had no ready replica for 60 seconds, OR its leader-election lease is absent or was last renewed more than 60 seconds ago, even while its replicas read ready. While it is down, a runner pod that names it and is Pending with no node and no scheduling gate MUST, within the next 30 seconds, have its runner re-pointed at the default scheduler and the pod deleted, so the runner controller recreates it under the same runner name naming the default scheduler and a scheduler outage never stalls CI. A runner pod placed this way ignores churn-slot use, and each node's declared churn-slot capacity still limits it through the default scheduler's fit filter. The 60-second lease bound is four durations of the scheduler's 15-second lease: a serving leader renews its lease about every 2 seconds and a standby replica takes the lease over within one lease duration, so a renewal older than the bound means no replica has held the lease through a full handover. The zero-ready state MUST raise an alert. A failed read of the scheduler's state MUST NOT recreate any pod; a failed read of the lease, other than an answer that the lease does not exist, is such a failed read. This rule does not detect a leader that keeps renewing its lease while it binds no pod.

In SPECIFICATION/scenarios.md, insert the following four scenarios immediately after "## Scenario: a failed read of the runner scheduler changes nothing" (before "## Scenario: runner pods select the committed runner scheduler profile and every other pod keeps the default profile"). The existing three fail-open scenarios stay unchanged.

## Scenario: a runner pod stranded behind a stale runner-scheduler lease is handed to the default scheduler

Given the runner scheduler has at least one ready replica
And its leader-election lease was last renewed more than 60 seconds ago
And a runner pod that names it is Pending with no node and no scheduling gate

When the fail-open reconciler next runs

Then the pod's runner MUST be re-pointed at the default scheduler and the pod deleted
And the runner controller MUST recreate the pod under the same runner name, naming the default scheduler

## Scenario: a runner pod stranded behind an absent runner-scheduler lease is handed to the default scheduler

Given the runner scheduler has at least one ready replica
And its leader-election lease does not exist
And a runner pod that names it is Pending with no node and no scheduling gate

When the fail-open reconciler next runs

Then the pod's runner MUST be re-pointed at the default scheduler and the pod deleted

## Scenario: a ready runner scheduler with a freshly renewed lease leaves runner pods alone

Given the runner scheduler has at least one ready replica
And its leader-election lease was last renewed within the last 60 seconds
And a runner pod that names it is Pending with no node and no scheduling gate

When the fail-open reconciler runs

Then that pod MUST NOT be recreated
And its runner MUST still name the runner scheduler

## Scenario: a failed read of the runner-scheduler lease changes nothing

Given the runner scheduler has at least one ready replica
And its leader-election lease cannot be read because the API call failed with an error other than not-found

When the fail-open reconciler runs

Then no runner and no runner pod MUST change
And the run MUST exit non-zero

The revise that accepts this MUST add a tests/heading-coverage.json row for each new scenario heading, owned by livespec-dev-tooling-hqbbff, at the unit tier (the reconciler's fake-kubectl harness in tests/livespec_dev_tooling/test_runner_scheduler_fail_open.py), and register those rows in the debt register.
