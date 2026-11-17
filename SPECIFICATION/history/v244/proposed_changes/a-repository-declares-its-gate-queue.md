---
topic: a-repository-declares-its-gate-queue
author: claude-opus-5-5
created_at: 2026-11-15T07:31:34Z
---

## Proposal: A consuming repository declares the gate LocalQueue its full-size gate Jobs use

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A consuming repository MAY declare `gate_queue` under `[tool.livespec_dev_tooling]`, naming a LocalQueue in the `gates` namespace. The gate client passes that name to the renderer's `--queue` for every full-size gate Job, and Lane capacity compares the Job against the flavors of that LocalQueue's ClusterQueue. When the key is absent, Jobs keep `gates-lq` and `gates-cq`.

### Motivation

legacy-coordinator-agent ruled A+C for plan gate-job-resources item (i), as relayed by throughput-plans-coordinator on 2026-11-15. The orchestrator gate now requests 10 cpu, while every other repository's gate requests 5. Inside one ClusterQueue under BestEffortFIFO, each 5-cpu gap goes to a later 5-cpu gate, so the 10-cpu gate starves. Measured: workload job-gate-livespec-orchestrator-beads-fabro-9xphj-aea5a (gate_cpu 10, created 06:58:54Z) stayed unadmitted for 30 minutes while nine later 5-cpu gates were admitted. StrictFIFO on gates-cq is the interim fix (A), and its head-of-line wait lands on every repository. The ruling's (C) is a separate ClusterQueue for 10-cpu gates, in a cohort with gates-cq, routed by the repository's own gate configuration and never by inference from its request. Once (C) lands, gates-cq returns to BestEffortFIFO. Today the renderer already takes `--queue` (gate_repro passes `gates-repro-lq`), but no consumer key reaches it, and Lane capacity reads only `gates-cq`. Plan gate-job-resources research note 004 records the measurements.

### Proposed Changes

In SPECIFICATION/contracts.md, §"Delegated pre-push gate", **Declared gate resources**:

1. *Keys*: change "MAY declare three keys" to "MAY declare four keys", and add after the `gate_parallelism` bullet:
    - `gate_queue` is a TOML string naming a LocalQueue in the `gates` namespace, such as `"gates-wide-lq"`. It MUST match the gate client's LocalQueue name rule: lowercase letters, digits and hyphens, beginning with a letter and ending in `-lq`. This rule is NEW and belongs to the gate client. It is stricter than the renderer's own `--queue` check, which only requires `[a-z0-9-]` characters and no leading `-`, and the renderer's check stays as it is.

2. *Passing*: change "It MUST pass each declared value to the renderer's `--cpu`, `--memory` and `--parallelism`" to "It MUST pass each declared value to the renderer's `--cpu`, `--memory`, `--parallelism` and `--queue`". Then extend the defaults sentence to read: "A key that is absent MUST leave that Job at the default the renderer carries: CPU `5`, memory `6Gi`, parallelism `4` (`render-gate-job.sh`, its defaults line), and queue `gates-lq` (`render-gate-job.sh`, its own `queue=` default, which is not on the defaults line)." A Red-leg or Green-leg replay Job of **Replay Job size** is not a full-size gate Job and MUST stay on `gates-lq` whatever `gate_queue` names.

3. *Validation*: change "MUST validate the three keys" to "MUST validate the four keys", add "or is a `gate_queue` value that is not a string matching the LocalQueue name rule" to the refusal conditions, and add "a number or boolean for `gate_queue`" to the list of wrong types.

4. *Lane capacity*: change "no single flavor of the `gates-cq` ClusterQueue" to "no single flavor of the gate ClusterQueue". Add: "The gate ClusterQueue is the ClusterQueue that the declared `gate_queue` LocalQueue is bound to in the committed `ci-runner/k3s/phase2/kueue/` manifests, or `gates-cq` when `gate_queue` is absent. A declared `gate_queue` that names no LocalQueue in those committed manifests MUST be refused the same way, naming the key and its value." Also extend the comparison trigger so that a declaration of `gate_queue` triggers it, like `gate_cpu` and `gate_memory`.

In SPECIFICATION/scenarios.md add:

## Scenario: a declared gate queue routes a repository's full-size gate Jobs and leaves its replay Jobs on the default queue

Given a consuming repository that declares `gate_queue = "gates-wide-lq"` and `gate_cpu = 10` under `[tool.livespec_dev_tooling]`
And the committed Kueue manifests bind `gates-wide-lq` to a ClusterQueue with a flavor holding at least 10 cpu
When the gate client submits that repository's pre-push gate Job and a Red-leg replay Job
Then the pre-push gate Job MUST carry the `kueue.x-k8s.io/queue-name` label `gates-wide-lq`
And the Red-leg replay Job MUST carry the `kueue.x-k8s.io/queue-name` label `gates-lq`

## Scenario: a declared gate queue that names no committed LocalQueue is refused before any gate Job is submitted

Given a consuming repository that declares `gate_queue = "gates-missing-lq"`
And no committed Kueue manifest declares a LocalQueue named `gates-missing-lq`
When the gate client prepares a delegated push
Then it MUST refuse the push, naming `gate_queue` and `gates-missing-lq`
And it MUST NOT submit any gate Job

The revise commit that accepts this proposal MUST add both scenarios' rows to `tests/heading-coverage.json`, per the repository's revise co-edit discipline. Each row is a spec-first `"test": "TODO"` row naming its owed tier and owning `work_item`, and is registered in the debt register. The ClusterQueue that (C) creates (working name `gates-wide-cq`, LocalQueue `gates-wide-lq`) is GitOps realization in `ci-runner/k3s/phase2/kueue/` and is not stated by this proposal: it covers the flavors that can hold a 10-cpu gate (gmktec-xubuntu, poweredge-xubuntu, and gamingpc-xubuntu once its 10-cpu lane lands) and sits in a cohort with gates-cq.
