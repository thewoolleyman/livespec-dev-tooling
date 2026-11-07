# 007: landed-lever re-read, a second assertion-2 window, lever 4, and the uv-seed sample — 2026-11-06

Measured by the ci-cache-optimization seat after the three carriers of plan assertion 1 closed (bd-ib-uuatg4,
bd-ib-rpit5z, bd-ib-vnmph2). This note is evidence for the plan-level Proof of Done capture of assertions 1, 2 and 5. It
does not replace that capture. Every figure comes from read-only GitHub API reads, and each section names the script and
arguments that reproduce it. All three scripts appear in full at the end of this note.

The epic comments on livespec-dev-tooling-7zozck at 2026-11-06T02:39Z ("plan-measurement ... landed-lever re-read") and
08:37Z ("plan-measurement ... lever 4") first recorded the lever figures. Commits were held under the R301 load freeze,
so the figures waited there. The second assertion-2 window and the second lever window are new in this note.

## How assertion 5 is read

Assertion 5 compares "the median duration of the jobs it targets" against "the baseline recorded in this plan's
research". The baselines research 002 recorded are STEP durations: the orchestrator `Prepare non-root leg` step at
120-130 s (ci-runtime-and-cost's 40-run figure, matching research 002's p90 of 146 s), and `Set up job` at 2 s median /
4 s p90. Whole-job durations were never baselined. They also move with changes that are not cache levers, such as the
coverage sharding that landed between the lever 4 windows below. So this note compares each lever's targeted STEP
against that step's recorded baseline. The completeness review can confirm or reject this reading.

## Levers 1 and 5 — two windows

Script: `landed_lever_steps.py <SINCE> <UNTIL> 25`. Completed runs in the window, for all ten fleet repositories. The
orchestrator is read in full, and every other repository is a `random.Random(1)` sample of 25 runs. Jobs come from
`jobs?filter=latest`, keeping only k3s jobs (runner name contains `-k3s-`). Skipped jobs and skipped steps are excluded.

| Window (UTC) | Lever | Step | n (steps) | median | p90 | max | Baseline (research 002) |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 2026-11-05T14:00Z..11-06T02:30Z | 1 nonroot prep | `Prepare non-root leg (open baked toolchain to uid 1000)` | 427 | 1 s | 2 s | 22 s | 120-130 s |
| 2026-11-05T14:00Z..11-06T02:30Z | 5 action archive cache | `Set up job`, all repos | 1,058 | 1 s | 2 s | 61 s | 2 s / 4 s |
| 2026-11-06T02:30Z..11-06T22:30Z | 1 nonroot prep | same | 823 | 1 s | 2 s | 5 s | 120-130 s |
| 2026-11-06T02:30Z..11-06T22:30Z | 5 action archive cache | same | 1,423 | 1 s | 2 s | 12 s | 2 s / 4 s |

Runs in the first window, total / read: orchestrator 173 / 173, livespec 168 / 25, dev-tooling 266 / 25, driver-claude
39 / 25, driver-codex 43 / 25, overseer 78 / 25, driver-pi 39 / 25, orchestrator-git-jsonl 39 / 25. Runtime and console
had no runs in the window.
In the second window: orchestrator 380 / 380, livespec 248 / 25, dev-tooling 525 / 25, driver-claude 59 / 25,
driver-codex 56 / 25, overseer 59 / 25, runtime 3 / 3, driver-pi 59 / 25, console 8 / 8, orchestrator-git-jsonl
59 / 25. This second window starts where the first one ends, so the two windows do not overlap.

Reproduction check. The 02:39Z comment reported lever 5 at n=1,067. This script, re-run over that window on 2026-11-06
~22:5xZ, gives n=1,058 with the same median, p90 and max. The original script was lost with its session scratchpad, and
it did not record the order it sampled repositories in, so its 25-run samples cannot be redrawn exactly. Lever 1 reads
the orchestrator in full and reproduces exactly.

Assertion 1, timing clause: met in both windows (median 1 s against the 15 s ceiling). The code clauses were read on
orchestrator master 6b1cd6d4 (2026-11-06T02:19:43Z). All five nonroot prepare steps use the targeted
`find ... -exec chown -h 1000:1000` passes and no `chown -R`, and each one sets `NONROOT_UV_CACHE_DIR` to the warm seed
`/__w/_warm/uv`. If the seed is unusable, the step falls back to `/home/ci/.cache/uv` and emits a `::warning::`. The
section on the uv seed below samples that fallback.

