---
topic: arc-listener-pods-spread-across-always-on-nodes
author: claude-fable-5-2:homelab-k8s-worker-nodes
created_at: 2026-11-13T09:03:11Z
---

## Proposal: Spread the ARC listener pods across the always-on nodes, softly, and count them per node in the read-back

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds one paragraph to non-functional-requirements.md §"Runner-pool node rebuild recipe", directly after the paragraph "**Always-on posture from the profile, and listener placement by it.**" that the pending proposal `arc-listener-pods-run-only` adds. The new paragraph requires every runner scale set's Actions Runner Controller (ARC) listener pod to carry a soft topology spread over the node hostname and a toleration of the `livespec.io/factory-pressure` taint, so that the listeners of the scale sets do not all sit on one always-on node. It also adds a per-node count to the committed listener read-back. Adds two scenarios to scenarios.md. Work item livespec-dev-tooling-zrsyfp owns the implementation.

### Motivation

Measured on the production cluster, 2026-11-13 at about 09:00Z (work item livespec-dev-tooling-zrsyfp, a follow-on to livespec-dev-tooling-crvvxt).

- 15 of 15 listener pods were Running on hp-xubuntu. The read-back of livespec-dev-tooling-crvvxt exits 0 on that state, correctly: every listener is on an always-on node. But one loss of hp-xubuntu stops every scale set at once, until the pods are rescheduled or the committed `clear-lost` action is run.
- Three nodes carry `ci-runner.io/always-on=true`: poweredge-xubuntu, gmktec-xubuntu and hp-xubuntu. The first two carry the taint `livespec.io/factory-pressure=high:PreferNoSchedule`; hp-xubuntu carries no taint. A listener pod carried only the default not-ready and unreachable tolerations and no spread constraint. So hp-xubuntu is the only always-on node the scheduler did not score down.
- Every listener pod carries the label `app.kubernetes.io/component=runner-scale-set-listener` (15 of 15 selected by it), so one selector covers the listeners of every scale set.
- The ARC controller in use (chart 0.14.2) copies `tolerations` and `topologySpreadConstraints` from `listenerTemplate` onto the listener pod, as it copies `nodeSelector` (`mergeListenerPodWithTemplate` in its resourcebuilder.go at tag gha-runner-scale-set-0.14.2).

Why the spread is soft. A required spread counts a node that is not Ready as a place holding no listener. After one node loss it would then refuse to place the displaced listeners on the remaining nodes. The rule exists to make a node loss cost less, so the spread must never hold a listener unscheduled.

Why the toleration is part of the rule. The factory-pressure taint filters nothing; it lowers a node's score. A soft spread is a score as well, and the default scheduler weighs the taint score above the spread score. Without the toleration the spread may change nothing on a cluster where all but one always-on node carry the taint, which is the production cluster today. A listener pod is small and long-lived, so its cost to a factory node is small.

Why the read-back reports and does not refuse. After a node loss the listeners are rightly on fewer nodes, and with one always-on node Ready they are all on it. A read-back that failed on concentration would fail exactly when the fleet is behaving as intended. The outcome is asserted at converge time, with two or more always-on nodes Ready, and not by the read-back's exit status.

Ruling and ordering. legacy-coordinator-agent ordered this follow-on on 2026-11-13 at about 09:00Z, at fleet scope (every scale set). This proposal depends on `arc-listener-pods-run-only`: it names the paragraph and a scenario that proposal adds, so it MUST be revised after that proposal, in the same cut or a later one.

Not established: whether the toleration and the soft spread are enough, by themselves, for the scheduler to place 15 pods across three nodes, since the resource and image-locality scores still count. The first scenario below is the test. If the converge leaves the listeners on one node, the implementation strengthens the placement; the rule does not change.

