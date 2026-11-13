# Full runtime mutation report as a retained cluster Job

This is the launch adapter for `livespec-dev-tooling-mrahu4` under
`fleet-mutation-testing-rule-26`. It uses the existing `rule26_kill_matrix`
drift/apply/stop role with a runtime namespace, PVC and Job name. The
orchestrator adapter keeps its existing defaults.

The target commit must contain the on-demand recipe from livespec-runtime#904
and pin a released engine containing the collected-node-ID repair. The Job
uses `uv sync --frozen --all-groups`, verifies the installed engine's VCS
commit and matching stable release tag, and runs the target's actual
`just mutation-kill-matrix`. It uses the consumer's pin without a source
override. Its contemporaneous `inputs.json` records that commit, version,
release tags, public executing-source digest, target revision, lock digest,
worker count and per-test timeout.

Before launch, verify the current plan admission and fleet launch conditions,
and choose the worker, memory and storage inputs from current capacity
evidence. These resource values are required; this adapter sets no host cap.
The renderer only writes YAML and contacts no cluster. The committed apply
runs from the control node against the inventory's k3s server.

```bash
just ansible-drift ansible/rule26-runtime-kill-matrix.yml \
  -e rule26_runtime_sha=<40-hex-target-commit> \
  -e rule26_kill_matrix_engine_sha=<40-hex-release-commit> \
  -e rule26_runtime_workers=<positive-integer> \
  -e rule26_runtime_memory=<Mi-or-Gi-quantity> \
  -e rule26_runtime_storage=<Mi-or-Gi-quantity> \
  -e rule26_kill_matrix_run=<unique-lowercase-id>
just ansible-apply ansible/rule26-runtime-kill-matrix.yml -e ...
```

The apply uses the same inputs as the reviewed drift. A fresh run ID is
required, and a PVC lock prevents overlapping runtime writers. Each run has
its own clones and worker trees. A 24-hour Job deadline includes setup;
`backoffLimit: 0` requires an explicit new run after failure. The result
cache is shared across runtime runs on this PVC, and the engine checkpoints
it normally. The orchestrator's namespace, cache and reports are separate.

In namespace `rule26-runtime`, PVC `rule26-runtime` retains:

| Path on PVC | Evidence |
| --- | --- |
| `<run>/run.log` | Setup and engine output. |
| `<run>/inputs.json` | Inputs verified before the engine starts. |
| `<run>/runtime/reports/mutation-kill-matrix.json` | Complete report after successful execution. |
| `<run>/result.json` | Exit status, finish time and report checksum, when the exit trap runs. |
| `cache/mutation-kill-matrix-cache.json` | Checkpointed outcomes for a subsequent run. |

A hard kill can leave no `result.json` or report. Retained logs and cache
then remain partial evidence; a finished matrix is still owed. The run is
advisory and removes no tests. Record its artifact/checksum and counts on the
parent plan before any pruning decision.

Stop just the named runtime Job and retain its namespace and PVC:

```bash
just ansible-apply ansible/rule26-runtime-kill-matrix.yml \
  -e rule26_kill_matrix_state=job-absent \
  -e rule26_kill_matrix_run=<run>
```