Assertion 5: levers 1 and 5 each have far more than 20 steps below baseline in both windows.

## Assertion 2 — a second 6-hour window

Script: `setup_job_failures.py <SINCE> <UNTIL>`. This is research 006's query written as a script. Every run created in
the window, for all ten fleet repositories, with `jobs?filter=all`, keeping jobs that started inside the window. A
failure counts when the first failed step is `Set up job`, and each such job's log is read for `codeload` and `429`.

| Window (UTC) | Runs | Job attempts | of which `-k3s-` | Set up job failures | codeload / 429 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-11-04T11:38:19Z..17:38:19Z (research 006) | 467 | 2,472 | 1,623 | 0 | 0 |
| 2026-11-06T17:00:00Z..23:00:00Z | 508 | 3,032 | 1,498 | 0 | 0 |

The second window was read on 2026-11-07 ~00:0xZ, two days after the first. Baseline (2026-11-03, 6 h): 10 Set up job
failures in 4,359 job attempts, all of them codeload downloads of `actions/checkout`, 9 of them HTTP 429.

## Lever 4 — the nonroot warm uv seed (bd-ib-rpit5z, closed 2026-11-05T11:12:38Z)

Finding 1: lever 4's measured target is no longer on k3s. Research 002 measured lever 4 as "+30 s nonroot minus root on
batched python checks". Since 2026-11-04T17:41:18Z the orchestrator repository variable `CI_RUNNER_LABELS` has been
`["ubuntu-latest"]`. Only `CI_COVERAGE_RUNNER_LABELS` is `["livespec-orchestrator-k3s"]`. So `check-python-batch`,
`check-types`, `check-lint` and `check-format` now run on GitHub-hosted runners. That holds for the nonroot `ci.yml` legs
and, from the 2026-11-05 runs on, for the root jobs of the scheduled `ci-root-uid.yml`. Hosted runners have no pod warm
seed. The k3s job-hours that lever 4 targeted were removed by moving those jobs to hosted runners, not by the seed.

Finding 2: on the k3s nonroot jobs that remain, the coverage legs, the seed is live and the fallback never fired.

| Window (UTC) | Runs in window / sampled | k3s nonroot jobs | on `/__w/_warm/uv` | fallback warnings | cache init failures | jobs with uv network lines |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| post: 2026-11-05T10:15Z..11-06T08:30Z | 134 / 20 | 113 (65 pull_request, 48 push) | 113 | 0 | 0 | 0 |
| pre: 2026-11-04T17:45Z..11-05T10:10Z | 140 / 20 | 66 | 0 (private `/home/ci/.cache/uv`) | 0 | 0 | 0 (62 with a uid-1000 step) |

Script: `uvseed_sample.py <SINCE> <UNTIL> 20`. Completed orchestrator `ci.yml` runs of every event type, a
`random.seed(1)` sample of 20, `jobs?filter=latest`, keeping nonroot jobs on a `-k3s-` runner. Each job log is counted
for the `NONROOT_UV_CACHE_DIR` value, `##[warning]bd-ib-rpit5z` fallbacks, `Failed to initialize cache`, and uv network
lines after `##[group]Run setpriv --reuid=1000`. These are the same counts as rpit5z's host record
(livespec-orchestrator-beads-fabro#4453, comment 6656174426).

The one failed job in the post window was job 127558388526 (PR run 42113087029, `check-per-file-coverage`). It was
refused for per-file coverage (`test_gap_closure.py` at 98.9%), not for anything in the cache. The four pre-window jobs
with no uid-1000 step all came from one failed PR run, 42002447287.

Finding 3: the seed has no duration saving to attribute on k3s. Before rpit5z, the k3s nonroot coverage legs already
pulled nothing from the network as uid 1000 (0 network lines in 62 jobs), so the seed had no download to remove there.
The medians of the `just ... (uid 1000)` step did move. `check-per-file-coverage` (nonroot) went from 2,132 s to 47 s,
and the shards went from 795.5 s (n=24) to 584 s (n=76). Both changes come from coverage sharding, which landed between
the two windows. They are not lever 4's doing and must not be credited to it.

Seat decision, recorded on the epic at 08:37Z and open to objection at the completeness review: assertion 5 is recorded
for lever 4 as "target relocated off the pool; seed verified live on the remaining k3s nonroot legs (113/113, 0
fallbacks); no k3s duration saving is attributable". Lever 4 needs no further carrier. The Definition of Done is not
edited: the "jobs it targets" in assertion 5 are no longer pool jobs.

