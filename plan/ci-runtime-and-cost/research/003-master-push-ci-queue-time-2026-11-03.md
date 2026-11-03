# 003 — Master-push CI queue time vs pull-request CI (2026-11-03)

Asked by legacy-coordinator-agent at 2026-11-03 ~10:55Z. Dev-tooling MASTER CI runs were sitting queued for more than 30 minutes behind PR CI. The orchestrator Dispatcher's master-CI preflight then refused dev-tooling dispatches after its bounded wait: ftgiu4 and dnokt2 were refused, and about ten more items were exposed. Measured read-only with `gh api` reads and `kubectl get` over ssh to poweredge-xubuntu. Nothing was changed.

## Measurement (window 2026-11-02T10:33:55Z to ~11:50Z next day)

Queue wait = job `started_at − created_at`, counted over completed, non-skipped jobs of the `CI` workflow that ran on a k3s self-hosted label.

| repo / event | runs | jobs | job wait median | p90 | max | per-run worst job median / p90 |
|---|---|---|---|---|---|---|
| livespec-dev-tooling master push | 107 | 941 | 3.8 min | 50.7 | 109.7 | 9.4 / 62.0 |
| livespec-dev-tooling pull_request | 222 | 1958 | 4.6 | 19.3 | 56.7 | 10.8 / 26.1 |
| livespec-overseer master push | 38 | 373 | 2.6 | 27.9 | 116.0 | 6.2 / 33.2 |
| livespec-overseer pull_request | 67 | 659 | 4.9 | 33.1 | 124.3 | 12.4 / 66.8 |

- Master waits come in bursts during release-please and self-bump storms. Every dev-tooling master run from 23:30Z to 03:15Z waited 28–110 min, and every one from 08:13Z to 10:00Z waited 33–98 min. Overseer runs at 06:21, 06:22, 08:21 and 08:37Z waited 82–116 min.
- Master pushes are about a third of dev-tooling's self-hosted CI load: 107 pushes × ~9 jobs.
- The figures are biased low, because runs still queued at measurement time are not counted.

## Why nothing prioritises master today

1. Every gating job uses `runs-on: ${{ fromJSON(vars.CI_RUNNER_LABELS || '["ubuntu-latest"]') }}` (`.github/workflows/ci.yml`) for both `pull_request` and `push: [master]`. Each repo's variable names ONE scale set, so GitHub holds one assignment queue for both events.
2. ARC creates a runner pod before GitHub assigns it a job. The pod carries only repo, scale-set, `patch-id` and `runner-spec-hash` labels, so nothing at pod creation knows the triggering event.
3. `livespec-dev-tooling-k3s` sits at maxRunners 12 (`ci-runner/k3s/phase2/arc/values-livespec-dev-tooling.yaml`), live 12/12 with 6 pending. Further jobs wait on GitHub's side.
4. Kueue: `livespec-dev-tooling-cq` is BestEffortFIFO with all preemption `Never` and fairSharing weight 1. Every live workload has priority 0. The only WorkloadPriorityClass, `gate-priority`, orders gate Jobs inside `gates-cq` only.
5. The nominal floors sum to C = 44: orchestrator 29, dev-tooling 6, livespec 2, every other repo 1.

A WorkloadPriorityClass alone cannot fix this. It would only reorder pods already inside one ClusterQueue, which still sit behind the same GitHub queue and the same 12-runner ceiling. The event has to be chosen at `runs-on`.

## Ruled change (legacy-coordinator-agent, 2026-11-03 ~11:55Z)

- A dedicated master scale set `livespec-dev-tooling-master-k3s` (maxRunners 9), with a LocalQueue into a new `livespec-dev-tooling-master-cq` in cohort `fleet-ci-runner-pool`.
  - nominalQuota 3 is taken from dev-tooling's 6, which becomes 3. The sum stays 44.
  - `lendingLimit: 0` on the churn-slot resource. Reclaim is Never, so without it the idle master floor would be borrowed and never returned.
  - Preemption stays Never.
