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
| PVC `rule26-orchestrator` (local-path) | Holds the orchestrator clone, the engine, the uv cache, the worker trees and every run's outputs, so they survive the pod. |
| Job `rule26-orchestrator-kill-matrix-<run>` | One run, pinned to `poweredge-xubuntu`, `backoffLimit: 0`, with a 24-hour `activeDeadlineSeconds`. |

The Job clones the orchestrator and livespec-dev-tooling at the two commits
given, runs `uv sync --frozen`, installs the engine without changing the
orchestrator's locked dependencies, and widens `[tool.mutmut]` to the whole
first-party package and `tests/` tree. Then it runs the engine. Outputs land in
`/data/<run>/` on the PVC: `run.log`, `mutation-kill-matrix.json` and a copy of the
result cache. The live cache is `/data/cache/mutation-kill-matrix-cache.json`,
shared by every run on the PVC. The engine checkpoints it at most every 300 s,
so a run ended by its 24-hour deadline leaves its finished mutants for the next
run id, which reuses them and logs `mutation-kill-matrix: executed N/M mutants`. `run.log` records the start, end, exit code and elapsed seconds.

The engine also stores its baseline measurement (per-test coverage and the
baseline failures) beside the cache, as
`/data/cache/mutation-kill-matrix-cache-measure.json`. A later run over the
same orchestrator commit, engine image and dependency set reuses it, logs
`mutation-kill-matrix: reused the stored per-test coverage`, and skips the
serial measure stage (about 3.6 h on run 20261111t1). A change to any input
file, to the collected tests or to the per-test timeout measures again.
A reusing run does not trust the stored baseline failures: it runs each of
them again on the unmutated orchestrator and keeps only those that still
fail, so a test that failed once (one out-of-memory kill, say) rejoins
attribution in the next Job.

### One engine commit for the whole matrix

A matrix that needs several Jobs MUST run every Job on the same
`rule26_kill_matrix_engine_sha`. The cache key covers every installed
distribution's version, and the Job installs the engine into the
orchestrator's environment, so livespec-dev-tooling's own version is part of
the key (1.199.0 at `6a35f37d`, 1.200.0 at `a40114a6`). That is deliberate: the
orchestrator's tests import `livespec_dev_tooling`. A Job on a different engine
commit therefore reuses nothing from the Jobs before it, cache and stored
measurement alike. Fix the engine first, then start the matrix under a new run
id and keep that commit until the report is written.

### What a slow mutant costs

All of a mutant's selected tests run in one pytest process. When that process
ends before a test reports (a test hangs past the per-test timeout, or kills
the process), the first unreported test is run alone and the tests after it
run together in one further process. A selected test whose file cannot be
collected under the mutant counts as failed, with no process of its own. Run
20261111t2 predates this: it re-ran every unreported test alone, and no mutant
finished between 13:20Z and 14:03Z on 2026-11-12 while 9 of 12 workers sat in
that loop. A mutant that hangs many tests still costs one per-test timeout for
each of them.

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
  -e rule26_kill_matrix_run=<lowercase id>
just ansible-apply ansible/rule26-kill-matrix.yml -e ...   # the same -e flags
```

`rule26_kill_matrix_workers` defaults to 12. If the node's CPU pressure (PSI
avg60) reads above 30 twice, re-launch with 8 (legacy-coordinator-agent ruling,
2026-11-09).

Revert, which deletes the whole `rule26` namespace, including the PVC and
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
