---
topic: ended-run-factory-sandbox-pod-reaper
author: gate-job-resources-session
created_at: 2026-11-19T08:26:49Z
---

## Proposal: ended-run-factory-sandbox-pod-reaper

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Section "Consent-gated pool-node disruption" gains one ratified factory sandbox deletion beside the sandbox loss drill: a committed, preserve-checked reaper that deletes the factory sandbox pod of a run the Fabro petri server reports terminal.

### Motivation

REVISION 2026-11-19 (legacy-coordinator-agent ruling on the failed revise): the first text said the reaper "MAY act on any node" with no confirmation variable, which contradicted "Committed and consent-gated" and the Scope sentence's "every other disruption above acts on a pool node named in inventory". This revision states the reaper as a THIRD explicit exception, beside the cordon/uncordon and the two pod-deleting plays, to both, and names the preconditions as the reason the per-host confirmation is not needed.


Measured by legacy-coordinator-agent on 2026-11-19: four sandbox pods in namespace factory belong to runs that ended 14-46 hours ago (three failed, one succeeded). Each requests 3 cpu and 7630Mi and uses 0m. Together they hold 12 cpu and 30 GiB of Kueue requests, 9 cpu of it on gmktec-xubuntu (72% cpu and 75% memory requested there), which keeps gate, repro and sandbox work out. The section's closed Scope list and its rule that the node-recreated-pods plays leave in place every pod in a factory namespace stay correct for those plays; the one ratified factory sandbox deletion is the loss drill, which deletes one named run's pod. No ratified path deletes the pod of an ended run, and a hand kubectl delete is refused by the host guard. Deleting a sandbox is a safety-relevant act, so the path needs a spec clause.

### Proposed Changes

Four edits to SPECIFICATION/non-functional-requirements.md, all inside section "Consent-gated pool-node disruption".

(1) **Scope list.** After the entry "deliberately deleting one Fabro factory run's factory sandbox pod to exercise the engine's resume of that run onto a re-acquired sandbox", add the entry "and deleting the factory sandbox pod of a run that the Fabro server reports terminal and whose work is preserved".

(2) **Scope closing sentence.** Replace "The node hold and the two pod-deleting plays MAY name any node registered in the cluster, including a node that has no inventory entry (a homelab container worker); every other disruption above acts on a pool node named in inventory." with: "The node hold and the two pod-deleting plays MAY name any node registered in the cluster, including a node that has no inventory entry (a homelab container worker). The ended-run sandbox reaper names no node: it acts on every node that holds a factory sandbox pod of a terminal, preserved run. Every other disruption above, the reaper excepted, acts on a pool node named in inventory."

(3) **"Committed and consent-gated".** Append to that paragraph: "The ended-run sandbox reaper is the third exception to the single-host confirmation variable, beside the cordon and uncordon and the two pod-deleting plays that accept a registered node. It is not an exception to the rest of this paragraph: it MUST be a committed playbook applied from `vps` with `just ansible-apply`, and its pods MUST NOT be deleted for this purpose by a command run by hand."

(4) **New paragraph**, after "A factory sandbox loss drill deletes exactly one named run's sandbox pod": "**An ended-run sandbox reaper deletes only the factory sandbox pods of terminal runs whose work is preserved, and needs no host confirmation because of that.** A playbook that deletes the factory sandbox pod of a Fabro factory run that has ended is a disruption this section covers, and it is the third exception named under \"Committed and consent-gated\". The per-host confirmation exists to protect live work from a disruptive play; this play touches no live work, and these preconditions, not a confirmation variable, are what make that so. It MUST judge a run terminal from the Fabro server that owns the run, read through the committed carrier client, and MUST NOT judge it from a bare `fabro ps` or from the pod's own state. It MUST delete a terminal run's pod only when that run's tree is reachable from a ref on `origin` OR an export archive of the run reads back from a durable path that the play names, where a path under a dev host's tmp directory is not durable; a terminal run with neither MUST be left in place and named in the play's output. It MUST leave in place every pod of a run that the server does not report terminal, and every pod whose run cannot be read. It MUST provide a dry-run mode that lists the pods it would delete and deletes none, and a kill switch that, when set, makes it delete nothing and say that it is switched off. It MUST record, for each pod it deletes, the run id, the pod name, the node, the terminal state read and which preserve condition held. It acts on whichever node holds such a pod, because a confirmation variable naming one host would defeat a play whose subjects are on whichever node ran them. It never replaces the sandbox loss drill, which keeps its single named-run precondition and its confirmation variable."

HEADING COVERAGE: this revision adds or changes no `## ` heading, so the revise owes no tests/heading-coverage.json row.
