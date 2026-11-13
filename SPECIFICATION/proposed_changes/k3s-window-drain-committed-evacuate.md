---
topic: k3s-window-drain-committed-evacuate
author: claude-fable-5-2:homelab-k8s-worker-nodes
created_at: 2026-11-12T21:41:47Z
---

## Proposal: State the committed evacuation of a cordoned node and the clearing of a lost node, which delete only recreated pods and are not drills

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds four paragraphs to non-functional-requirements.md §"Consent-gated pool-node disruption". The first states the node hold: a cordon moves no pod, and a hold ends only by an explicit, confirmed uncordon naming the node, never by a timer. The other three state two committed plays that delete pods on a named cluster node: a planned power-off evacuation of a cordoned, Ready node, and the clearing of a node that is already lost. Each is committed, applied from `vps`, consent-gated on a confirmation naming the action and the node, and limited to pods whose controller recreates them. The evacuation has a bounded post-condition: each recreated pod is read back Running on another Ready node, or the play fails naming it. Neither is a drill, so the node-loss drill's rule against deleting pods keeps governing the drill alone, and neither is a rebuild or a posture move, which §"Runner-pool node rebuild recipe" governs. Adds four scenarios to scenarios.md. Work item livespec-dev-tooling-acgcwp owns the implementation.

### Motivation

Measured 2026-11-12 (work item livespec-dev-tooling-acgcwp). The maintainer powered gamingpc-xubuntu off for a RAM upgrade. The node was cordoned at 20:13:52Z and went unreachable at 21:23:26Z. Eight Actions Runner Controller (ARC) listener pods in `arc-systems` were on it: livespec-driver-pi-k3s, livespec-local-ci-k3s, livespec-orchestrator-git-k3s, livespec-orchestrator-k3s, livespec-overseer-k3s, livespec-runtime-k3s, macbook-m4-max-homelab-worker-k3s and poweredge-xubuntu-k3s. At 21:32:24Z all eight read 1/1 Terminating, still bound to the node, with no replacement. The eviction had marked them for deletion, the node's kubelet was off so the delete could not complete, and the ARC controller creates no listener while the old pod of that name exists. Those eight scale sets took no jobs.

No committed route could prevent or repair this. `ansible/k3s-window-drain.yml` had four actions (pause-arc, restore-arc, cordon, uncordon), and none evicts or deletes a pod. A hand force delete is refused by the Driver's fleet-host mutation guard. This section requires every deliberate disruption of a pool node to be a committed, consent-gated playbook, and it stated none that moves a recreated pod off a node or clears one from a dead node.

Not established: how long each scale set's queued jobs waited, and whether a listener deleted by the evacuation on a healthy node is recreated within seconds (no run has been taken).

Ruling and ordering. legacy-coordinator-agent ruled on 2026-11-12 at about 21:35Z (session bf7fce92) that the fix is hand-landed now as a stop-the-line and the specification follows. The implementation adds the actions `evacuate` and `clear-lost` to `ansible/k3s-window-drain.yml` on branch `fix/window-drain-evacuate-clear-lost`. This proposal is the specification that follows; it states the behaviour the item's Definition of Done asserts.

Why these are not drills. The node-loss drill clause says the drill "MUST NOT cordon, drain, evict or delete any pod, because a workload left on the node is what the drill exists to observe." That sentence is about a drill that takes an agent down on purpose to watch what happens. The two plays here do the opposite job: they keep, or return, scale sets in service around a real power-off. The proposed text says so in words, so neither clause can be read as contradicting the other.

How the consent rule applies. The section's rule names "the single host named by an explicit confirmation variable equal to that host's inventory name". These plays act on a cluster node, and a node can be registered in the cluster with no inventory entry (a homelab container worker is one). The proposed text keeps the rule's shape and names the node by its inventory name or, when it has none, by its registered Node name.

One point beyond the item's wording. The item says the lost-node play leaves every DaemonSet pod. The implementation on the branch also leaves every pod in a factory namespace, for both actions, because a factory sandbox pod holds a run that follows the dispatcher's cancel-and-re-dispatch route. The proposed text states that for both plays, so the lost-node clause cannot be read as requiring the delete of a sandbox pod that is marked for deletion.

Grade and fixes. legacy-coordinator-agent graded this proposal PASS-WITH-FIXES on 2026-11-12 (recorded on livespec-dev-tooling-acgcwp, 23:20Z). This text carries its six fixes. (a) The confirmation names both the action and the node; the hand-landed play enforces that with two variables. (b) The evacuation has a bounded post-condition, read back. (c) A graceful delete consults no PodDisruptionBudget, and a deleted pod's emptyDir data is lost and named in the report. (d) Every other pod is left and reported. (e) The cordon action is stated, and a hold ends only by an explicit confirmed uncordon. (f) The lost-node play force-deletes a gate Job's pod that is already marked for deletion. It also cites §"Runner-pool node rebuild recipe" for the scope boundary.

