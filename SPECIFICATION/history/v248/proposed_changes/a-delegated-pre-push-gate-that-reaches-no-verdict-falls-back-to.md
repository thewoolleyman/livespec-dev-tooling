---
topic: a-delegated-pre-push-gate-that-reaches-no-verdict-falls-back-to
author: gate-job-resources-seat
created_at: 2026-11-17T19:05:02Z
---

## Proposal: a-delegated-pre-push-gate-that-reaches-no-verdict-falls-back-to-the-local-gate

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Change the delegated pre-push gate's no-verdict outcome from refusing the push to running the local fall-through, and say so in a scenario.

### Motivation

The maintainer ruled on livespec-dev-tooling-6wueag (relayed by throughput-plans-coordinator, 2026-11-17): the delegated gate needs a fallback to run the checks locally when the cluster or the gate is unavailable. Measured on master 02fce7ab7, the pre-commit aggregate and the replay leg already fall back (ratified scenarios), and an unreadable gates kubeconfig already gates locally at push. The one remaining fail-closed point is the **Verdict** bullet, which refuses the push when no verdict arrives. This proposal is the ratification the maintainer's ruling needs before livespec-dev-tooling-6jwz3x changes the code. Other pending proposals touch the same section (gate-job-cpu-limit, bug-a-delegated-gate-client, the-delegated-gate-outcome-event, a-repository-declares-its-gate-queue and others) but none edits the **Verdict** sentence.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Delegated pre-push gate", bullet **Verdict**, replace the sentence

> When no verdict arrives — the API server is unreachable, the credential cannot be refreshed, the gate Job cannot be submitted, or it is lost or times out — the push is refused, never completed.

with

> When no verdict arrives — the API server is unreachable, the credential cannot be refreshed, the gate Job cannot be submitted, or it is lost or times out — the push runs the local `just check` fall-through instead and prints a line saying that it gated locally and why the delegated gate returned no verdict; it is neither refused for the missing verdict nor completed without a gate. A verdict the gate Job did return is never replaced by the fall-through: a red verdict refuses the push, a validation refusal of the committed configuration (**A refusal is not an absent verdict**) refuses the push, and a non-Linux pushing host is refused as **Host eligibility** states. The fall-through's own verdict then decides the push exactly as it does for a host that cannot read the gates kubeconfig.

In `SPECIFICATION/scenarios.md`, add this scenario beside "an opted-in push from a host that cannot read the gates kubeconfig gates locally":

```
## Scenario: a delegated pre-push gate that reaches no verdict falls back to the local gate

Given a repository with `delegated_gate = true`

And a pushing Linux host whose user can read the gates kubeconfig

When the push delegates and the gate client reaches no verdict because the API server is unreachable, the credential cannot be refreshed, the gate Job cannot be submitted, or the gate Job is lost or times out

Then the push MUST run the local `just check` fall-through

And the push MUST print a line saying that it gated locally and why the delegated gate returned no verdict

And the push MUST NOT be refused because the cluster returned no verdict

And a gate Job that returned a red verdict MUST still refuse the push, and MUST NOT be replaced by the local fall-through
```

`tests/heading-coverage.json` takes a spec-first row for the new scenario heading at revise time (`test: TODO`, naming the tier and the owning work item livespec-dev-tooling-6jwz3x). The abandoned-Job deletion in the **Abandoned Job** bullet and the one outcome event per run in **Telemetry** are unchanged: the fall-through starts after the client has reported its no-verdict outcome.