- ci.yml gating `runs-on` becomes `fromJSON(github.event_name == 'push' && vars.CI_RUNNER_LABELS_MASTER || vars.CI_RUNNER_LABELS || '["ubuntu-latest"]')`. It is inert until the variable is set.
- Order: converge the scale set and CQ, confirm the listener has registered, then set `CI_RUNNER_LABELS_MASTER`.
- The 6→3 floor trade is approved: a starved master blocks every dev-tooling dispatch through the master-CI preflight, and PRs still borrow above 3.
- The routing contract in `constraints.md` §"CI matrix shape" changes, so a propose-change and revise come first (topic `master-push-ci-routing`). DERIVATION.md gains a section for the quota move.
- Overseer follows the same pattern once dev-tooling proves it.
- Open question for the maintainer, NOT taken: a master `concurrency` group that cancels superseded master runs would shrink the bursts. It would also remove the per-commit verdicts the red-master reconciler uses to find a breaking commit, which is a gate reduction and so the maintainer's call.

Expected effect: a master run's first 3 jobs start as soon as a slot frees, cutting the 50–110 min tail to about one job's duration. Cost: up to 3 of 44 slots (7%) sit idle when no master run is queued.

## Reproduce

Run `python3 -I qtime.py <repo> <since-iso> [-v]` with the script below. It calls
`gh api --paginate 'repos/thewoolleyman/<repo>/actions/runs?event=push&branch=master&created=>=<since>&per_page=100'`
(and the same with `event=pull_request`, no branch filter), then
`gh api --paginate repos/thewoolleyman/<repo>/actions/runs/<id>/attempts/<n>/jobs?per_page=100`.

```python
"""Queue time of self-hosted jobs, master push vs pull_request, last 24h.

usage: python3 -I qtime.py <repo> <since-iso>
"""
import json, subprocess, sys
from datetime import datetime
from statistics import median

repo, since = sys.argv[1], sys.argv[2]

def gh(path):
    out = subprocess.run(["gh", "api", "--paginate", path], capture_output=True, text=True, check=True).stdout
    # paginate concatenates JSON objects
    dec, i, objs = json.JSONDecoder(), 0, []
    out = out.strip()
    while i < len(out):
        o, j = dec.raw_decode(out, i); objs.append(o); i = j
        while i < len(out) and out[i].isspace(): i += 1
    return objs

def ts(s): return datetime.fromisoformat(s.replace("Z", "+00:00"))

runs = []
for ev in ("push", "pull_request"):
    q = f"repos/thewoolleyman/{repo}/actions/runs?event={ev}&created=>={since}&per_page=100"
    if ev == "push": q += "&branch=master"
    for page in gh(q):
        runs += [r for r in page["workflow_runs"] if r["name"] == "CI"]

rows = {"push": [], "pull_request": []}
runq = {"push": [], "pull_request": []}
for r in runs:
    jobs = []
    for page in gh(f"repos/thewoolleyman/{repo}/actions/runs/{r['id']}/attempts/{r['run_attempt']}/jobs?per_page=100"):
        jobs += page["jobs"]
    sh = [j for j in jobs if any("k3s" in l for l in j["labels"]) and j["started_at"] and j["status"] == "completed" and j["conclusion"] != "skipped"]
    if not sh: continue
    w = [(ts(j["started_at"]) - ts(j["created_at"])).total_seconds() / 60 for j in sh]
    rows[r["event"]] += w
    runq[r["event"]].append((r["created_at"], r["head_branch"], len(sh), round(max(w), 1)))

def pct(xs, p):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]

for ev in rows:
    xs = rows[ev]
    if not xs: print(ev, "no jobs"); continue
    rq = [m for *_, m in runq[ev]]
    print(f"{repo} {ev}: runs={len(runq[ev])} jobs={len(xs)} job-queue-min median={median(xs):.1f} p90={pct(xs,.9):.1f} max={max(xs):.1f} | per-run worst-job-queue median={median(rq):.1f} p90={pct(rq,.9):.1f}")
if "-v" in sys.argv:
    for ev in runq:
        for row in sorted(runq[ev]): print(ev, *row)
```
