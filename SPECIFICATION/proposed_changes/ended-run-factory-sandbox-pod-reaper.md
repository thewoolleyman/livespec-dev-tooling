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

Measured by legacy-coordinator-agent on 2026-11-19: four sandbox pods in namespace factory belong to runs that ended 14-46 hours ago (three failed, one succeeded). Each requests 3 cpu and 7630Mi and uses 0m. Together they hold 12 cpu and 30 GiB of Kueue requests, 9 cpu of it on gmktec-xubuntu (72% cpu and 75% memory requested there), which keeps gate, repro and sandbox work out. The section's closed Scope list and its rule that the node-recreated-pods plays leave in place every pod in a factory namespace stay correct for those plays; the one ratified factory sandbox deletion is the loss drill, which deletes one named run's pod. No ratified path deletes the pod of an ended run, and a hand kubectl delete is refused by the host guard. Deleting a sandbox is a safety-relevant act, so the path needs a spec clause.

### Proposed Changes

Add one bold-led paragraph to "Consent-gated pool-node disruption", after "A factory sandbox loss drill deletes exactly one named run's sandbox pod", and add "deleting the factory sandbox pod of a run that the Fabro server reports terminal" to the Scope list. Text of the paragraph: "**An ended-run sandbox reaper deletes only the factory sandbox pods of terminal runs, and only when their work is preserved.** A playbook that deletes the factory sandbox pod of a Fabro factory run that has ended is a disruption this section covers. It MUST be committed and applied from the control node `vps` with `just ansible-apply`, and such a pod MUST NOT be deleted for that purpose by a command run by hand. It MUST judge a run terminal from the Fabro server that owns the run, read through the committed carrier client, and MUST NOT judge it from a bare `fabro ps` or from the pod's own state. It MUST delete a terminal run's pod only when that run's tree is reachable from a ref on `origin` OR an export archive of the run reads back from a durable path that the play names, where a path under a dev host's tmp directory is not durable; a terminal run with neither MUST be left in place and named in the play's output. It MUST leave in place every pod of a run that the server does not report terminal, and every pod whose run cannot be read. It MUST provide a dry-run mode that lists the pods it would delete and deletes none, and a kill switch that, when set, makes it delete nothing and say that it is switched off. It MUST record, for each pod it deletes, the run id, the pod name, the node, the terminal state read and which preserve condition held. It MAY act on any node that carries a factory namespace pod. It never replaces the sandbox loss drill, which keeps its single named-run precondition."
