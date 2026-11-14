---
topic: evacuation-needs-an-always-on-node-and-three-wording-fixes
author: claude-homelab-k8s-worker-nodes-vps-seat
created_at: 2026-11-14T05:34:19Z
spec_commitments:
  impl_followups:
    - id_hint: evacuation-refuses-without-always-on-destination
      description: |
        ansible/k3s-window-drain.yml: the evacuation action refuses, before any delete and naming each listener pod, when the pods it would delete include an AutoscalingListener's pod and no other node carrying ci-runner.io/always-on=true is Ready and not cordoned; a failed label read refuses too. Tests for both, and the heading-coverage row of the new scenario maps to a test.
    - id_hint: runner-pin-check-covers-worker-values
      description: |
        assert_values_pins_agree in ci-runner/k3s/phase2/container-hook/runner-image.sh, and the pin-freshness bump, read ci-runner/k3s/phase2/arc/worker/values-*.yaml beside the other two directories, so a worker set that pins a different actions/runner version fails just check naming the files.
---

## Proposal: The evacuation play refuses unless another always-on node can take the listener pods it would delete

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

The planned power-off evacuation play gains a second refusal: when the pods it would delete include an ARC AutoscalingListener's pod, it refuses and changes nothing unless another node carrying `ci-runner.io/always-on=true` is Ready and not cordoned. Today it refuses only when no other node at all is Ready, so it can delete listeners that have nowhere to run and fail only afterwards.

### Motivation

Found by the doctor pass on v215 and ruled by legacy-coordinator-agent on 2026-11-13 (comment of 23:22Z on livespec-dev-tooling-ko26ez) as a follow-up to v215. v215's **Always-on posture** paragraph places every listener pod only on nodes that carry `ci-runner.io/always-on=true`. The evacuation paragraph's destination check is weaker: `ansible/k3s-window-drain.yml` refuses with 'no other node is Ready, so a deleted pod would have nowhere to run' only when NO other node is Ready. When the named node is the last schedulable always-on node and some not-always-on node (a homelab worker, a part-time host) is Ready, the play passes that check, deletes the listener pods, their replacements stay Pending because no node matches their selector, and the play fails its 120-second read-back with the listeners already gone. CI for every affected repository then queues until someone intervenes. The refusal has to come before the delete.

### Proposed Changes

In `non-functional-requirements.md` §"Consent-gated pool-node disruption", paragraph **A planned power-off evacuation moves the recreated pods off a cordoned, Ready node.**, replace the sentence

> When no other node's Ready condition is True, the play MUST refuse and change nothing, because a deleted pod would have nowhere to run.

with

> When no other node's Ready condition is True, the play MUST refuse and change nothing, because a deleted pod would have nowhere to run. When the pods it would delete include a pod an Actions Runner Controller AutoscalingListener owns, the play MUST also refuse and change nothing unless at least one other node carries the label `ci-runner.io/always-on=true`, has its Ready condition True and is not cordoned. That refusal MUST name each such listener pod and MUST say that no other always-on node can take it. It covers the whole play: the play MUST NOT then delete the node's ReplicaSet or StatefulSet pods either. A listener's pod template places it only on a node that carries that label (the **Always-on posture from the profile, and listener placement by it.** paragraph of §"Runner-pool node rebuild recipe"), so on any other node its replacement stays Pending, and a cordoned node takes no new pod. A read of the node labels that fails MUST NOT be taken for an answer in either direction: the play MUST refuse and change nothing.

In `scenarios.md`, directly after `## Scenario: a planned power-off evacuation moves a cordoned node's listener pods and leaves its other pods`, add:

> ## Scenario: a planned power-off evacuation refuses when no other always-on node can take the listener pods
>
> Given a cluster node that is cordoned and Ready
>
> And an ARC listener pod and a ReplicaSet's pod run on that node
>
> And another node is Ready, but no other node that carries `ci-runner.io/always-on=true` is both Ready and not cordoned
>
> When an operator applies the evacuation play with its confirmation naming the evacuation and that node
>
> Then the play MUST refuse and MUST name the listener pod
>
> And the play MUST NOT delete any pod

The revise that accepts this MUST add the new scenario heading's row to `tests/heading-coverage.json` in the same commit. The play change and the test for the new scenario are the implementation follow-up `evacuation-refuses-without-always-on-destination` declared below; until it lands the sentence is spec-first.

## Proposal: The runner version pin rule names the homelab worker scale-set values directory

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

The pin rule's list of scale-set values files gains `ci-runner/k3s/phase2/arc/worker/values-*.yaml`, so the one-version rule, the one-pull-request bump and the `just check` agreement check cover a homelab worker's runner scale set too.

### Motivation

