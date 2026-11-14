---
topic: a-running-detached-gate-cannot
author: claude-opus-5-5:fleet-flaky-tests-seat
created_at: 2026-11-11T14:16:02Z
---

## Proposal: A running detached gate can be stopped by its run id, and reads STOPPED

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a `gate-stop <run-id>` verb and a `STOPPED` terminal state to contracts.md §"Detached gate runner", with two scenarios. Today the runner offers `gate-start`, `gate-wait`, `gate-status` and `gate-list` and no way to stop a run. A caller that has decided a run must not complete has no supported means to prevent it, and the process-group signal an operator first reaches for does not reach the gate. The new verb ends every process attributed to the run, including a hook-run gate client in its own session and a delegated gate's in-cluster Job, before it reports success. The run then reads STOPPED, which is neither a pass nor a refusal. Because the runner is a worktree-pack member materialized in every fleet member, the verb reaches the whole fleet through each member's dev-tooling pin.

### Motivation

Work item livespec-dev-tooling-kjwanx, spec-change tier, granted by legacy-coordinator-agent on 2026-11-11 (~14:08Z). Measured 2026-11-11: the ci-runtime-and-cost seat decided under coordinator-duties §2 (no whole-suite re-run past a flake) to stop its re-run push gate 20261111T134833Z-2372296. It sent SIGINT to the gate child's process group (pgid 2373653) at about 13:5xZ. The gate was not stopped: its record shows exit_code 0 at 14:01:59Z, VERDICT PASSED (84 targets, 0 failed), and output.log ends with branch docs/kueue-cohortname-read pushed to origin at f3a886e9c. So a re-run the fleet rule forbids went through, because the runner gave its caller no way to stop it. The mechanism is the one .ai/independent-host-replay-identity.md records for livespec-dev-tooling-4rliwe: `gate-start` detaches the wrapper with setsid, and lefthook starts each hook command in its OWN session, so a pre-push or pre-commit gate client, and the gate Job it submits, sit outside any process group a caller can signal from the run record. Every fleet member carries the runner: livespec, livespec-orchestrator-beads-fabro, livespec-overseer, livespec-driver-codex, livespec-driver-claude, livespec-driver-pi, livespec-runtime, livespec-console-beads-fabro, livespec-orchestrator-git-jsonl and this repository each have the pack-provisioned `dev-tooling/gate-run.sh` (surveyed on the dev host 2026-11-11).

### Proposed Changes

In SPECIFICATION/contracts.md §"Detached gate runner":

1. In the opening paragraph, the recipe list MUST read `gate-start`, `gate-wait`, `gate-status`, `gate-stop` and `gate-list`.

2. The **Terminal states.** bullet MUST gain one state, placed before the `exit_code` rules: a run whose record carries a `stopped` marker is `STOPPED`, whatever else its record holds. `STOPPED` MUST NOT read as a pass on any surface, and it MUST NOT be reported as a `FAILED` verdict, because the gate did not reach one.

3. A new **Stop.** bullet MUST follow **Stall bound.**:

- **Stop.** `gate-stop <run-id>` stops a `RUNNING` run on request. It MUST write the run's `stopped` marker, carrying the time and the requesting identity, BEFORE it signals anything, so that a run ending while the stop is in progress still reads `STOPPED`. It MUST then end every process attributed to the run under the attribution, SIGTERM-then-grace-then-SIGKILL order, re-verification and unended rules this section's **Stall bound.** applies. That covers the wrapper's own process group and every descendant that entered a new OS session, including a gate client that lefthook, the repository's hook runner, started in its own session. When the run's gate is delegated, `gate-stop` MUST also end the gate's in-cluster Job, through the same path the delegated client uses to cancel its own Job, before it reports. `gate-stop` MUST exit `0` only once no process attributed to the run remains and any delegated Job has ended; the wrapped command therefore cannot complete afterwards, and a wrapped `git push` or `git commit` that had not completed MUST NOT complete. When a process or Job survives, `gate-stop` MUST name each survivor and exit non-zero. A run that is already in a terminal state MUST be left unchanged: `gate-stop` prints its state and exits `1`. An unknown run id exits `64`. `gate-wait` and `gate-status` MUST report a `STOPPED` run with exit `75`, like `DIED_WITHOUT_VERDICT`, and the printed state MUST say `STOPPED`. Signalling a run's recorded `pid` or process group directly is NOT a supported way to stop a run, because a hook-run gate client does not share that group. The shipped runner's operator guidance MUST say so and name `gate-stop`. This bullet is spec-first: the shipped runner has no `gate-stop`, and work item livespec-dev-tooling-kjwanx owns the change.