In-flight survey, 2026-11-13 at about 09:01Z. Remote `spec/*` branches and open pull requests that touch `SPECIFICATION/` were read. None of the open pull requests changes listener placement: livespec-dev-tooling#4481 (`runner-placement-post-add-tie`) and livespec-dev-tooling#4478 (`the-runner-scheduler-fail-open`) concern runner pods and name no listener. On master, the pending proposals `arc-listener-pods-run-only`, `factory-budget-admission-counts-memory`, `delete-the-dead-phase-1` and `the-arc-runner-version-pin` touch the same section or the same part of `scenarios.md`. This proposal aligns with each: it changes no paragraph any of them changes, and it places its text relative to what `arc-listener-pods-run-only` adds.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "Runner-pool node rebuild recipe", insert the following paragraph immediately after the paragraph that begins "**Always-on posture from the profile, and listener placement by it.**". No heading is added, removed or renamed in that file.

**Listener spread across the always-on nodes.** The listener pods of the runner scale sets MUST NOT all depend on one node while more than one always-on node is available. Every runner scale set's values MUST declare, on the listener's pod template, one topology spread constraint over the node hostname (`kubernetes.io/hostname`) that selects the listener pods of every scale set together, by a label they all carry. That constraint MUST NOT hold a listener unscheduled when it cannot be met (`whenUnsatisfiable: ScheduleAnyway`): a required spread counts a node that is not Ready as a place with no listener, so after a node loss it would keep the displaced listeners off the nodes that remain. Every runner scale set's values MUST also make the listener tolerate the `livespec.io/factory-pressure` taint. That taint only lowers a node's score, and while a listener does not tolerate it, it outweighs the spread on every always-on node that carries it. The always-on node selector MUST stay as it is: the spread chooses among the always-on nodes and MUST NOT admit any other node. The repository's check suite MUST refuse a scale set values file that lacks the spread constraint or the toleration, naming the file. When two or more always-on nodes are Ready at the time the scale sets are converged, the listener pods MUST afterwards be Running on at least two nodes, and a single node MUST NOT run more than half of them. The committed listener read-back MUST print, for each node that carries the always-on label, the number of listener pods Running on it, and it MUST print a node that runs none with a count of zero. That count MUST NOT change the read-back's exit status: after a node loss the listeners are rightly on fewer nodes, so a concentration is reported and not refused.

In `SPECIFICATION/scenarios.md`, insert the following two scenarios immediately after the scenario "the listener read-back fails when a listener is on a node that is not always on", which the pending proposal `arc-listener-pods-run-only` adds, and before the scenario "a node-loss drill holds one agent node NotReady and restores it without touching its workloads".

## Scenario: the listener pods of the scale sets are spread across the always-on nodes

Given two or more nodes carry the `ci-runner.io/always-on=true` label and each of them is Ready

And at least one of those nodes carries the `livespec.io/factory-pressure` taint

When the runner scale sets are converged from their committed values

Then listener pods MUST be Running on at least two of those nodes

And a single node MUST NOT run more than half of the listener pods

And every listener pod MUST run on a node that carries `ci-runner.io/always-on=true`

## Scenario: the listener read-back counts the listener pods on each always-on node

Given three nodes carry the `ci-runner.io/always-on=true` label

And every scale set's listener pod is Running on one of those three nodes, with all of them on the same node

When an operator runs the committed listener read-back

Then the read-back MUST print one line for each of the three nodes with the number of listener pods Running on it

And the two nodes that run no listener pod MUST each be printed with a count of zero

And the read-back MUST exit with status 0

**Co-edit owed at revise.** This proposal adds two `## ` headings to `scenarios.md` and none to `non-functional-requirements.md`. The revise that accepts it MUST add one `tests/heading-coverage.json` entry per new scenario heading in the same commit, at these tiers:

- "the listener pods of the scale sets are spread across the always-on nodes" needs the live production cluster, so its proof is host-captured. Its row is a spec-first `"test": "TODO"` row whose `reason` names the host-captured tier and the owning work item, with a `work_item` key naming livespec-dev-tooling-zrsyfp while that item is open.
- "the listener read-back counts the listener pods on each always-on node" is covered at the unit tier by a stub-kubectl test of `ci-runner/k3s/phase2/arc/read-listener-placement.sh`. Until livespec-dev-tooling-zrsyfp lands that test, its row is a spec-first `"test": "TODO"` row whose `reason` names the unit tier and that work item, with a `work_item` key naming it.

The revise MUST then run `just generate-heading-coverage-debt-register` and stage `tests/heading-coverage-debt.json`.