## What this leaves for the plan-level capture

- Assertion 1: re-run `landed_lever_steps.py` and `uvseed_sample.py` over a window ending at capture time against the
  released orchestrator build, and re-read the five prepare steps on that build's `ci.yml`.
- Assertion 2: two 6 h windows read 0 Set up job failures (research 006, and the section above). The capture re-runs
  `setup_job_failures.py` over a window ending at capture time.
- Assertion 5: levers 1 and 5 as above. Lever 4 per the seat decision. Lever 2 (dciyg5 and qyrmwe) and lever 6b (n622ze
  and rpdowy) still have to land and collect 20 runs each.

## Scripts

All three scripts are read-only. They call only `gh api --cache 6h`, and they write nothing to GitHub or the ledger.

### `landed_lever_steps.py`

```python
"""Read-only: step durations for the landed CI cache levers on k3s runners.

Method (ci-cache-optimization research 007, rewriting the 2026-11-06T02:39Z read):
- per fleet repository, page completed runs created in [SINCE, UNTIL];
  the orchestrator is read in full, every other repository is a random.seed(1)
  sample of PER_REPO runs (sampled in REPOS order, one shared RNG);
- per run, jobs?filter=latest; keep jobs whose runner_name contains '-k3s-'
  and whose conclusion is not skipped; drop skipped steps;
- step duration = completed_at - started_at, in whole seconds.

Lever 1: orchestrator step 'Prepare non-root leg (open baked toolchain to uid 1000)'.
Lever 5: 'Set up job', every repository.

Usage: python3 -I landed_lever_steps.py <SINCE> <UNTIL> [PER_REPO=25]
"""
import json
import random
import statistics
import subprocess
import sys
from datetime import datetime

OWNER = "thewoolleyman"
FULL = "livespec-orchestrator-beads-fabro"
REPOS = [
    "livespec", "livespec-dev-tooling", FULL, "livespec-driver-claude",
    "livespec-driver-codex", "livespec-overseer", "livespec-runtime",
    "livespec-driver-pi", "livespec-console-beads-fabro",
    "livespec-orchestrator-git-jsonl",
]
STEPS = {
    "lever1": (FULL, "Prepare non-root leg (open baked toolchain to uid 1000)"),
    "lever5": (None, "Set up job"),
}
SINCE, UNTIL = sys.argv[1], sys.argv[2]
PER_REPO = int(sys.argv[3]) if len(sys.argv) > 3 else 25


def gh(path):
    out = subprocess.run(["gh", "api", "--cache", "6h", path], capture_output=True, text=True)
    return json.loads(out.stdout) if out.returncode == 0 else None


def ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def runs_of(repo):
    runs, page = [], 1
    while page <= 30:  # bounded: at most 3,000 runs per repository
        d = gh(f"repos/{OWNER}/{repo}/actions/runs?created={SINCE}..{UNTIL}"
               f"&status=completed&per_page=100&page={page}")
        if not d or not d["workflow_runs"]:
            break
        runs += d["workflow_runs"]
        page += 1
    return runs


def jobs_of(repo, run_id):
    jobs, page = [], 1
    while page <= 10:
        d = gh(f"repos/{OWNER}/{repo}/actions/runs/{run_id}/jobs?filter=latest"
               f"&per_page=100&page={page}")
        if not d or not d["jobs"]:
            break
        jobs += d["jobs"]
        page += 1
    return jobs


rng = random.Random(1)
durations = {key: [] for key in STEPS}
read = {}
for repo in REPOS:
    runs = runs_of(repo)
    chosen = runs if repo == FULL else rng.sample(runs, min(PER_REPO, len(runs)))
    read[repo] = (len(runs), len(chosen))
    for run in chosen:
        for job in jobs_of(repo, run["id"]):
            if "-k3s-" not in (job.get("runner_name") or "") or job["conclusion"] == "skipped":
                continue
            for step in job.get("steps") or []:
                if step.get("conclusion") in (None, "skipped") or not step.get("completed_at"):
                    continue
                for key, (only_repo, name) in STEPS.items():
                    if step["name"] == name and (only_repo is None or only_repo == repo):
                        secs = (ts(step["completed_at"]) - ts(step["started_at"])).total_seconds()
                        durations[key].append(int(secs))

print(f"window {SINCE}..{UNTIL}; runs in window / read per repository:")
for repo, (total, chosen) in read.items():
    print(f"  {repo}: {total} / {chosen}")
for key, (_, name) in STEPS.items():
    d = sorted(durations[key])
    if not d:
        print(f"{key} '{name}': n=0")
        continue
    p90 = d[int(0.9 * (len(d) - 1))]
    print(f"{key} '{name}': n={len(d)} median={statistics.median(d)}s p90={p90}s max={d[-1]}s")
```

