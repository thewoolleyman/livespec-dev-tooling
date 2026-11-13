---
topic: arc-listener-pods-run-only
author: claude-fable-5-2:homelab-k8s-worker-nodes
created_at: 2026-11-13T00:25:00Z
---

## Proposal: State that ARC listener pods run only on always-on nodes, a posture each node's profile declares

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds one paragraph to non-functional-requirements.md §"Runner-pool node rebuild recipe", after the paragraph "**Factory posture from the profile, surviving registration.**", and adds the always-on posture to the list of node-specific values in "**One profile per node.**". The new paragraph states that a pool node's always-on posture is read from its committed profile, is carried by one node label that survives a control-plane boot, and is the only thing an Actions Runner Controller (ARC) listener pod is placed by, for every runner scale set. It also requires a committed read-back of listener placement. Adds two scenarios to scenarios.md. Work item livespec-dev-tooling-crvvxt owns the implementation.

### Motivation

Measured 2026-11-12 (work items livespec-dev-tooling-acgcwp and livespec-dev-tooling-crvvxt). gamingpc-xubuntu was powered off from 21:23:26Z to 22:13:24Z for a RAM upgrade. Eight ARC AutoscalingListener pods were on it. They sat Terminating with no replacement from about 21:28Z to 22:13:30Z. A scale set with no listener takes no jobs, and its idle runners kept holding Kueue cohort quota, so every queue in the cohort lost slots. livespec-overseer's master run waited 88 minutes.

Nothing committed kept a listener off that node. Only one values file carried a `listenerTemplate`, and it selected by CPU architecture alone. At 2026-11-12 23:35Z every listener was on hp-xubuntu by the scheduler's choice, not by a rule.

The companion proposal `k3s-window-drain-committed-evacuate` states the plays that move a listener off a node before a planned power-off and clear one after a loss. Those repair an exposure. This proposal removes it: a listener is never placed on a node that is powered down at will, so a planned power-off of such a node strands none.

Ruling and ordering. legacy-coordinator-agent ruled on 2026-11-12 at about 23:50Z that this holds for every runner scale set, and at about 23:58Z that the implementation is hand-landed because it changes values files the CI-stack converge applies. The implementation is on branch `fix/crvvxt-listeners-on-always-on-nodes`. This proposal is the specification that follows; it states the behaviour the item's Definition of Done asserts. The dispatcher's launch screen classified the item as a specification change with this topic (its record of 2026-11-12T23:53Z on the item).

Why the profile. "**One profile per node.**" already requires every node-specific value to be read from the node's committed profile, and "**Factory posture from the profile, surviving registration.**" already states one posture label that way. Whether a node is always on is a fact about the node of the same kind, so it takes the same shape: a profile value, one label, and the same survival rule.

Why the default is not-always-on. A node whose profile says nothing must never be chosen for a listener. A homelab container worker has no profile at all, so the default is also what keeps a listener off it.

Not established: whether the ARC chart version in use re-creates a running listener pod when its `listenerTemplate` changes, and how long a listener takes to appear on another node after one is deleted. Neither has been measured.

Grade, 2026-11-13. legacy-coordinator-agent graded this proposal PASS-WITH-FIXES on head 5baa55a4b. This text carries its fixes: the ordering rule binds every procedure that installs or upgrades a scale set and not the boot converge alone; the boot stop's scope is stated (the scale sets only); the scenarios' tiers are named in the co-edit note; and the read-back's exit statuses 1 and 2 are named.

Second grade, 2026-11-13. legacy-coordinator-agent graded head 74f610f7f PASS-WITH-FIXES. This text carries its fixes. The ordering sentence now says what the routes do: the boot converge re-asserts the label from the profiles before it installs a scale set, and every install route reads the labelled nodes and refuses; no playbook installs a scale set, so "a playbook apply" is gone, and the install run by hand refuses and does not label. Two sentences were kept because livespec-dev-tooling#4414 now makes them true: the converge's final failure names the scale sets it did not install, and the boot reconcile removes the label from a labelled node that has no profile. The co-edit note names one test. The in-flight survey names three more pending proposals.

