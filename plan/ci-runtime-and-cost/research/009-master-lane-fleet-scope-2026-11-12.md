# Master-push CI lanes: fleet scope (rule G)

Status: measured by the ci-runtime-and-cost seat on 2026-11-12 ~21:10Z. Context: handoff 69 on epic livespec-dev-tooling-ib3oe3. That handoff gives the orchestrator its own master lane through livespec-dev-tooling-7sqr36 (the scale set) and bd-ib-mexkuo (the ci.yml routing and the variable). Rule G asks the same of every other fleet member on k3s: a lane, or a measured reason it does not starve.

## Bottom line

**No other fleet repository needs a master lane now, but see the addendum: overseer starved right after this window because its runner listener was down, which a lane would not have prevented.** Within the measured window, none of the six showed master-push starvation. Over their last 16–20 master-push CI runs, the worst queue wait on a k3s job was 7.2–11.7 minutes. The orchestrator's master check-per-file-coverage shards waited 28–55 minutes on 2026-11-12.

The orchestrator starved for a reason the others do not share:

- **The competition is within one label, and every repo has its own label.** ARC hands a job to whichever runner registers on the job's label. The orchestrator's master shards waited behind its OWN pull-request coverage shards, because both read `CI_COVERAGE_RUNNER_LABELS=["livespec-orchestrator-k3s"]`. Each of the six repos below routes to a scale set of its own, so another repo's pull-request traffic cannot occupy its runners.
- **The orchestrator has more pull-request traffic, and each run asks for more.** It had 37 pull-request CI runs in the 24 h to 21:00Z, and each one asks for 4 coverage shards. The six repos had 5–23 runs each.

## Measurements

Master-push queue wait is `started_at − created_at` for each job of a master-push `ci.yml` run whose runner labels or runner name contain `k3s`. The script below takes the most recent master-push runs created from 2026-11-05 to 2026-11-12T21:10:00Z, the window these figures were measured in, and the API returned at most 20. An open-ended window does not reproduce them: by 2026-11-13 it already read overseer at a p95 of 27.5 and a max of 88.0 minutes (see the addendum).

| Repository | Scale-set label (CI_RUNNER_LABELS) | Master runs | k3s jobs | p50 (min) | p95 (min) | max (min) | Run window (UTC) | PR CI runs, 24 h |
|---|---|---|---|---|---|---|---|---|
| livespec | livespec-local-ci-k3s (coverage the same) | 20 | 198 | 0.4 | 3.1 | 8.0 | 11-11 09:37 → 11-12 21:07 | 20 |
| livespec-overseer | livespec-overseer-k3s | 20 | 200 | 0.4 | 3.6 | 7.5 | 11-11 00:22 → 11-12 10:17 | 23 |
| livespec-driver-claude | livespec-driver-claude-k3s | 20 | 239 | 1.0 | 4.8 | 7.8 | 11-09 17:06 → 11-12 13:26 | 9 |
| livespec-driver-codex | livespec-driver-codex-k3s | 20 | 280 | 1.1 | 5.7 | 8.9 | 11-10 00:52 → 11-12 13:27 | 9 |
| livespec-runtime | livespec-runtime-k3s | 20 | 200 | 0.6 | 5.3 | 7.2 | 11-10 23:00 → 11-12 13:26 | 5 |
| livespec-console-beads-fabro | livespec-console-beads-k3s | 16 | 272 | 3.0 | 10.6 | 11.7 | 11-09 22:25 → 11-12 13:18 | 5 |
| (orchestrator, for contrast) | coverage on livespec-orchestrator-k3s | — | — | — | — | 55 | 11-12 18:57 → 20:28 | 37 |

The orchestrator row comes from handoff 69: master CI 6f7b88531's four coverage shards queued 28–55 minutes. Master run c1bb7dbc9 then sat with no jobs for 1 h 24 m behind it, under B' concurrency.

