# Master-push CI lanes: fleet scope (rule G)

Status: measured by the ci-runtime-and-cost seat on 2026-11-12 ~21:10Z. Context: handoff 69 on epic livespec-dev-tooling-ib3oe3. That handoff gives the orchestrator its own master lane through livespec-dev-tooling-7sqr36 (the scale set) and bd-ib-mexkuo (the ci.yml routing and the variable). Rule G asks the same of every other fleet member on k3s: a lane, or a measured reason it does not starve.

## Bottom line

**No other fleet repository needs a master lane now.** None of the six showed master-push starvation. Over their last 16–20 master-push CI runs, the worst queue wait on a k3s job was 7.2–11.7 minutes. The orchestrator's master check-per-file-coverage shards waited 28–55 minutes on 2026-11-12.

The orchestrator starved for a reason the others do not share:

- **The competition is within one label, and every repo has its own label.** ARC hands a job to whichever runner registers on the job's label. The orchestrator's master shards waited behind its OWN pull-request coverage shards, because both read `CI_COVERAGE_RUNNER_LABELS=["livespec-orchestrator-k3s"]`. Each of the six repos below routes to a scale set of its own, so another repo's pull-request traffic cannot occupy its runners.
- **The orchestrator has more pull-request traffic, and each run asks for more.** It had 37 pull-request CI runs in the 24 h to 21:00Z, and each one asks for 4 coverage shards. The six repos had 5–23 runs each.

## Measurements

Master-push queue wait is `started_at − created_at` for each job of a master-push `ci.yml` run whose runner labels or runner name contain `k3s`. The script below takes the most recent master-push runs created on or after 2026-11-05, and the API returned at most 20.

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
runs = gh(f"repos/thewoolleyman/{repo}/actions/runs?branch=master&event=push&per_page=40&created=>=2026-11-05")["workflow_runs"]
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
