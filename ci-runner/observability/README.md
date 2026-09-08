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
dataset header, so they auto-route by `service.name`. The wide events emitted
by `ci-pool-attributed-gauges.sh` carry `service.name = ci-runner-pool` and so
land in a **separate `ci-runner-pool` dataset**, which Honeycomb creates on the
first POST. Two record kinds share that dataset and one POST — the running-job
rows and the per-phase start rows — told apart by `ci.record_kind`
(`running-job` / `start`) rather than by which columns happen to be populated.

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

### First, widen the configuration key — it cannot touch boards today

`HONEYCOMB_CONFIG_KEY_LIVESPEC` currently carries **Manage Queries and
Columns** but **not Manage Public Boards**. Measured 2026-09-07 against the
live environment, with the same key the trigger applier uses:

| Read | Result |
|---|---|
| `GET /1/triggers/metrics` | `200` |
| `GET /1/columns/metrics` | `200` |
| `GET /1/query_annotations/metrics` | `200` |
| `GET /1/boards` | `401 {"error":"this API key isn't allowed to access boards"}` |

So `apply-boards.sh` fails on its FIRST call until someone adds the **Manage
Public Boards** permission to that key, in the Honeycomb UI under Team
settings → Environments → `livespec` → API keys. Nothing in this repository
can grant it.

Note the shape of that refusal, because it is easy to mis-read: the boards
endpoint answers `401` with a JSON OBJECT, while a permitted-but-empty listing
answers `200` with a JSON ARRAY. Code that reaches for a `boards` key with a
default of `[]` turns the refusal into "the environment has no boards" and
reports a clean result for a call that was rejected. Branch on the status code,
never on whether a list came back empty.

Its seven query panels and the dataset each reads:

| Panel | Dataset | Reads |
|---|---|---|
| Pool queue depth by repository | `metrics` | `livespec.ci_pool.queue_pending` and `.queue_admitted`, broken down by `ci.repository` |
| Pool runners by repository and phase | `metrics` | `livespec.ci_pool.runners`, broken down by `ci.repository` and `ci.runner_phase` |
| Pool fleet totals against quota | `metrics` | `livespec.ci_kueue.pending` and `.admitted` against `livespec.ci_churn_slot.quota_sum` and `.allocatable` |
| Runner-pod lifecycle stall classes | `metrics` | all ten `livespec.ci_lifecycle.<class>` gauges |
| Pool running jobs now | `ci-runner-pool` | the per-runner wide events: repository, workflow ref, run id, job name, phase and age |
| Runner start latency, broken into phases | `ci-runner-pool` | P95 of each `ci.start_*_s` field on the start wide events (`ci.record_kind = start`) |
| Runner start phases by repository | `metrics` | the four `livespec.ci_pool.start_*_s` gauges and `livespec.ci_pool.starts_observed`, broken down by `ci.repository` |

The lifecycle panel names all **ten** classes: the original `pvc-pending`,
`bind-deadline`, `inotify-emfile`, `containerd-deadline`, `hook-failure`,
`stale-listener` and `capacity-absent`, plus `warm-cache-oversize`,
`start-seed-cost` and `api-unavailable` added since. All ten are live columns
in `metrics`. The `phase2/README.md` table row lists the same ten; a class
added to the sweep's `EMIT_CLASSES` has to be added to both, and to this
board's lifecycle panel, or the panel silently under-reports.

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

## Start latency is reported PER PHASE, and one aggregate is not an acceptance signal

**A single runner-pod-to-workflow-pod delta is not an acceptance signal for
anything, and no claim about start latency may cite one.** That number is four
stacked waits summed. It indicts no component when it regresses, and it
convicts the wrong one when it does not: on 2026-09-08 a 60 s aggregate made
`livespec-wm7c`'s criterion read as unmet while the phase that item actually
owns was about 4 s. `ci-pool-attributed-gauges.sh` therefore emits the start
interval as its parts (`livespec-ifwnqj.6`), and a latency claim cites the
phase it is about:

| Phase | Measured from → to | Indicts |
|---|---|---|
| 1 created → scheduled | pod `.metadata.creationTimestamp` → the `PodScheduled` condition | Kueue admission, the scheduler's bind, and the `WaitForFirstConsumer` work volume's provisioning |
| — of which, volume bound | pod `.metadata.creationTimestamp` → the creationTimestamp of the PersistentVolume bound to `<runner pod>-work` | the local-path provisioner and its helper pod, inside phase 1 |
| 2 scheduled → ready | `PodScheduled` → `Ready` | containerd's sandbox creation, the image, the runner process |
| 3 ready → job assigned | **not emitted** | — see below |
| 4 ready → workflow pod | `Ready` → the workflow pod's `.metadata.creationTimestamp` | phases 3 **and** 4 together; an UPPER BOUND on the ARC container hook's `prepare-job` |

**Phase 3 has no clock, and nothing invents one.** The EphemeralRunner status
carries the *fact* of a job assignment (`jobRepositoryName` and its siblings
become non-empty) but no timestamp for it, the pod's conditions do not move at
assignment, and the workflow pod does not exist yet. The emitter's own tick
clock would encode the sampler's 60 s cadence as the runner's latency, and the
GitHub API's `started_at` is neither a cluster listing nor free. So phase 3 is
absent — no gauge, no event field, no stand-in — and what it costs, it costs to
the ready→workflow-pod number, which is named for the two boundaries the
emitter can actually see rather than for the hook. **A claim about the container
hook cites the hook's own log line, not this series.**

**The emission SAMPLES starts, so a gap is never a stall.** A start is
computable only while both the runner pod and its `<name>-workflow` pod are
present, so a job short enough to appear and vanish inside one 60 s tick is
never observed at all; a runner sampled after its job finished may have flipped
`Ready` back to `False`, and the phases needing `Ready` are then omitted rather
than computed from a transition in the wrong direction. The bias runs one way,
toward the longer-lived job, and it is a bias in *which* starts are sampled and
never in the durations reported for the ones that are.
`livespec.ci_pool.starts_observed` is emitted every tick, `0` included, so an
empty stretch of the phase series can always be told apart from a broken
emitter — the same discipline the running-job events discharge through
`livespec.ci_pool.runners_total`.

**Measuring ONE start, in a quiet window.** This is the form a start-latency
acceptance claim cites. Start a single job on an otherwise idle pool, and while
it is running, on the host:

```bash
/usr/local/lib/ci-runner/ci-pool-attributed-gauges.sh --single-start
```

It reads the same four listings once, ignores the emission window, prints every
start it can compute as a per-phase breakdown, and **POSTs nothing** — a mode
meant to be run by hand at any moment must not inject a duplicate datapoint into
the series it exists to explain. Pass a runner name to report just that runner.
It exits `3` when the cluster read cleanly and no start was computable, which
means neither pod was there: run it while the job is running. It needs no
waiting and no loop, because both pods live for the job's duration.

This mode is the committed successor to the single-start watcher of
`livespec`'s `plan/ci-runner-pod-lifecycle-reliability/research/005`, which was
a session-local loop whose raw rows that note itself records as "not a durable
source". There is no second timer, no second unit and no second polling loop:
the per-tick emission rides the existing 60 s
`ci-pool-attributed-gauges.timer`, widened with the two listings the
EphemeralRunner objects cannot supply (pod conditions and PersistentVolume
bind times), exactly as the running-job events widened the EphemeralRunner
listing rather than standing up an emitter of their own.
