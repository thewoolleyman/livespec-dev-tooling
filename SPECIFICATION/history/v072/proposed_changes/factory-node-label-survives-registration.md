---
topic: factory-node-label-survives-registration
author: claude-opus-5-5:factory-worker-nodes-gitops
created_at: 2026-10-16T17:21:58Z
---

## Proposal: factory posture comes from the profile and survives registration

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Add a clause to §"Runner-pool node rebuild recipe" stating that a pool node's factory label (`ci-runner.io/factory`) is a fact of its committed profile, and that the label MUST be re-established at node registration or by the control-plane boot converge. A playbook apply MUST NOT be the only thing that sets it. Without the clause, the label survives only until the next control-plane reboot.

### Motivation

On 2026-10-16 the first poweredge-xubuntu reboot after the factory label existed (livespec plan factory-worker-nodes-gitops, epic livespec-sqvj7p) brought every node back Ready, but `ci-runner.io/factory=true` returned only on hp-xubuntu. gmktec-xubuntu and poweredge-xubuntu re-registered without it. The control-plane datastore is a tmpfs rebuilt at every boot, so every Node object is recreated at registration. Their label had been set afterwards by `ansible/roles/node_labels`, which reconciles only on a `ci-pool.yml` apply. The kubernetes-sandbox-backend plugin selects factory pods by that label, so until someone ran an apply, factory pods could land only on hp. That broke the plan's requirement that the factory posture survive a control-plane reboot with no hand step. The label was restored with a tagged apply, and the fix is work-item livespec-dev-tooling-izlx4g. No heading in this specification states the label at all, so izlx4g's Definition of Done had no governing clause (freeze-driver ruling R69).

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Runner-pool node rebuild recipe", insert the following paragraph immediately after the paragraph that begins `**One profile per node.**`:

**Factory posture from the profile, surviving registration.** A pool node's factory posture — the `ci-runner.io/factory` node label that the factory's sandbox scheduling selects on — MUST be read from that node's committed profile (its `FACTORY_NODE` value) and MUST NOT be set or removed by hand. The control-plane datastore is rebuilt empty at every control-plane boot, so every node re-registers after a control-plane reboot. The label MUST therefore be re-established at that registration, or by the control-plane boot converge, with no playbook applied and no command run on any host. Once a node is Ready again, it MUST carry `ci-runner.io/factory=true` exactly when its profile declares `FACTORY_NODE=true`. A reconcile that runs only when a playbook is applied MAY also correct the label, but it MUST NOT be the only mechanism that sets it.

## Proposal: scenario: a factory node keeps its factory label across a control-plane reboot

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Add a scenario that states the new clause's behaviour end to end: after a control-plane reboot, every node's factory label matches its committed profile once the node is Ready again, with nothing applied or run by hand after the reboot.

### Motivation

Per the authoring discipline, load-bearing behaviour is stated as a BCP14 clause AND a `## Scenario`. The clause above is behaviour an implementation can get wrong exactly as it was on 2026-10-16: correct after an apply, wrong after the next reboot. A scenario makes the reboot the observable trigger rather than the apply.

### Proposed Changes

In `SPECIFICATION/scenarios.md`, insert the following scenario immediately after `## Scenario: a pool node is rebuilt from bare metal by the recipe and its profile`:

## Scenario: a factory node keeps its factory label across a control-plane reboot

Given every ci_pool node's committed profile declares `FACTORY_NODE`

And every node whose profile declares `FACTORY_NODE=true` carries the `ci-runner.io/factory=true` label

When the control-plane node is rebooted by the committed reboot playbook and every node re-registers against the rebuilt datastore

Then once every node is Ready again, each node whose profile declares `FACTORY_NODE=true` MUST carry `ci-runner.io/factory=true`, and each node whose profile declares `FACTORY_NODE=false` MUST NOT carry it

And that MUST hold with no playbook applied and no command run on any host between the reboot and that observation

The revise that accepts this scenario MUST co-edit `tests/heading-coverage.json` for the new `## Scenario:` heading (a `TODO` entry whose `reason` names the integration tier, pending livespec-dev-tooling-izlx4g's test), and MUST add the matching entry to `tests/heading-coverage-debt.json` that the authoring-time armed tier requires.