In-flight survey, 2026-11-13. The pending proposal `k3s-window-drain-committed-evacuate` changes §"Consent-gated pool-node disruption" and not this section; it is compatible, and the two do not touch the same paragraph. Read on master at 6d6969845, three more pending proposals touch the same section or the same scenario anchor, and each is compatible:

- `factory-budget-admission-counts-memory` inserts three scenarios into `scenarios.md` directly after "a factory node keeps its factory label across a control-plane reboot", which is this proposal's anchor too. The order of the result is fixed whichever is revised first: the anchor scenario, that proposal's three scenarios, then this proposal's two, then the node-loss drill scenario. If this proposal is revised first, its two scenarios go directly after the anchor and that proposal's three are later inserted between the anchor and them, as its own text says. If that proposal is revised first, these two go after its third scenario. Its normative text is a new section, "Factory budget admission", and changes no paragraph this proposal changes.
- `delete-the-dead-phase-1` adds a paragraph to the same section, "Runner-pool node rebuild recipe", after "**One procedure, staged.**", and appends one scenario at the end of `scenarios.md`. It changes no paragraph this proposal changes. It names `ci-runner/k3s/install-arc.sh`, the install run by hand, as a superseded artifact that work item livespec-dev-tooling-y4umcc deletes (livespec-dev-tooling#4229). This proposal's rule binds every install route and names none of them by file, so it holds before and after that deletion. Whichever of livespec-dev-tooling#4229 and livespec-dev-tooling#4414 merges second drops the test of that script's refusal.
- `the-arc-runner-version-pin` appends one sentence to the paragraph "**The runner version pin stays ahead of GitHub's cutoff.**" of the same section and appends one scenario at the end of `scenarios.md`. It requires every AutoscalingRunnerSet to have a listener after a runner version bump converges; this proposal says where that listener may run. The two do not touch the same paragraph.

No other pending proposal changes "**One profile per node.**" or the factory-posture paragraph.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "Runner-pool node rebuild recipe", paragraph "**One profile per node.**", replace the words "the node's admission capacity, and its factory posture" with "the node's admission capacity, its factory posture, and its always-on posture". No other word of that paragraph is changed.

In the same section, insert the following paragraph immediately after the paragraph that begins "**Factory posture from the profile, surviving registration.**". No heading is added, removed or renamed in that file.

**Always-on posture from the profile, and listener placement by it.** A pool node's profile MUST declare whether the node is always on in its `ALWAYS_ON_NODE` key, as `true` or `false`. The profile parser MUST refuse any other value, naming the key, and a profile that does not carry the key MUST be read as `false`, so that a node nobody has declared is never treated as always on. A node whose profile declares `ALWAYS_ON_NODE=true` MUST carry the node label `ci-runner.io/always-on=true`. Every other node MUST NOT carry it: that covers a node whose profile declares `false` and a node that has no profile (a homelab container worker), and the reconcile that sets the label MUST remove it from each such node that carries it. A node whose profile cannot be read (its `ALWAYS_ON_NODE` is neither value) MUST be skipped and reported, with its label left as it is, and while a committed profile names no node, a labelled node that no readable profile names MUST be skipped and reported in the same way: a profile that cannot be read is not a declaration of `false`. The label MUST NOT be set or removed by hand. It MUST be re-established at node registration or by a mechanism that runs unattended at control-plane boot, with no playbook applied and no command run on any host, exactly as the factory label is; a reconcile that runs only when a playbook is applied MAY also correct it but MUST NOT be the only mechanism that sets it. Every runner scale set's values MUST place its Actions Runner Controller listener pod only on nodes that carry that label, by a node selector or a required node affinity on the listener's pod template, and the repository's check suite MUST refuse a scale set values file that lacks that placement, naming the file. The unattended converge at control-plane boot MUST re-assert the label from the committed profiles before it installs or upgrades any runner scale set. Every route that installs or upgrades a runner scale set (that converge, and an install run by hand) MUST first read which nodes carry the label, and MUST install or upgrade no scale set, saying why, when no node carries it or when that read fails: a scale set installed then would have a listener that can be placed nowhere, and it would take no jobs. A failed read MUST NOT be taken as an answer in either direction. At control-plane boot that stop MUST be scoped to the scale sets: every other step of the converge (the controller, the node-status credentials, the factory namespace and the label reconciles among them) MUST still run, because a factory run or a delegated gate needs no CI listener, and the converge MUST then end with a failure that names the scale sets it did not install. The repository MUST carry a committed, read-only read-back that lists each scale set's listener pod with the node it runs on. It MUST read the installed scale sets themselves, so that a scale set with no listener object at all is reported and not merely absent from the list. It MUST exit with status 1 when no scale set is installed, when a scale set has no listener or no listener pod, when a listener pod is not Running, or when one runs on a node that does not carry the label. It MUST exit with status 2 when a read of the cluster fails. A failed read MUST NOT be reported as a correct placement.

In `SPECIFICATION/scenarios.md`, insert the following two scenarios after the scenario "a factory node keeps its factory label across a control-plane reboot" and before the scenario "a node-loss drill holds one agent node NotReady and restores it without touching its workloads". When the three scenarios of the pending proposal `factory-budget-admission-counts-memory` are already there, these two go after the last of them (see the in-flight survey for the order).

## Scenario: every scale set's listener pod runs on an always-on node

Given every pool node's committed profile declares `ALWAYS_ON_NODE`

And each node whose profile declares `ALWAYS_ON_NODE=true` carries the `ci-runner.io/always-on=true` label, and no other node carries it

When the runner scale sets are converged from their committed values

Then each scale set's listener pod MUST be Running on a node that carries `ci-runner.io/always-on=true`

And a listener pod MUST NOT run on a node whose profile declares `ALWAYS_ON_NODE=false` or on a homelab container worker

And the committed read-back MUST list each scale set's listener pod with its node and MUST exit with status 0

## Scenario: the listener read-back fails when a listener is on a node that is not always on

Given a scale set's listener pod runs on a node that does not carry `ci-runner.io/always-on=true`

And another installed scale set has no listener at all

When an operator runs the committed listener read-back

Then the read-back MUST name the first scale set, its listener pod and the node

And the read-back MUST name the second scale set as having no listener

And the read-back MUST exit with status 1

**Co-edit owed at revise.** This proposal adds two `## ` headings to `scenarios.md` and none to `non-functional-requirements.md`. The revise that accepts it MUST add one `tests/heading-coverage.json` entry per new scenario heading in the same commit, at these tiers:

- "every scale set's listener pod runs on an always-on node" needs the live production cluster, so its proof is host-captured. Its row is a spec-first `"test": "TODO"` row whose `reason` names the host-captured tier and the owning work item, with a `work_item` key naming livespec-dev-tooling-crvvxt while that item is open.
- "the listener read-back fails when a listener is on a node that is not always on" is covered at the unit tier by one test, which builds the scenario's whole setup in one run (a listener on a node without the label, and another installed scale set with no listener): `tests/livespec_dev_tooling/test_always_on_node_label.py::test_the_read_back_names_a_misplaced_listener_and_a_scale_set_with_no_listener_in_one_run` (livespec-dev-tooling#4414). Its row's `test` value names that test alone, in the map's dotted form (`tests.livespec_dev_tooling.test_always_on_node_label.test_the_read_back_names_a_misplaced_listener_and_a_scale_set_with_no_listener_in_one_run`), and it is not a TODO row, provided livespec-dev-tooling#4414 has merged before the revise.

The revise MUST then run `just generate-heading-coverage-debt-register` and stage `tests/heading-coverage-debt.json`.
