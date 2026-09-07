# `ci-runner/observability/` — what the PowerEdge pool emits, and what reads it

Every unit in this directory posts OTLP to the host's local OTel collector on
`127.0.0.1:4319`, which exports to the `livespec` Honeycomb environment. The
units themselves are described in the `observability/` row of
[`../README.md`](../README.md); this file covers the READERS — the Honeycomb
triggers and the board that those emissions exist for — and how each is
applied.

`install-observability.sh` is the only sanctioned way to install or update the
live copies of the units on the host. It does not touch Honeycomb; the two
appliers below do, and only they.

## The two datasets, and why a reader has to know

The `livespec` environment is a Honeycomb **Metrics 2.0** environment. Every
OTLP **metric** lands in its single `metrics` dataset, and an
`x-honeycomb-dataset` header naming another dataset is ignored there — measured
2026-08-23, when a header naming `livespec-host-metrics` created nothing and
the rows appeared in `metrics` anyway. Gauges are therefore told apart by
metric NAME plus `host.name`, never by dataset.

**Events** and traces are different: the collector's Honeycomb exporter sets no
dataset header, so they auto-route by `service.name`. The running-job wide
events emitted by `ci-pool-attributed-gauges.sh` carry
`service.name = ci-runner-pool` and so land in a **separate `ci-runner-pool`
dataset**, which Honeycomb creates on the first POST.

So a reader spanning both signal families spans two datasets. The board below
does, and each of its panels names its own dataset for that reason.

## `triggers/` — the alarms

Value and dead-man triggers, one `*.json` per trigger, converged by name:

```bash
/usr/local/bin/with-livespec-env.sh -- ci-runner/observability/triggers/apply-triggers.sh
```

Each definition may name a `dataset`; absent, it defaults to `metrics`.

## `boards/` — the pool board

One board, `ci-runner-pool.json`, named **"CI runner pool — PowerEdge: queued,
admitted and running by repository"**. It is the named READER of the
per-repository pool gauges and of the running-job wide events emitted by
`ci-pool-attributed-gauges.sh`, and of the fleet sums and lifecycle stall
classes emitted by
`../k3s/phase2/runner-pod-lifecycle/scan-runner-pod-lifecycle.sh`. Apply it the
same way:

```bash
/usr/local/bin/with-livespec-env.sh -- ci-runner/observability/boards/apply-boards.sh
```

It prints one line per panel, then `created|updated <id> <name>` and the
board's URL. Record that URL on `livespec-mqy35a` in the livespec repository
the first time it is created.

Its five query panels and the dataset each reads:

| Panel | Dataset | Reads |
|---|---|---|
| Pool queue depth by repository | `metrics` | `livespec.ci_pool.queue_pending` and `.queue_admitted`, broken down by `ci.repository` |
| Pool runners by repository and phase | `metrics` | `livespec.ci_pool.runners`, broken down by `ci.repository` and `ci.runner_phase` |
| Pool fleet totals against quota | `metrics` | `livespec.ci_kueue.pending` and `.admitted` against `livespec.ci_churn_slot.quota_sum` and `.allocatable` |
| Runner-pod lifecycle stall classes | `metrics` | all ten `livespec.ci_lifecycle.<class>` gauges |
| Pool running jobs now | `ci-runner-pool` | the per-runner wide events: repository, workflow ref, run id, job name, phase and age |

The lifecycle panel names **ten** classes, not the seven the `phase2/README.md`
table row still lists: the original `pvc-pending`, `bind-deadline`,
`inotify-emfile`, `containerd-deadline`, `hook-failure`, `stale-listener` and
`capacity-absent`, plus `warm-cache-oversize`, `start-seed-cost` and
`api-unavailable` added since. All ten are live columns in `metrics`.

### A panel whose columns do not exist yet is skipped, not fatal

Honeycomb creates a dataset on its first datapoint and a column on its first
value. The first three panels read gauges that already exist; the other two
read `livespec.ci_pool.*` columns and a `ci-runner-pool` dataset that no
datapoint has created until `install-observability.sh` has run on the host.

`apply-boards.sh` therefore resolves each panel independently: a query the API
refuses is reported, that panel is dropped from this apply, the rest are
applied, and the script exits non-zero so the incompleteness is visible rather
than silent. Re-running after the host apply completes the board with **no edit
to the definition** — the whole board is defined from the start.

A re-run with nothing changed reuses every existing query and annotation and
re-applies an identical board, so it is a no-op in shape as well as in name.
