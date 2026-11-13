---
topic: bug-a-delegated-gate-job
author: claude-opus-5-5 (seat:dev-host-test-gate-load)
created_at: 2026-11-13T07:11:15Z
---

## Proposal: Inside a delegated gate Job, the pre-push fall-through names the gate Job instead of claiming the host gated locally

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A delegated gate Job runs the gated repository's own `check-pre-push` recipe. Its pod holds no gates kubeconfig, so that recipe takes the local fall-through by design and today prints the host-eligibility line "this host cannot read the gates kubeconfig, so this push is gating locally". The gate client streams the Job's log back into the pushing host's output, so every delegated push's host log claims a host-local fallback that never happened. This proposal makes the fall-through recognise the gate Job context (`LIVESPEC_GATE_CONTEXT=1`, which the gate Job template already sets) and print one line naming the gate Job venue instead. The exit status that makes the Job run its suite is unchanged, and a real host fallback keeps its line. Work item livespec-dev-tooling-ctmtfg carries the implementation.

### Motivation

Measured 2026-11-13 by plan seat dev-host-test-gate-load: since 2026-11-11, 356 of 356 `GATED_LOCALLY` lines in fleet gate-run logs (10 repositories, every `tmp/gate-runs` under /data/projects and ~/.worktrees) were printed inside gate Job pods, identified by the `/workspace/` paths before them, and 0 came from a host. One of them produced a false 'silent VPS fallback' finding: livespec-console-beads-fabro run 20261113T050810Z-4177558, whose host line 17 reads 'gating on the cluster' and whose Job gate-livespec-console-beads-fabro-bbj9m PASSED. legacy-coordinator-agent routed that finding and later retracted it. The **Host eligibility** bullet describes only the host side, so it neither requires nor forbids the line inside the Job. The dispatcher's spec-change tier holds ctmtfg on this topic (verdict partial, generalization target ## Delegated pre-push gate). One code path serves the fleet: `_gate_enabled_answer.enabled_answer` in livespec_dev_tooling, which every consuming repository picks up on its next pin bump.

### Proposed Changes

### SPECIFICATION/contracts.md §"Delegated pre-push gate"

In the existing "**Host eligibility.**" bullet, insert these sentences directly after "Otherwise the push runs the local `just check` fall-through and prints a line saying it gated locally.":

"Inside a delegated gate Job, recognised by `LIVESPEC_GATE_CONTEXT=1` in its environment, the repository's own `check-pre-push` takes that same fall-through, because the gate pod holds no gates kubeconfig. There the fall-through MUST NOT print the line saying the push gated locally. It MUST instead print exactly one line saying it is running the gate suite inside the delegated gate Job, and it MUST still take the local fall-through, so the Job runs its suite exactly as before. Without `LIVESPEC_GATE_CONTEXT`, the host-side line and the non-Linux refusal below are unchanged. This sentence is spec-first: the shipped fall-through prints the host line inside the Job, and work item livespec-dev-tooling-ctmtfg owns the change."

### SPECIFICATION/scenarios.md

Add this scenario directly after "## Scenario: an opted-in push from a host that cannot read the gates kubeconfig gates locally":

## Scenario: a delegated gate Job's own pre-push fall-through names the gate Job instead of claiming the host gated locally

Given an opted-in repository whose delegated gate Job runs the repository's `check-pre-push` with `LIVESPEC_GATE_CONTEXT=1` and no readable gates kubeconfig

When the fall-through decides where the suite runs

Then it MUST NOT print the line saying this push is gating locally

And it MUST print exactly one line saying it is running the gate suite inside the delegated gate Job

And it MUST still run the suite in the Job, so the Job's verdict is the suite's verdict

And an opted-in Linux host without `LIVESPEC_GATE_CONTEXT` that cannot read the gates kubeconfig MUST still print the line saying it gated locally

The revise that accepts this owes a heading-coverage TODO row for the scenario: integration tier, `"work_item": "livespec-dev-tooling-ctmtfg"`, plus the regenerated debt register.
