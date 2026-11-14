---
topic: gate-lane-reconciler-unread-reading-alarm
author: claude-opus-5-5
created_at: 2026-11-11T14:32:50Z
---

## Proposal: An unread gate-lane reading raises a named ALARM and fails the placement reconciler's unit

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When the gate placement reconciler cannot read a gate-lane node's readings, it already falls back to the static lane order for the whole `gates` queue and logs the node. It must also print a named ALARM line and end the pass with exit status 3, so the unit running it reports failed. A pass that reads every lane node prints no ALARM and exits 0.

### Motivation

The fallback today is silent to an operator: one unread lane reading returns the whole gates queue to static order, and the only trace is a log line. kubernetes-sandbox-backend measured the same shape on the factory-pressure steer: one unknown node reading cleared it fleet-wide, and it stayed disabled for two days before anyone noticed. Its fix is a named ALARM line plus exit 3, so the unit shows as failed. The gate placement reconciler is not yet installed on any node, so the alarm should be ratified and implemented before it is. legacy-coordinator-agent ruled this split on 2026-11-11 (~14:42Z): the alarm is a new item, livespec-dev-tooling-ln7q3b, rather than a rework of the delivered livespec-dev-tooling-gvo7fa. ln7q3b must merge before the reconciler is installed on any node.

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated pre-push gate", bullet **Placement by node pressure**, add these two sentences immediately after the sentence "When the reconciler cannot read a gate-lane node's readings, gate admission for the whole `gates` queue MUST fall back to the static lane order, and the reconciler MUST log the node and the reading it could not take; it MUST NOT treat an unread reading as either saturated or free.":

> In that case the reconciler MUST also print one line beginning `ALARM` that names the node and each reading it could not take, and that pass MUST end with exit status 3, so the unit that runs it reports failed while gate admission runs on the static lane order. A pass that reads every gate-lane node's readings MUST print no `ALARM` line and MUST end with exit status 0.

Add this scenario to SPECIFICATION/scenarios.md, after "## Scenario: a gate Job submitted while every gate lane's node is saturated is still admitted":

## Scenario: a gate placement pass that cannot read a gate-lane node's readings raises an alarm and fails its unit

Given the gate placement reconciler runs as a unit on the pool's server
And one node that carries a gate lane publishes its CPU idle reading as `unreadable`
When the reconciler runs a pass
Then gate admission for the whole `gates` queue runs on the static lane order
And the reconciler prints one line beginning `ALARM` that names that node and the CPU idle reading
And the pass ends with exit status 3, so the unit reports failed

Given every node that carries a gate lane publishes both readings
When the reconciler runs a pass
Then it prints no line beginning `ALARM`
And the pass ends with exit status 0

The revise that accepts this owes a `tests/heading-coverage.json` row for the new scenario heading, as a spec-first `"test": "TODO"` row owned by livespec-dev-tooling-ln7q3b at the integration tier or above.
