# 004: lever 2 measured — where checkout time goes (2026-11-03)

Measured read-only on 2026-11-03, 21:05-21:25Z, by the ci-cache-optimization seat (resumed after handoff 5). Nothing on
any host, cluster or ledger was changed. This note refines row 2 of research 002 before any proposal is written.

## Method (reproducible)

- Runs: completed runs created since 2026-11-03T12:00Z, newest 100 per repository, from
  `gh api "repos/thewoolleyman/<repo>/actions/runs?status=completed&created=>=2026-11-03T12:00:00Z&per_page=100"`, for
  livespec-dev-tooling, livespec-orchestrator-beads-fabro, livespec and livespec-overseer.
- Sample: `random.seed(1)`; per repository 6 `CI` runs plus 4 runs of other workflows; per run up to 3 jobs that ran on
  k3s (no `ubuntu-*` label, not skipped) and carry a checkout step. 72 jobs, 74 `actions/checkout` steps, started
  15:32Z-20:47Z. Script: `fetch.py`, run from the session scratchpad.
- Phases come from each job's timestamped log (`gh api repos/thewoolleyman/<repo>/actions/jobs/<id>/logs`). Inside the
  step, `##[group]` boundaries split it into: the fleet hook start (`Run '/home/runner/fleet-hook/index.js'`), git init
  and auth setup, `Fetching the repository`, and `Checking out the ref`. `Post Checkout` comes from the job's `steps[]`.
  Script: `parse.py`, run from the session scratchpad.

## Result

Sample total for `Checkout` + `Post Checkout`: 808 s over 74 steps.

| Phase | Sum (s) | Share | Median / p90 (s) | Can a node-local git cache remove it? |
|---|---:|---:|---|---|
| `Fetching the repository` | 451 | 56% | 3.7 / 15.9 | yes, most of it |
| `Post Checkout` (credential cleanup) | 135 | 17% | 2 / — | no |
| fleet hook start inside the step | 111 | 14% | 1.3 / 2.7 | no |
| `Checking out the ref` (writing the work tree) | 65 | 8% | 0.7 / 1.4 | no |
| git init, auth, config | 30 | 4% | 0.4 / 0.7 | no |

- The fetch is the lever, and it is a TAIL. 13 of 74 fetches took over 10 s, and those 13 carry 50% of all fetch time.
  The slowest were `check-red-green-replay` (29, 27, 24, 16 s) and `check-metadata-batch` (20, 12 s).
- Full-history jobs (`fetch-depth: 0`, 29 of 74) have a fetch median of 5.3 s and p90 of 23.9 s. Their refspec pulls
  every branch and tag: orchestrator has 775 branches and 812 tags, dev-tooling 146 and 660, overseer 140 and 531.
- Shallow jobs (`--depth=1`, 45 of 74) have a fetch median of 2.3 s, yet 7 of them took over 10 s (one dev-tooling
  `check-types` single-commit fetch took 17.4 s). A depth-1 fetch transfers the whole tree of one commit, so a slow one
  is pack transfer and pack indexing under load, not history size.
- Applied to research 002's normalized ≈53 h/wk for this row: the fetch is a ceiling of about 30 h/wk. If a local
  object source brought every fetch down to about 1 s, the saving is about (451 - 74) / 808 = 47%, about **25 h/wk**.
  That confirms 002's estimate, and it is still an estimate until a node benchmark replaces the 1 s assumption.

## What this changes in the design

Research 002 named the realization as a host-served mirror reached through `url.<mirror>.insteadOf`. The numbers
point at a different shape, and a node benchmark has to decide between them before the proposal is written:

- **A redirected mirror** still has to serve every new PR merge ref, so it must fetch from GitHub on demand. It also
  still builds a pack per job, which is part of the cost even on a local link.
- **A reference object store** (`.git/objects/info/alternates` pointing at a node-held bare clone, refreshed on a timer)
  keeps GitHub as the remote, so freshness is never a question. Only the objects the store lacks cross the network,
  and no pack is built for objects already present.

A first microbenchmark on the dev host (vmi3006760) could not settle it. The host was at load 116 with 1.6% idle CPU
during the runs, and the same command varied 3× between repeats (for example a full fetch from GitHub took 31.9, 14.6
and 16.6 s). The one clean pass, before the load rose, gave: GitHub depth-1 4.6-7.0 s, local `file://` mirror depth-1
6.5 s, local mirror full 11.5 s against GitHub full 11.3 s, and GitHub with alternates 2.3 s (depth 1) and 1.9 s (full).
That pass suggests the cost is pack generation and indexing rather than the network, which would favor the reference
store, but one pass on a saturated host is not evidence. The benchmark must run on a ci-cache node (poweredge or gmktec)
and from runner-only hp over the node network, with the four modes: GitHub, local mirror, GitHub with alternates, each
at depth 1 and full.

## Not carried by lever 2

- `Post Checkout` and the fleet hook start are 31% of checkout time and are not cache levers. The hook start (median
  1.3 s per checkout step) is a Node process launch. If it runs once per action step, it may be a lever of its own;
  that needs a count of hook launches per job before anything is filed.
- Narrowing the `fetch-depth: 0` refspec (fetching only base and head instead of every branch and tag) would cut the
  worst tail with no cache at all. That is a workflow change in each repository, not a cache tier. It is recorded here
  as a candidate, to be ranked against lever 2 once the node benchmark exists.
