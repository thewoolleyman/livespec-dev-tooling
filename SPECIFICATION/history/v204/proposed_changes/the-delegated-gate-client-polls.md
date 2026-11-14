---
topic: the-delegated-gate-client-polls
author: claude-opus-5-5
created_at: 2026-11-12T05:35:20Z
---

## Proposal: The delegated gate client's terminal-state wait blocks on a bounded watch, bounds every kubectl call and renews its progress stamp

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a Delegated pre-push gate bullet, Terminal-state wait: the client blocks on a bounded watch, starts no process per poll interval and at most one kubectl per watch window of at least 240 s (apart from re-arms), reports the verdict within 10 s, bounds every kubectl call on both waits under the runner's stall window (a timed-out call is transient; a spent budget ends no-verdict naming it), and renews the progress stamp at least every 60 s in-process. Add two scenarios: a Job outliving the stall window ends with its own verdict, and a hung kubectl request is timed out with the wait still ending.

### Motivation

livespec-dev-tooling-ie7fas (a child of plan dev-host-test-gate-load) replaces the delegated gate client's 10-second `kubectl get` poll. Its first delivery, livespec-dev-tooling#4177, was reverted by livespec-dev-tooling#4225 (085a0983b) because its single long watch never renewed the progress stamp, so gate-run.sh's 900 s stall bound ended healthy gates whose Job ran past 15 min (push gate 20261111T234256Z-3116833, about 23:58Z on 2026-11-11). Separately, a `kubectl get` with no request timeout froze three gates in the same second (19:40:59Z on 2026-11-11). Measured before the change: 18 gate runs spawned 420 `kubectl` processes in 600 s on the dev host (2026-11-11 00:15:45-00:25:46Z). At the 0.320.0 wall (2026-11-12T05:32:51Z, spec v200) the tier judgement read the re-land as spec-change, verdict partial: §"Delegated pre-push gate" **Admission wait** and §"Detached gate runner" **Stall bound** do not state that the client blocks on a watch, renews the stamp, bounds hung requests, or starts no process per poll, and **Idle cost** covers only the runner and `gate-wait`. It named this section and linked this topic. This proposal ratifies the client's terminal-state wait exactly as ie7fas's Definition of Done states it, which already passed the launch preflight (gate 20261112T033205Z-2435575).

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Delegated pre-push gate", insert this bullet directly after the "**Admission wait.**" bullet:

- **Terminal-state wait.** After admission, the gate client waits for its gate Job's Complete or Failed condition by blocking on a bounded watch of the Job, not by polling it. While the Job stays admitted and running, the client MUST start no new process per poll interval, neither `kubectl` nor the `with-gates-kubeconfig` wrapper nor any helper the wrapper runs, and apart from a re-arm after a failed or timed-out request its wait MUST start at most one `kubectl` process per watch window of at least 240 seconds. The client MUST report the Job's verdict within ten seconds of the Job reaching its Complete or Failed condition. Every `kubectl` call the client makes on its admission wait and on this wait MUST carry a request bound shorter than the detached gate runner's stall window (§"Detached gate runner" **Stall bound**). A call that hits its bound is a transient failure: the client re-arms within its poll budget, and when the budget runs out it ends with a no-verdict state naming the timed-out call, never a pass. Throughout both waits the client MUST renew the run's progress stamp (`LIVESPEC_GATE_RUN_PROGRESS_STAMP`) at least once every 60 seconds, from its own process and without starting a process, so a healthy Job that outlives the stall window is never ended by the runner. The Admission wait rules above, including that suspended time does not count toward the poll budget, are unchanged.

In SPECIFICATION/scenarios.md, add these two scenarios directly after "## Scenario: an opted-in push from a host that cannot read the gates kubeconfig gates locally" (each heading preceded and followed by a blank line, matching the surrounding scenarios):

## Scenario: a delegated gate Job that runs longer than the stall window still ends with its own verdict

Given a delegated gate run started through `gate-run.sh`, whose gate Job stays admitted and running for longer than the runner's stall window

When the Job reaches its Complete condition

Then the gate client MUST have renewed the run's progress stamp at least once every 60 seconds throughout the wait

And it MUST have started at most one `kubectl` process per watch window of at least 240 seconds, apart from re-arms after a failed or timed-out request

And the run MUST record the Job's own verdict, never the runner's stall-bound `FAILED` verdict or a `DIED_WITHOUT_VERDICT` state

## Scenario: a hung kubectl request on a delegated gate wait is timed out and the wait still ends

Given a delegated gate run whose gate client makes a `kubectl` request, on its admission wait or its terminal-state wait, that never returns

When the request reaches its bound

Then the client MUST end that request before the runner's stall window elapses

And it MUST keep renewing the run's progress stamp

And it MUST reach the Job's verdict, or a no-verdict state naming the timed-out call, within its overall wait deadline

The revise that accepts this MUST add a `tests/heading-coverage.json` row for each new scenario in the same commit, as a spec-first `"test": "TODO"` row at the integration tier owned by `"work_item": "livespec-dev-tooling-ie7fas"`, and regenerate the heading-coverage debt register.