### `uvseed_sample.py`

```python
"""Read-only sample: does the k3s nonroot leg use the warm uv seed, post bd-ib-rpit5z?

Method (same counts as rpit5z's host record on livespec-orchestrator-beads-fabro#4453):
- completed ci.yml runs created in [SINCE, UNTIL], all events; random.seed(1) sample of N.
- per run, jobs?filter=latest; keep nonroot jobs whose runner_name contains '-k3s-' and conclusion != skipped.
- per job log: NONROOT_UV_CACHE_DIR value(s), '##[warning]bd-ib-rpit5z' fallback count,
  'Failed to initialize cache' count, and uv network lines after the first
  '##[group]Run setpriv --reuid=1000' ('Downloading ', 'Downloaded ', 'Prepared <n> package',
  files.pythonhosted.org).
"""
import json, random, re, subprocess, sys
from collections import Counter

REPO = "thewoolleyman/livespec-orchestrator-beads-fabro"
SINCE, UNTIL, N = sys.argv[1], sys.argv[2], int(sys.argv[3])


def gh(path, raw=False):
    out = subprocess.run(["gh", "api", "--cache", "6h", path], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return out.stdout if raw else json.loads(out.stdout)


runs = []
page = 1
while page <= 20:  # bounded: at most 2,000 runs
    d = gh(f"repos/{REPO}/actions/workflows/ci.yml/runs?created={SINCE}..{UNTIL}&status=completed&per_page=100&page={page}")
    if not d or not d["workflow_runs"]:
        break
    runs += d["workflow_runs"]
    page += 1
random.seed(1)
sample = random.sample(runs, min(N, len(runs)))
print(f"runs in window: {len(runs)}; sampled: {len(sample)}")

NET = re.compile(r"(Downloading |Downloaded |Prepared \d+ package|files\.pythonhosted\.org)")
rows, tot, durs, nets = [], Counter(), {}, {}
for r in sample:
    jobs = gh(f"repos/{REPO}/actions/runs/{r['id']}/jobs?filter=latest&per_page=100") or {"jobs": []}
    for j in jobs["jobs"]:
        if "nonroot" not in j["name"] or "-k3s-" not in (j.get("runner_name") or ""):
            continue
        if j["conclusion"] in (None, "skipped", "cancelled"):
            continue
        log = gh(f"repos/{REPO}/actions/jobs/{j['id']}/logs", raw=True)
        if log is None:
            tot["log_unavailable"] += 1
            continue
        dirs = sorted(set(re.findall(r"NONROOT_UV_CACHE_DIR:\s*(\S+)", log)))
        warn = log.count("##[warning]bd-ib-rpit5z")
        initf = log.count("Failed to initialize cache")
        i = log.find("##[group]Run setpriv --reuid=1000")
        net = len(NET.findall(log[i:])) if i >= 0 else -1
        st = [x for x in j.get("steps", []) if x["name"].startswith("just ") and "uid 1000" in x["name"] and x.get("conclusion") not in (None, "skipped")]
        from datetime import datetime
        f = lambda t: datetime.fromisoformat(t.replace("Z", "+00:00"))
        dur = int((f(st[0]["completed_at"]) - f(st[0]["started_at"])).total_seconds()) if st and st[0].get("completed_at") else -1
        kind = re.sub(r", \d/4", "", j["name"])
        durs.setdefault(kind, []).append(dur)
        nets.setdefault(kind, []).append(net)
        tot["jobs"] += 1
        tot["seed"] += dirs == ["/__w/_warm/uv"]
        tot["fallback_jobs"] += warn > 0
        tot["init_fail_jobs"] += initf > 0
        tot["net_jobs"] += net > 0
        tot["no_uid1000_step"] += net < 0
        tot[f"conclusion_{j['conclusion']}"] += 1
        rows.append((r["id"], r["event"], j["id"], j["name"], j["conclusion"], ",".join(dirs) or "-", warn, initf, net))

for row in rows:
    print(" | ".join(map(str, row)))
print(json.dumps(tot, sort_keys=True))
import statistics as S
for k in sorted(durs):
    d = sorted(x for x in durs[k] if x >= 0); n = nets[k]
    print(f"{k}: n={len(d)} uid1000-step median={S.median(d)}s p90={d[int(0.9*(len(d)-1))]}s | uv-net-lines median={S.median(n)} max={max(n)} jobs-with-net={sum(1 for x in n if x>0)}")
```