Doctor finding on v215, ruled a follow-up by legacy-coordinator-agent (2026-11-13 23:22Z): add the directory or say why the rule excludes it. Read on master at v215: `ci-runner/k3s/phase2/arc/worker/values-macbook-m4-max-homelab-worker.yaml` pins `ghcr.io/actions/actions-runner:2.338.2@sha256:759a1d94…`, the same image the fleet's sets pin; `converge-ci-stack.sh` step 7 upgrades every worker set beside the fleet's sets; and the file's own header says its jobs run exactly as on the fleet's sets, with the fleet-patched container hook, which is built for one runner version. So nothing excludes it: a bump that skipped it would leave the worker's runners on a superseded version that GitHub stops serving, with a hook built for another version. The file lives in `worker/` only because the fleet's churn-slot and scheduler rules do not apply to it. The committed agreement check, `assert_values_pins_agree` in `ci-runner/k3s/phase2/container-hook/runner-image.sh`, globs `arc/values-*.yaml` only, so today the worker file is outside it.

### Proposed Changes

In `non-functional-requirements.md` §"Runner-pool node rebuild recipe", paragraph **The runner version pin stays ahead of GitHub's cutoff.**, replace

> The scale-set values files are `ci-runner/k3s/phase2/arc/values-*.yaml` and `ci-runner/k3s/arc/values-*.yaml`.

with

> The scale-set values files are `ci-runner/k3s/phase2/arc/values-*.yaml`, `ci-runner/k3s/phase2/arc/worker/values-*.yaml` (a homelab worker's host-unique set) and `ci-runner/k3s/arc/values-*.yaml`.

and replace

> Every values file in those two directories that pins an actions/runner image MUST pin the same version, and a check in `just check` MUST fail when two of them pin different versions.

with

> Every values file in those three directories that pins an actions/runner image MUST pin the same version, and a check in `just check` MUST fail when two of them pin different versions, naming the files.

No other sentence of the paragraph changes: the one pull request that moves 'every values file' then moves the worker's file with the rest. Widening the committed agreement check and the pin-freshness bump to the worker directory is the implementation follow-up `runner-pin-check-covers-worker-values` declared below; until it lands the widened sentences are spec-first.

## Proposal: The Scope sentence of Consent-gated pool-node disruption names every disruption the section governs

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

The section's Scope paragraph is rewritten to list the agent restart, the node hold and the two pod-deleting plays, which v215 and earlier revisions added below it, and to say that the hold and the two plays accept any node registered in the cluster.

### Motivation

Doctor finding on v215, ruled a follow-up by legacy-coordinator-agent (2026-11-13 23:22Z). The Scope paragraph still lists only the reboot, the node-loss drill, the container-termination drill and the sandbox loss drill, and speaks of 'a runner-pool node'. The section now also governs an agent restart, a node hold (cordon and confirmed uncordon) and the evacuation and lost-node plays, and those last three accept a registered Node with no inventory entry. A reader who stops at Scope concludes that a homelab worker's cordon is outside the section. This is a wording repair: it adds no rule the paragraphs below do not already state.

### Proposed Changes

In `non-functional-requirements.md` §"Consent-gated pool-node disruption", replace the **Scope.** paragraph with

> **Scope.** This section covers deliberately disrupting a node of the runner pool's cluster or a workload on it: rebooting the control-plane node; taking an agent node's k3s agent down to exercise node loss; restarting an agent node's k3s agent so that its committed start configuration takes effect; holding a node by a cordon and releasing it by a confirmed uncordon; deleting a named node's recreated pods, before a planned power-off or after the node is lost; deliberately terminating containers on the cluster to exercise termination telemetry; and deliberately deleting one Fabro factory run's factory sandbox pod to exercise the engine's resume of that run onto a re-acquired sandbox. The node hold and the two pod-deleting plays MAY name any node registered in the cluster, including a node that has no inventory entry (a homelab container worker); every other disruption above acts on a pool node named in inventory. Each is a host action, and this section states how this repository performs it. Rebuilding a node from empty storage is governed by §"Runner-pool node rebuild recipe", not by this section.

## Proposal: Cluster controllers telemetry calls a runner scale set's listener an AutoscalingListener, not a Deployment

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

The **Cluster controllers.** paragraph of §"Runner-pool workload and control-plane telemetry" stops listing 'each per-repository listener' among Deployments, and says where a listener's health and placement are read.

### Motivation

Doctor finding on v215, ruled a follow-up by legacy-coordinator-agent (2026-11-13 23:22Z). A runner scale set's listener is an Actions Runner Controller AutoscalingListener object that owns one pod in `arc-systems`; it is not a Deployment and has no desired or available replica count. v215 says so everywhere else (the agent-restart idle check, the pod-deleting plays, the listener placement read-back). The telemetry paragraph is the one place that still calls it a Deployment, so it requires a replica-count series that cannot exist.

### Proposed Changes

In `non-functional-requirements.md` §"Runner-pool workload and control-plane telemetry", replace the **Cluster controllers.** paragraph with

> **Cluster controllers.** Every Deployment the cluster's operation depends on — the ARC controller, the Kueue controller-manager, CoreDNS and the local-path provisioner — MUST have its desired and available replica counts reported. A runner scale set's listener is not among them: it is an Actions Runner Controller AutoscalingListener that owns one pod in the `arc-systems` namespace, and it has no replica count. Its health MUST be readable from that pod's phase and restart count under **Workload state per namespace.** above, and its placement from the committed read-back the **Always-on posture from the profile, and listener placement by it.** paragraph of §"Runner-pool node rebuild recipe" requires.
