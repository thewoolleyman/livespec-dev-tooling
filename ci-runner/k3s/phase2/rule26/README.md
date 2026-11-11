# Rule-26 kill matrix as a cluster Job

This directory runs one full rule-26 mutation kill matrix of
`livespec-orchestrator-beads-fabro` as a Kubernetes Job (plan
`fleet-mutation-testing-rule-26`, work item `livespec-dev-tooling-fqnbtd`). The
engine is `livespec_dev_tooling.mutation_kill_matrix_runner`. Its contract is in
`SPECIFICATION/contracts.md`, under "Rule-26 mutation kill matrix".

## Why a Job

A kill-matrix run uses up to `--workers` CPUs for many hours. Run as a bare
host process, it is invisible to the scheduler and to the node's slot
accounting. On 2026-11-09, bare kill-matrix processes took about half of
hp-xubuntu's CPU and skewed a CI baseline. This Job requests and limits CPU
equal to its `--workers`, so the cluster accounts for it.

## What it creates

| Object | Purpose |
|---|---|
| Namespace `rule26` | Keeps the run apart from CI and gate workloads. |
| PVC `rule26-orchestrator-<node>` (local-path) | Holds the orchestrator clone, the engine, the uv cache, the worker trees and every run's outputs on that node, so they survive the pod. A local-path volume is bound to the node that first used it, so each node has its own claim. The original `rule26-orchestrator` claim, from runs before the node became a variable, stays bound to `poweredge-xubuntu` with its outputs. |
| Job `rule26-orchestrator-kill-matrix-<run>` | One run, pinned to the node passed as `rule26_kill_matrix_node`, `backoffLimit: 0`, with a 24-hour `activeDeadlineSeconds`. |

The Job clones the orchestrator and livespec-dev-tooling at the two commits
given, runs `uv sync --frozen`, installs the engine without changing the
orchestrator's locked dependencies, and widens `[tool.mutmut]` to the whole
first-party package and `tests/` tree. Then it runs the engine. Outputs land in
`/data/<run>/` on the node's PVC: `run.log`, `mutation-kill-matrix.json` and the
result cache. `run.log` records the start, end, exit code and elapsed seconds.

## Launch

A launch is a committed apply from the control node, never a hand `kubectl
apply` on a fleet host: the fleet host guard refuses that. The playbook
`ansible/rule26-kill-matrix.yml` (role `rule26_kill_matrix`) renders the
manifest on the control node with `./render-kill-matrix-job.sh` and applies it
on the k3s server:

```bash
just ansible-drift ansible/rule26-kill-matrix.yml \
  -e rule26_kill_matrix_orchestrator_sha=<40-hex> \
  -e rule26_kill_matrix_engine_sha=<40-hex> \
  -e rule26_kill_matrix_run=<lowercase id> \
  -e rule26_kill_matrix_node=<k3s node name>
just ansible-apply ansible/rule26-kill-matrix.yml -e ...   # the same -e flags
```

`rule26_kill_matrix_node` is required and names the k3s node
(`-e rule26_kill_matrix_node=hp-xubuntu`).
Read the node's unrequested CPU and memory first: the pod requests
`--workers` CPUs and stays Pending until that much is free.
`rule26_kill_matrix_workers` defaults to 12. If the node's CPU pressure (PSI
avg60) reads above 30 twice, re-launch with 8 (legacy-coordinator-agent ruling,
2026-11-09).

Revert, which deletes the whole `rule26` namespace, including every PVC and
every run's outputs:

```bash
just ansible-apply ansible/rule26-kill-matrix.yml -e rule26_kill_matrix_state=absent
```

## Watching

These commands only read:

```bash
kubectl -n rule26 get job,pods -o wide
kubectl -n rule26 logs -f job/rule26-orchestrator-kill-matrix-<run>
```