### `setup_job_failures.py`

```python
"""Read-only: plan assertion 2 — Set up job failures on a codeload action download.

Method (research 006's query, as a script):
- per fleet repository, page every run created in [SINCE, UNTIL] (all statuses);
- per run, page jobs?filter=all and keep jobs with SINCE <= started_at < UNTIL;
- a Set up job failure is a job with conclusion == failure whose first failed step is 'Set up job';
- for each one, fetch its log and count 'codeload' and '429' lines;
- a runner name containing '-k3s-' marks an ARC runner.

Usage: python3 -I setup_job_failures.py <SINCE> <UNTIL>
"""
import json
import subprocess
import sys

OWNER = "thewoolleyman"
REPOS = [
    "livespec", "livespec-dev-tooling", "livespec-orchestrator-beads-fabro",
    "livespec-driver-claude", "livespec-driver-codex", "livespec-overseer",
    "livespec-runtime", "livespec-driver-pi", "livespec-console-beads-fabro",
    "livespec-orchestrator-git-jsonl",
]
SINCE, UNTIL = sys.argv[1], sys.argv[2]


def gh(path, raw=False):
    out = subprocess.run(["gh", "api", "--cache", "6h", path], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return out.stdout if raw else json.loads(out.stdout)


def paged(path, key, limit):
    items, page = [], 1
    while page <= limit:
        d = gh(f"{path}&per_page=100&page={page}")
        if not d or not d[key]:
            break
        items += d[key]
        page += 1
    return items


totals = {"runs": 0, "jobs": 0, "k3s_jobs": 0, "setup_failures": 0, "codeload": 0, "http_429": 0}
failures = []
for repo in REPOS:
    runs = paged(f"repos/{OWNER}/{repo}/actions/runs?created={SINCE}..{UNTIL}", "workflow_runs", 30)
    totals["runs"] += len(runs)
    for run in runs:
        for job in paged(f"repos/{OWNER}/{repo}/actions/runs/{run['id']}/jobs?filter=all", "jobs", 10):
            started = job.get("started_at") or ""
            if not (SINCE <= started < UNTIL):
                continue
            totals["jobs"] += 1
            k3s = "-k3s-" in (job.get("runner_name") or "")
            totals["k3s_jobs"] += k3s
            if job.get("conclusion") != "failure":
                continue
            failed = [s for s in job.get("steps") or [] if s.get("conclusion") == "failure"]
            if not failed or failed[0]["name"] != "Set up job":
                continue
            totals["setup_failures"] += 1
            log = gh(f"repos/{OWNER}/{repo}/actions/jobs/{job['id']}/logs", raw=True) or ""
            codeload = sum("codeload" in line for line in log.splitlines())
            h429 = sum("429" in line for line in log.splitlines())
            totals["codeload"] += codeload > 0
            totals["http_429"] += h429 > 0
            failures.append((repo, run["id"], job["id"], job.get("runner_name"), k3s, codeload, h429))

print(f"window {SINCE}..{UNTIL}")
print(json.dumps(totals, sort_keys=True))
for row in failures:
    print(" | ".join(map(str, row)))
```
