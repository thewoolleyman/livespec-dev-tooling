# CI pool job-hours by repository, 7 days to 2026-10-22T01:14:57Z

Measured for work-item `livespec-dev-tooling-u5j5f6` (coordinator R541) by
`claude:delegated-gate-fleet-rollout`. This note is the measured input the
re-derivation of the Kueue demand weights consumes (`ci-runner/k3s/phase2/kueue/DERIVATION.md`).
It records the numbers and the query. It does not apply them.

## What was measured

One `cache.job-summary` span per CI job pod on the k3s pool, emitted by
`ci-runner/k3s/phase2/cache-telemetry/ci-cache-span.sh`. The span starts at the
job container's postStart (`started_at_ns` in the pod's state dir) and ends at
its preStop. Its `duration_ms` is the time the job held a pod on the pool, and
its `repo` attribute comes from the runner's `event.json`. Only pool pods emit
this span, so hosted-runner jobs are excluded by construction.

Job-hours are `SUM(duration_ms) / 3,600,000`.

## The query

Environment `livespec`, dataset `github-ci`. Run through the Honeycomb MCP
`run_query` tool with `HONEYCOMB_MCP_API_KEY_LIVESPEC`, as described in `.ai/honeycomb-query-credential.md`.

```json
{
  "from": "-7d",
  "to": "now",
  "filters": [{"column": "name", "op": "=", "value": "cache.job-summary"}],
  "breakdowns": ["repo"],
  "calculations": [
    {"op": "COUNT"},
    {"op": "SUM", "column": "duration_ms"},
    {"op": "P50", "column": "duration_ms"},
    {"op": "MAX", "column": "duration_ms"}
  ],
  "orders": [{"op": "SUM", "column": "duration_ms", "order": "descending"}]
}
```

The run started at 2026-10-22T01:14:57Z, so the window is 2026-10-15T01:14:57Z to 2026-10-22T01:14:57Z.

## Results

| Repository | Jobs (spans) | P50 job (s) | SUM(duration_ms) | Job-hours | Share |
|---|---:|---:|---:|---:|---:|
| `livespec-orchestrator-beads-fabro` | 11,860 | 26.9 | 696,802,474.57 | 193.56 | 69.24% |
| `livespec-dev-tooling` | 3,304 | 26.5 | 136,182,515.69 | 37.83 | 13.53% |
| `livespec` | 1,267 | 24.1 | 37,621,491.47 | 10.45 | 3.74% |
| `livespec-overseer` | 983 | 21.5 | 36,079,571.04 | 10.02 | 3.59% |
| `livespec-orchestrator-git-jsonl` | 1,277 | 16.6 | 24,959,966.15 | 6.93 | 2.48% |
| `livespec-driver-claude` | 785 | 18.3 | 20,075,772.47 | 5.58 | 2.00% |
| `livespec-driver-pi` | 1,035 | 17.1 | 19,206,794.10 | 5.34 | 1.91% |
| `livespec-console-beads-fabro` | 320 | 23.7 | 15,472,382.40 | 4.30 | 1.54% |
| `livespec-driver-codex` | 779 | 17.4 | 15,376,912.89 | 4.27 | 1.53% |
| `livespec-runtime` | 259 | 14.6 | 4,520,871.00 | 1.26 | 0.45% |
| **total (10 repositories)** | **21,869** | | **1,006,298,751.78** | **279.53** | **100%** |

One further span had an empty `repo` (90,322.62 ms). It is excluded because no
event identity reached it.

## Indicative apportionment (not applied)

This applies the existing rule (Hamilton, C = 44, exact rationals, then the step-5 floor) to the job-hours as weights.
It is shown so the derivation's author can check their arithmetic. The derivation itself belongs to the work-item.

| Repository | Exact share | Floor | Quota | `max(2 x quota, 6)` |
|---|---:|---:|---:|---:|
| `livespec-orchestrator-beads-fabro` | 30.4674 | 30 | 30 | 60 |
| `livespec-dev-tooling` | 5.9545 | 5 | 6 | 12 |
| `livespec` | 1.6450 | 1 | 2 | 6 |
| `livespec-overseer` | 1.5776 | 1 | 1 | 6 |
| `livespec-orchestrator-git-jsonl` | 1.0914 | 1 | 1 | 6 |
| `livespec-driver-claude` | 0.8778 | 0 | 1 | 6 |
| `livespec-driver-pi` | 0.8398 | 0 | 1 | 6 |
| `livespec-console-beads-fabro` | 0.6765 | 0 | 1 | 6 |
| `livespec-driver-codex` | 0.6723 | 0 | 1 | 6 |
| `livespec-runtime` | 0.1977 | 0 | 1 (step-5 floor) | 6 |

The six leftover units go to the six largest remainders: dev-tooling, driver-claude, driver-pi,
console, driver-codex and livespec. The step-5 floor then lifts `livespec-runtime` from 0 to 1, so the quotas sum to 45.

DERIVATION.md handles that excess two ways, and they disagree. The rule paragraph says to
deduct the excess from the largest quota, which would make `livespec-orchestrator-beads-fabro` 29.
The "ONE known exception" paragraph says to keep the C + k sum. The work-item's
derivation has to pick one and say why.

## Caveats

- The span emit is best-effort (2 s timeout, failures only logged), so a job whose
  preStop could not reach the node's collector is missing. That undercounts every
  repository proportionally, and the shares are what feed the apportionment.
- The window includes the 2026-10-21 Petri cutover day and the factory's normal
  churn on `livespec-orchestrator-beads-fabro`. Its job count, 11,860, is 3.6 times
  the next repository's. The per-day stability of that skew was NOT checked here.
  A derivation that wants to exclude one atypical day should re-run the query with
  a narrower `from`/`to`.
- `ci.job.*` spans in the same dataset were NOT used. One series
  (`ci.job.check-factory-provenance`) carries impossible duration sums (about 3.4e15 ms over 430 spans).
  Those spans come from a different emitter and do not separate pool jobs from hosted ones.