4. A new **Fleet reach.** sentence MUST be appended to the **Stop.** bullet: the runner and its recipes are worktree-pack members, materialized into every consumer's `dev-tooling/` at that consumer's pinned livespec-dev-tooling version. Every fleet member that installs the pack therefore receives `gate-stop` at its first dev-tooling pin that carries the release, and no per-member change beyond that pin bump is required. A member whose pin predates that release MUST NOT be described as able to stop a gate.

In SPECIFICATION/scenarios.md, two scenarios MUST be added:

```
## Scenario: a stopped push gate ends without pushing and reads STOPPED

Given a run started with `gate-start -- git push origin <branch>` whose pre-push hook runs a gate client in its own session

And the run is RUNNING and `<branch>` has not yet reached the remote

When the operator runs `gate-stop <run-id>`

Then `gate-stop` MUST exit 0 only after no process attributed to the run remains

And the remote MUST NOT receive `<branch>`

And `gate-status <run-id>` MUST print `STOPPED` and exit 75

## Scenario: stopping a delegated gate ends its gate Job

Given a RUNNING run whose gate is delegated to an in-cluster gate Job

When the operator runs `gate-stop <run-id>`

Then the gate Job MUST have ended before `gate-stop` exits 0

And `gate-wait <run-id>` MUST print `STOPPED` and exit 75
```

The revise that accepts this proposal MUST add `tests/heading-coverage.json` rows for both new scenario headings in the same revise commit, per this repository's CLAUDE.md co-edit discipline. A spec-first `"test": "TODO"` row MUST name the integration tier and carry `"work_item": "livespec-dev-tooling-kjwanx"`, and the debt register MUST be regenerated.

## Proposal: The waiter-independence bullet states the waiter's real poll cadence

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Correct one stale sentence in contracts.md §"Detached gate runner" **Waiter independence.**. It says the shipped waiter polls the run's state every five seconds, but the shipped `gate-run.sh` polls every 0.1 seconds (`POLL_INTERVAL_S=0.1`). Five seconds is the return-latency ceiling the **Idle cost.** bullet states, not the cadence.

### Motivation

Deferred by the fleet-flaky-tests seat (handoff 43, item 6) until a dev-tooling revise turn was granted. legacy-coordinator-agent granted this proposal's slot on 2026-11-11, so it rides with the kjwanx proposal in the same section. The stale claim bears on livespec-dev-tooling-oczx3k, a flaky test asserting the idle waiter's return latency (5.6 s measured against a 5.0 s bound): a reader taking the spec's 'every five seconds' at face value would expect a five-second floor on that latency, not a ceiling.

### Proposed Changes

In SPECIFICATION/contracts.md §"Detached gate runner", the **Waiter independence.** bullet's last sentence ("The shipped waiter polls the run's state every five seconds.") MUST be replaced with: "The shipped waiter polls the run's state every 0.1 seconds. The five seconds in **Idle cost.** is a ceiling on how long `gate-wait` MAY take to return after `exit_code` appears, not the poll cadence." No other sentence of the bullet changes, and this finding MUST NOT alter the **Idle cost.** bullet, including its statement of what the shipped runner forks, which this proposal does not re-measure.
