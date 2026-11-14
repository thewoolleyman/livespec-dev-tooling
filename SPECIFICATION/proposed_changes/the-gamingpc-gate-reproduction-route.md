---
topic: the-gamingpc-gate-reproduction-route
author: claude-opus-5-5
created_at: 2026-11-13T06:31:07Z
---

## Proposal: Every gate Job renders onto the one gate queue, and the gamingpc reproduction route is retired

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State that every gate Job manifest the renderer renders names the `gates-lq` LocalQueue, that `render-gate-job.sh` refuses the retired `--queue` and `--repro-stack-interval` flags with a usage error naming the flag, and that the pool's converge deletes the three Kueue objects of the retired gamingpc reproduction route (`gates-repro-cq`, `gates-repro-gamingpc-flavor`, `gates-repro-lq`) idempotently. A scenario states the observable behaviour. Today the spec is silent on the route, so both its existence and its removal are unratified.

### Motivation

Work item livespec-dev-tooling-caq7uh, a child of plan gate-job-resources (epic livespec-dev-tooling-ukoeah), assertion 6 (stranded capacity). livespec-dev-tooling-pkmxgu added an operator reproduction route so that one diagnosed full-suite gate could run on gamingpc-xubuntu while gates-cq's gamingpc lane was held at zero for livespec-dev-tooling-ddy5xu (AppArmor denying signals inside the gate container). ddy5xu is closed, and gates-gamingpc-flavor admits gates again (livespec-dev-tooling#4290, then livespec-dev-tooling#4454 at one gate unit). livespec-dev-tooling#4321 zeroed the reproduction lane's quota as a same-day fix, because gamingpc's factory_pod_budget derivation counts only one pinned gate lane. The route is dead behind that zero, and the item deletes it: gate_repro.py and its tests, gate-repro.sh, the renderer's two flags and the stack-diagnostics block they render into gate-job-template.yaml, section Y of render-gate-job-exit-tests.sh, the justfile recipe, cluster-queue-repro-gates.yaml and the reproduction-lane lines of gamingpc's host_vars. The converge applies committed files and never prunes, so removing the yaml would leave the three cluster objects in place; the deletion has to be part of the converge so that the retirement is reached through the normal route rather than a hand `kubectl delete`. Before filing, legacy-coordinator-agent's two conditions were checked on 2026-11-12: homelab-k8s-worker-nodes confirmed nothing of its work still needs the route, and `git grep` at HEAD of every repository under /data/projects found no gate-repro, gate_repro or gates-repro outside livespec-dev-tooling. Alignment: the pending proposal gate-placement-and-kueue-admission names `gates-repro-cq` in a parenthetical list of gate ClusterQueues whose admissions are recorded. That clause stays true once the queue is gone (a deleted queue admits nothing), so this proposal aligns with it; whichever revise lands second SHOULD drop the stale name from that list.

### Proposed Changes

In `contracts.md` §"Delegated pre-push gate", add one bullet after **Gate lane headroom**:

- **One gate queue.** Every gate Job manifest that `ci-runner/k3s/phase2/gates/render-gate-job.sh` renders MUST name `gates-lq` as its `kueue.x-k8s.io/queue-name` LocalQueue, so every gate Job the gate client submits is admitted through the `gates-cq` ClusterQueue and its committed lanes. The renderer MUST NOT accept a flag that selects another LocalQueue or that adds a diagnostics container to the Job: invoked with `--queue` or with `--repro-stack-interval`, it MUST exit non-zero with a usage error that names the flag it did not recognise, and it MUST NOT print a manifest. The operator reproduction route that once ran a gate on a lane held at zero (the `gates-repro-cq` ClusterQueue, the `gates-repro-gamingpc-flavor` ResourceFlavor and the `gates-repro-lq` LocalQueue in namespace `gates`) is retired. The self-hosted pool's converge MUST delete those three objects whenever it runs, and the delete MUST be idempotent: an object that is already absent MUST NOT fail the converge. A lane that has to be withheld MUST be withheld by its quota in `cluster-queue-gates.yaml`, never by a second queue. This bullet binds every gate Job the gate client submits, so it covers §"Delegated commit-time replay test runs", §"Delegated pre-commit aggregate" and §"Delegated gate-runner runs" as well as this section. It is spec-first: as of its ratification the renderer still carries both flags and the three objects exist on the cluster; work item livespec-dev-tooling-caq7uh owns the change.

In `scenarios.md`, add:

## Scenario: a gate Job renders onto the one gate queue and the renderer refuses the retired reproduction flags

```gherkin
Given the committed gate Job renderer ci-runner/k3s/phase2/gates/render-gate-job.sh
When it renders a gate Job manifest from valid arguments
Then the manifest's kueue.x-k8s.io/queue-name label MUST be gates-lq.
And the renderer invoked with --queue gates-repro-lq MUST exit non-zero with a usage error naming --queue and print no manifest.
And the renderer invoked with --repro-stack-interval 30 MUST exit non-zero with a usage error naming --repro-stack-interval and print no manifest.
```

The revise that accepts this proposal MUST add the scenario's heading to `tests/heading-coverage.json` in the same commit, as a spec-first `test: "TODO"` row whose `work_item` is livespec-dev-tooling-caq7uh and whose reason names the integration tier, and MUST register it in the debt register.
