# Scheduled Rule-26 kill-matrix runs

The Rule-26 kill matrix (its contract is in `SPECIFICATION/contracts.md`, "Rule-26 mutation kill
matrix") runs on demand through `just mutation-kill-matrix <target>`, or on a
schedule through `just mutation-kill-matrix-scheduled <target>`. A scheduled
run is advisory. It is never part of `just check`, a commit or push hook, or a
required per-PR job, and nothing waits on it.

## What one scheduled run writes

All paths are relative to the target package root:

| Path | What it is |
|---|---|
| `reports/mutation-kill-matrix.json` | The fresh report, in the same format as an on-demand run. |
| `reports/previous/mutation-kill-matrix.json` | The previous run's report, retained before this run starts. |
| `reports/mutation-kill-matrix-changes.json` | The what-changed summary against the retained report. |
| `reports/mutation-kill-matrix-cache.json` | The result cache, so an unchanged mutant is not re-tested. |

The first scheduled run has no retained report. It writes the report alone and
says so in its output.

Engine flags pass through, for example `--workers 16 --timeout 120`. The worker
trees are full copies of the target, so give `--workspace` a disk with room for
`workers` copies when `/tmp` is small.

## Where a scheduled run executes

On a fleet host, run the engine inside the host's Kubernetes cluster, never as
a bare host process. The engine's workers are threads in one process, and each
drives its own pytest subprocesses, so a run uses up to `--workers` CPUs. A
bare process that size is invisible to the cluster scheduler and to the CI
node's slot accounting. Measured 2026-11-09: kill-matrix processes running
outside k3s took about half of hp-xubuntu's CPU and skewed a CI baseline.

Use a `CronJob` whose pod requests what the run uses:

- `resources.requests.cpu` equal to `--workers`;
- the clone and the reports directory on a persistent volume, so the retained
  report and the cache survive between runs;
- `concurrencyPolicy: Forbid`, so two runs never share one report path;
- the command `just mutation-kill-matrix-scheduled <clone> --workers <n>`.

Run the engine on Linux: mutmut's forked runner crashes on macOS hosts.

Example schedule, as it appears in the `CronJob` spec:

```yaml
schedule: "0 2 * * *"
concurrencyPolicy: Forbid
```

A run on a single developer machine, outside any cluster, can use a systemd
user timer instead (`OnCalendar=*-*-* 02:00:00` with `Persistent=true`, running
the same command), when nothing else on that machine is measured.

A run that finds nothing to re-test finishes in about the time of one full
test-suite run, because the baseline and coverage pass always runs.

## Using a CI workflow instead

A CI workflow that runs the recipe must be triggered only by `schedule` and
`workflow_dispatch`, and must never be a required status check. Upload
`reports/mutation-kill-matrix.json` as an artifact. On the next run, download
it to `reports/previous/mutation-kill-matrix.json`, so the run writes a
what-changed summary.
