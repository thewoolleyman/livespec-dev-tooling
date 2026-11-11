---
topic: factory-sandbox-loss-drill
author: claude-opus-5-5
created_at: 2026-11-11T04:01:31Z
---

## Proposal: A committed factory sandbox loss drill deletes exactly one named run's sandbox pod

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend §"Consent-gated pool-node disruption" with a narrow, separately fenced drill that deletes ONE Fabro factory run's sandbox pod, so the engine's resume of that run onto a re-acquired sandbox can be proven on a live factory through a committed path. Add the matching scenario. The container-termination drill's ban on factory namespaces is left unchanged; the new drill is its own clause with its own fences.

### Motivation

Two orchestrator host-captured proofs need a live run resumed onto a re-acquired sandbox after a host error: livespec-orchestrator-beads-fabro work items bd-ib-dpsiwz (assertion: on fabro-server-candidate :32278 a resumed run finds the Dispatcher-materialized plugin cache and sandbox helpers present before its next stage) and bd-ib-ljw2xg (blocked on exactly this live proof since 2026-11-04). Measured 2026-11-11: gmktec-factory-placement stopped at the Driver's fleet-host mutation guard before a hand `kubectl delete pod` on a factory sandbox pod, which the guard refuses by design (livespec .ai/gitops-deployment-discipline.md rule 2: the remedy is a committed path). The committed pattern exists, ansible/container-termination-drill.yml, but this section requires a container-termination drill to exit before any cluster write when its namespace is `factory`, `factory-mi-homelab` or any existing namespace, so no committed route can produce the loss today. Waiting for a natural host error has no bound and was rejected by legacy-coordinator-agent, who routed this proposal to the fabro-currency plan session (2026-11-11) with these fences: committed playbook applied from vps; confirmation variable naming the k3s server; exactly one pod, identified by a named Fabro run id in the factory namespace; refuse any pod that is not that run's sandbox, and the server and driver pods; delete the pod only; print UTC times. In-flight survey: no spec/* branch or pending proposal touches this section.

### Proposed Changes

In `non-functional-requirements.md` §"Consent-gated pool-node disruption", in the **Scope.** paragraph, after "and deliberately terminating containers on the cluster to exercise termination telemetry", insert: ", and deliberately deleting one Fabro factory run's factory sandbox pod to exercise the engine's resume of that run onto a re-acquired sandbox".

In the same section, insert the following paragraph directly after the paragraph that begins "**A container-termination drill works only in a throwaway namespace.**":

> **A factory sandbox loss drill deletes exactly one named run's sandbox pod.** A playbook that deletes a Fabro factory run's factory sandbox pod, to exercise the engine's resume of that run onto a re-acquired sandbox, MUST act only when a confirmation variable equals the k3s server's inventory name AND a run-id variable names one Fabro run, and MUST change nothing when either is absent or the confirmation names another host. Before any cluster write it MUST resolve, in its configured factory namespace, the factory sandbox pods that the factory's sandbox provider labels with that run's id, and MUST exit non-zero, naming what it found, when it resolves zero pods or more than one, or when the resolved pod is a Fabro server pod, a sandbox provider pod or any other pod that is not a factory sandbox pod. It MUST delete only that one pod, once. It MUST NOT cordon, drain or delete any node, MUST NOT delete any namespace, and MUST NOT create, modify or delete any other object. It MUST print the UTC time of the delete, the pod's name and the run id. The container-termination drill's throwaway-namespace rule does not govern this drill, and this drill MUST NOT be used to terminate containers for termination telemetry.

In `scenarios.md`, add the following scenario directly after `## Scenario: a container-termination drill produces a crash-looping and an OOM-killed container in a throwaway namespace and deletes it`:

~~~markdown
## Scenario: a factory sandbox loss drill deletes exactly one named run's sandbox pod and nothing else

Given the k3s cluster reached from the control node `vps` and a Fabro run whose factory sandbox pod the API server lists in a factory namespace

When an operator applies the factory sandbox loss drill with its confirmation naming the k3s server and that run's id

Then the API server MUST no longer list that pod, and no other object in the cluster MUST have been created, modified or deleted by the drill

And the drill MUST print the UTC time of the delete, the pod's name and the run id

And applying the drill without its confirmation or its run id, or with a run id that resolves to no factory sandbox pod or to more than one, MUST exit before any cluster write
~~~

Because the revise adds a `## ` heading to `scenarios.md`, it co-edits `tests/heading-coverage.json` with an entry for the new scenario heading (its `test` MAY be "TODO" with a non-empty reason until the drill's implementation item binds a test).
