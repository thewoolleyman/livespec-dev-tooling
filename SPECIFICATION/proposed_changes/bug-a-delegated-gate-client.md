---
topic: bug-a-delegated-gate-client
author: claude-opus-5-5
created_at: 2026-11-13T01:33:22Z
---

## Proposal: A delegated gate client saves an abandoned gate Job's container logs and process tree before it deletes the Job

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Before the delegated gate client deletes a gate Job that reached no terminal condition, it saves an abandoned-job capture on the pushing host. The capture holds the last 200 log lines of every container of the Job's pod, plus the gate container's process tree as it stood when the client gave up waiting. The no-verdict refusal names the capture's path. A failure to read the logs or the process tree is recorded in the capture and never stops or delays the delete. Work item livespec-dev-tooling-yrjatv carries the implementation.

### Motivation

The **Abandoned Job** bullet makes the client delete a Job it stopped waiting on, and nothing records what the Job was doing first. Deleting the Job also removes the pod's logs from the node, so a hang can be classed but never located. Measured case: livespec-dev-tooling-ddy5xu, a gate Job hang on gamingpc-xubuntu. The client deleted gate-livespec-orchestrator-beads-fabro-9p9pc at 18:13:38Z, and the node's /var/log/pods then held nothing for it. The earlier gate-livespec-dev-tooling-5mxn4 was lost the same way. The gates credential (system:serviceaccount:gates:gate-submitter) can read pod logs but cannot exec into pods, list events or create configmaps, as measured 2026-11-11. So the log tail is readable directly, and the process tree has to reach the client through the gate container's own log output. One code path serves the fleet: `_delete_abandoned_gate_job` in livespec_dev_tooling/gate_remote_client.py, with three call sites (the no-terminal timeout, the interrupted-wait cleanup and the admission-bound path). Every consuming repository picks the fix up on its next pin bump. legacy-coordinator-agent routed the spec-tier orphan livespec-dev-tooling-yrjatv to plan dev-host-test-gate-load (epic livespec-dev-tooling-6vuiwe) with this exact topic slug.

### Proposed Changes

### SPECIFICATION/contracts.md §"Delegated pre-push gate"

Insert this new bullet directly after the existing "**Abandoned Job.**" bullet:

- **Abandoned-job capture.** Before the gate client deletes a gate Job under **Abandoned Job**, it MUST write an abandoned-job capture file on the pushing host. When the client serves a detached gate run, the file lives in that run's directory (§"Detached gate runner" **Run record**). Otherwise it lives in a directory named for the Job under the primary checkout's `tmp/gate-runs/` store. The capture MUST hold a header line with the Job name and the UTC time it was taken, then the last 200 log lines of every container of the Job's pod, each block headed by its container name. It MUST also hold the gate container's process tree as it stood when the client gave up waiting: each process's pid, parent pid, elapsed time in whole seconds and full command line, in parent-before-child order. Because the gates credential grants no exec into a gate pod, the gate container MUST make that process tree readable through its own log output, and how it does so belongs to the implementation. The no-verdict refusal the client prints for that Job MUST name the capture's path. When the client cannot read a container's logs or the process tree, it MUST write the reason into the capture in place of the missing part, and it MUST still delete the Job within the bounds **Abandoned Job** sets, so a failed capture never delays or prevents the delete. The capture MUST NOT turn the absent verdict into a verdict. This bullet binds every delegation that **Abandoned Job** binds. This bullet is spec-first: the shipped client deletes the Job without saving anything, and work item livespec-dev-tooling-yrjatv owns the change.

### SPECIFICATION/scenarios.md

Add this scenario directly after "## Scenario: a gate client that stops waiting on an admitted gate Job deletes it":

## Scenario: a gate client saves an abandoned gate Job's container logs and process tree before it deletes the Job

Given a delegated gate whose admitted gate Job reaches no terminal condition before the client stops waiting

When the client abandons the Job

Then before the delete it MUST write an abandoned-job capture on the pushing host holding the last 200 log lines of every container of the Job's pod and the gate container's process tree as it stood when the client gave up

And the capture MUST still hold those lines after the Job and its pod are gone

And the client's no-verdict refusal MUST name the capture's path

And when a container's logs cannot be read, the capture MUST record why, and the Job MUST still be deleted

And the outcome MUST NOT be a pass

### Revise co-edit (outside the spec target)

The revise commit that accepts this proposal MUST add a `tests/heading-coverage.json` row for the new scenario heading: `"test": "TODO"`, a `reason` naming the integration tier as the tier the owed test runs at and naming livespec-dev-tooling-yrjatv as its owner, and `"work_item": "livespec-dev-tooling-yrjatv"`. It MUST also stage the regenerated `tests/heading-coverage-debt.json` from `just generate-heading-coverage-debt-register`. The new contracts bullet adds no `## ` heading, so it owes no other row.