Rulings on the fixes, 2026-11-12 (legacy-coordinator-agent, on livespec-dev-tooling#4404). For (c): the evacuation deletes a ReplicaSet's or StatefulSet's pod whatever volumes it mounts and names the emptyDir loss, because an emptyDir is ephemeral by design and the power-off loses it anyway. For (e): the uncordon takes the same node confirmation the two deleting plays take, because lifting the wrong node's hold puts load back on a node under maintenance; the cordon is the safe direction and keeps its single action confirmation. The lost-node play acts only on a node whose Ready condition is False or Unknown, and refuses a node that reports no Ready condition at all; that is stricter than "not True", and the text below states it.

Second grade, 2026-11-13 (legacy-coordinator-agent, on head 42603c5dd). Three more changes: the guarded reads are stated in the paragraph both plays share; the third scenario no longer asserts that each scale set gets a Running listener after the clearing, because the lost-node play ends after its force deletes and reads nothing back (that outcome is observed on the cluster and is the item's host-captured assertion); and a fourth scenario covers the uncordon's node confirmation.

In-flight survey, 2026-11-12. The pending proposal `the-k3s-agent-restart-play` inserts one paragraph into this same section (after "It restores and verifies.") and one scenario. It is compatible, and this proposal aligns with it: its text inserts at a different point. Its motivation says no committed route moves a listener pod off a node; the evacuation stated here is that route, and the restart play's listener exemption stays correct either way. No open spec pull request and no other pending proposal changes this section.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "Consent-gated pool-node disruption", insert the following four paragraphs at the end of the section, after the paragraph that begins "**A factory sandbox loss drill deletes exactly one named run's sandbox pod.**". No heading is added, removed or renamed in that file, and no existing sentence of the section is changed.

**A node hold is a cordon, and it ends only by a confirmed uncordon.** The committed cordon action MUST mark the named node unschedulable and MUST NOT evict, drain or delete any pod: pods already on the node keep running, and new pods land elsewhere. A cordon of a node that is already unschedulable MUST change nothing and MUST say so. A held node MUST be made schedulable again only by the committed uncordon action, applied with an explicit confirmation that names the uncordon action and a second explicit confirmation that names the node; when the node confirmation is absent or names another node, the uncordon MUST change nothing and MUST say so. The cordon action needs only the confirmation naming the action, because a cordon of the wrong node moves no pod and puts no load anywhere. A hold MUST NOT be lifted by any other play, or by a timer, a schedule or a deadline: the end of a hold is the word of whoever holds the node, never the passing of time. The two plays below MUST NOT cordon or uncordon a node.

**Two plays delete a named node's recreated pods, and neither is a drill.** A playbook that deletes pods on a cluster node so that a planned power-off does not strand them, or so that pods stranded on a lost node are cleared, is a disruption this section covers. It MUST be committed and applied from the control node `vps` with `just ansible-apply`, and such a pod MUST NOT be deleted for that purpose by a command run by hand. It MUST act only when an explicit confirmation names the action and the node. It MUST change nothing when the confirmation is absent, names another action, or names another node. The node MAY be any node registered in the cluster, not one fixed host: it is named by its inventory name, or by its registered Node name when it has no inventory entry, and a name that is neither MUST be refused with nothing changed. These plays are not drills, and they are not a rebuild or a posture move: §"Runner-pool node rebuild recipe" governs taking a node from empty storage to a pool member and moving it between CI-facilities postures, and these plays change no profile, no storage and no node registration. The node-loss drill's sentence "It MUST NOT cordon, drain, evict or delete any pod" governs the node-loss drill only, and this paragraph and the two below govern these plays only. In both plays a pod is **recreated elsewhere** when its controller owner is an Actions Runner Controller AutoscalingListener, a ReplicaSet or a StatefulSet. Both plays MUST leave in place every pod a DaemonSet owns and every pod in a factory namespace (`factory`, `factory-mi-homelab`), because a DaemonSet's pod belongs to its node and a factory sandbox pod holds a run that follows the dispatcher's cancel-and-re-dispatch route. Every other pod on the node MUST be left and reported, except where the lost-node paragraph below says otherwise: that covers an Actions Runner Controller EphemeralRunner's pod, which is a CI job, and a pod whose controller is of any kind not named above. Each play MUST report every pod it deleted and every pod it left on the node, with the reason it was left. A read of the cluster that fails MUST NOT be taken for an empty answer. When a read fails before a play has deleted anything, the play MUST refuse and change nothing. When a read fails after its deletes, the play MUST fail and MUST say that its post-condition is not established.

**A planned power-off evacuation moves the recreated pods off a cordoned, Ready node.** The evacuation play, for a named node that is cordoned and whose Ready condition is True, MUST delete gracefully each pod on that node that is recreated elsewhere. It MUST NOT delete a DaemonSet's pod, a Job's pod, a pod with no controller owner, a pod whose controller is of any other kind, or a factory sandbox pod. The delete is a delete and not an eviction, so it consults no PodDisruptionBudget; that is deliberate, because the power-off takes those pods whatever a budget says. A ReplicaSet's or StatefulSet's pod MUST be deleted whatever volumes it mounts. The contents of an `emptyDir` volume are lost with the pod, and the play's report MUST name each deleted pod that mounts one, in a check run too. The play has a bounded post-condition, read back from the API server: within a stated number of seconds of the deletes (120 by default), no pod it deleted MUST still be bound to the node, and each controller it deleted a pod from MUST have that many more pods in phase Running on another node whose Ready condition is True than it had before the play. When the bound passes first, the play MUST fail and MUST name each pod still bound and each controller without its replacement, so that it never reports the node safe to power off early. When no other node's Ready condition is True, the play MUST refuse and change nothing, because a deleted pod would have nowhere to run. When the named node is not cordoned, or its Ready condition is not True, the play MUST change nothing and MUST report which of the two it found: an uncordoned node would take the recreated pods straight back, and a node that is not Ready has no kubelet to complete a graceful delete.

**Clearing a lost node force-deletes the pods stranded on it, and refuses a Ready node.** The lost-node play, for a named node whose Ready condition is False or Unknown, MUST force-delete each pod bound to that node that is already marked for deletion or that is recreated elsewhere. A pod marked for deletion is cleared whatever owns it, so the play MUST force-delete a Kueue gate Job's pod and an unowned CI runner pod once the API server has marked it for deletion: that work was lost with the node, and its client reads the failure. A Job's pod or an unowned pod that is not yet marked MUST be left and reported. It MUST NOT delete a DaemonSet's pod or a pod in a factory namespace. When the named node's Ready condition is True, or the node reports no Ready condition, the play MUST refuse, change nothing and report why: a force delete on a node with a live kubelet can leave the pod's containers running.

In `SPECIFICATION/scenarios.md`, insert the following four scenarios immediately after the scenario "a factory sandbox loss drill deletes exactly one named run's sandbox pod and nothing else".

## Scenario: a planned power-off evacuation moves a cordoned node's listener pods and leaves its other pods

Given a cluster node that is cordoned and Ready

And an ARC listener pod, a DaemonSet's pod, a Job's pod and a factory sandbox pod run on that node

When an operator applies the evacuation play with its confirmation naming the evacuation and that node

Then the play MUST delete the listener pod gracefully

And the play MUST NOT delete the DaemonSet's pod, the Job's pod or the factory sandbox pod

And the play MUST report the listener pod as deleted and each of the other pods as left

And the play MUST succeed only after it reads that scale set's listener pod Running on another Ready node, and MUST otherwise fail naming the listener

## Scenario: clearing a lost node is refused for a node that reads Ready

Given a cluster node whose Ready condition is True

And an ARC listener pod runs on that node

When an operator applies the lost-node play with its confirmation naming the clearing and that node

Then the play MUST refuse and MUST report that the node reads Ready

And the play MUST NOT delete any pod

## Scenario: clearing a lost node force-deletes its stuck listener pods and reports each pod it cleared

Given a cluster node whose Ready condition is False or Unknown

And ARC listener pods bound to that node are marked for deletion and still listed by the API server

And a gate Job's pod bound to that node is marked for deletion, and another gate Job's pod bound to it is not

And a DaemonSet's pod is bound to that node

When an operator applies the lost-node play with its confirmation naming the clearing and that node

Then the play MUST force-delete each of those listener pods and the marked gate Job's pod

And the play MUST NOT delete the DaemonSet's pod or the gate Job's pod that is not marked

And the play MUST report each pod it cleared and each pod it left

## Scenario: an uncordon whose node confirmation is absent or names another node changes nothing

Given a cluster node that is cordoned

When an operator applies the uncordon action with its confirmation naming the uncordon, and its node confirmation absent or naming another node

Then the play MUST NOT uncordon any node

And the play MUST say that the node confirmation is absent or names another node, and that nothing was changed

And a cordon of a schedulable node, applied with only its confirmation naming the cordon, MUST mark that node unschedulable

**Co-edit owed at revise.** This proposal adds four `## ` headings to `scenarios.md` and none to `non-functional-requirements.md`. The revise that accepts it MUST add one `tests/heading-coverage.json` entry per new scenario heading in the same commit. A spec-first `"test": "TODO"` row MUST carry a `reason` that names the tier the owed test runs at and the owning work item, and a `work_item` key naming that open item (livespec-dev-tooling-acgcwp while it is open); the revise MUST then run `just generate-heading-coverage-debt-register` and stage `tests/heading-coverage-debt.json`.