livespec-console-beads-fabro waits longest of the six, with a p95 of 10.6 minutes. Its per-run worst waits are spread over the window, so they look like normal cold scale-up from `min-runners: 0`, not a backlog. It is the first repo to re-measure if this changes.

## Caveat: no sample overlaps the busiest window

No sampled master run of the six repos falls inside the orchestrator's 18:57–20:28Z window. livespec's master runs nearest it were created at 21:04Z and 21:07Z. So these figures do not show how the six behave under cluster-wide load. The no-lane conclusion rests on the per-repo labels and the pull-request volume above, not on load-tested queue figures.

Cluster-wide pressure is a different problem from master starvation. A shared Kueue ClusterQueue, or node CPU, can slow every set at once, and a master lane does not fix that. A lane only helps when a repo's master jobs wait behind that same repo's pull-request jobs on one label.

## When to revisit

Give a repository a master lane, using the 7sqr36 pattern, when either holds:

- its master-push k3s queue wait has a p95 above 15 minutes over 20 runs, measured with the method below; or
- it gains a separate coverage label shared by pull requests and master, with sharded coverage. That is the orchestrator's shape.

livespec is the nearest case. It already has `CI_COVERAGE_RUNNER_LABELS`, but that variable currently names the same set as `CI_RUNNER_LABELS`. If its coverage is ever split onto its own set, re-measure it.

## Reproduce

Queue waits per repository: run `python3 -I q.py <repo>` with this script.

```python
import json, subprocess, sys, time
from datetime import datetime
def gh(p):
    for a in range(4):
        r = subprocess.run(["gh", "api", p], capture_output=True, text=True)
        if r.returncode == 0:
            return json.loads(r.stdout)
        time.sleep(3 * (a + 1))
    raise SystemExit(f"gh api failed: {p}: {r.stderr[:200]}")
def t(s): return datetime.fromisoformat(s.replace("Z", "+00:00"))
repo = sys.argv[1]
runs = gh(f"repos/thewoolleyman/{repo}/actions/runs?branch=master&event=push&per_page=40&created=2026-11-05..2026-11-12T21:10:00Z")["workflow_runs"]
runs = [r for r in runs if r["path"].endswith("/ci.yml")]
qs = []
for r in runs[:25]:
    for j in gh(f"repos/thewoolleyman/{repo}/actions/runs/{r['id']}/jobs?per_page=100")["jobs"]:
        if not j.get("started_at") or not j.get("created_at"):
            continue
        if "k3s" not in " ".join(j.get("labels") or []) + " " + (j.get("runner_name") or ""):
            continue
        q = (t(j["started_at"]) - t(j["created_at"])).total_seconds() / 60
        if q >= 0:
            qs.append(q)
qs.sort()
pct = lambda p: round(qs[min(len(qs) - 1, int(p * len(qs)))], 1)
print(repo, len(qs), pct(.5), pct(.95), pct(1))
```

Labels: `gh variable list -R thewoolleyman/<repo>`.

Pull-request volume:

```sh
gh api "repos/thewoolleyman/<repo>/actions/runs?event=pull_request&per_page=100&created=>=2026-11-11T21:00:00Z" \
  -q '[.workflow_runs[]|select(.path|endswith("/ci.yml"))]|length'
```

## Addendum (2026-11-13): overseer starved, and a lane would not have helped

legacy-coordinator-agent's grade of livespec-dev-tooling#4392 found two livespec-overseer master-push runs just after the measured window that starved:

| Run | Created (UTC) | Worst k3s job wait | Next worst |
|---|---|---|---|
| 43307625796 | 2026-11-12 21:10:39 | 88.0 min (check-check-coverage-incremental, started 22:38:37) | 67.1, 64.8 |
| 43324225226 | 2026-11-12 22:54:48 | 44.6 min (check-red-green-replay, started 23:39:23) | 27.5 |

That puts overseer over this note's own re-measure trigger (a p95 above 15 minutes over 20 runs), so the trigger fired and overseer was re-measured.

**The finding: the wait was not overseer's own pull requests holding its runners, so a master lane would not have shortened it.** A lane only helps when master jobs queue behind the same repository's pull-request jobs on one label. Counting every overseer `ci.yml` k3s job (all 18 runs created 19:30–23:59Z, pull-request and push alike) by whether it had started or was still waiting:

| Instant (UTC) | overseer k3s jobs running | overseer k3s jobs waiting |
|---|---|---|
| 21:20 | 2 | 22 |
| 21:40 | 0 | 29 |
| 22:00 | 0 | 29 |
| 22:20 | 1 | 31 |

For about an hour, overseer's own scale set ran **zero to two** jobs while 22–31 waited. Its `maxRunners` is 6 (`ci-runner/k3s/phase2/arc/values-livespec-overseer.yaml`), so its own work was not filling it. The jobs were not being picked up at all. The 23:00Z and 23:20Z counts are left out: a job without `completed_at` counts as running there, and they read 24–25 against a cap of 6, so they are not trustworthy. The zeros above cannot be inflated that way.

**The measured cause was a listener outage, then designed saturation. Kueue was not short-changing overseer.** Two seats measured it on 2026-11-12, after this addendum's first draft guessed at "admission pressure":

- **From about 21:28 to 22:13Z, overseer had no ARC listener.** The gamingpc-xubuntu power-off left eight listeners Terminating with no replacement, `livespec-overseer-k3s` among them (livespec-dev-tooling-acgcwp; measured by homelab-k8s-worker-nodes). A scale set with no listener takes no jobs, whatever its quota. gate-job-resources saw the overseer listener's last CPU at about 21:28Z on gamingpc and its replacement's first on hp at about 22:12Z (Honeycomb query jz8wZ73C42B).
- **Kueue honoured overseer's floor the whole time.** That floor is a `nominalQuota` of 1 on churn-slot-flavor; 6 is `maxRunners`, the ceiling. overseer-cq's `livespec.ci_pool.queue_resource_usage` never fell below 1 (query 5mCebgFUxyv). The 3 slots it held during the outage were IDLE runners, at about 0.01 cpu with no workflow pod, because no listener existed to give them jobs (query w3PvJGCXuxt).
- **From 22:13 to 22:40Z the cohort was ordinarily saturated.** Admitted was 31–32 of 32 nominal, and cohort pending rose from about 1 to 65 at 22:20Z as the restored listeners released their backlog (query ju8JrNZLNna). dev-tooling-cq was borrowing up to 9 slots. With preemption and `reclaimWithinCohort` both `Never`, a borrowed slot returns only when its job ends, which is the designed behaviour.
- **The quota does not exceed capacity.** The live cohort sums to 31 on churn-slot-flavor, the same as the 31 amd64 churn slots measured at about 23:50Z (poweredge 17, gmktec 8, hp 5, gamingpc 1). The "C = 44" in the ClusterQueue file comments is stale prose.
- **The arm64 M4 cordon was irrelevant.** Its slot is in its own Kueue flavor, and overseer-cq has no quota there.

The same listener gap hit the orchestrator's listener, which explains part of its 28–55-minute coverage queue that evening: its queue usage fell from 15 to 3.

**Conclusion, amended:** still no master lane for overseer. A master lane would not have prevented this either, because its own listener can die the same way. The defence is listener placement and recovery, which livespec-dev-tooling-acgcwp owns. gate-job-resources also notes that a dead listener's admitted runners keep their quota, so an outage strands cohort slots for every queue, not just the dead set's. That finding belongs with acgcwp too.

Reproduce the instant counts by listing `repos/thewoolleyman/livespec-overseer/actions/runs?per_page=100&created=2026-11-12T19:30:00Z..2026-11-12T23:59:00Z` (`ci.yml` only), then the jobs of each run. For each k3s job, count it as running at instant T when `started_at <= T < completed_at`, and as waiting when `created_at <= T < started_at`.
