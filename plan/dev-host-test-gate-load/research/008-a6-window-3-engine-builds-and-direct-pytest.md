# 008 — A6 after-window 3 (1.82 cores, not met): engine builds through a stale primary pack, and a direct pytest

Recorded 2026-11-05 by seat dev-host-test-gate-load. This note follows note 007 (window 2, 1.10 cores, not met).

## Window 3

- **Window:** 2026-11-04 19:31:00Z to 23:57:06Z, 1560 intervals of 10 s, 4.33 hours. The unit was `vpsload-a6-after-3`.
  It started after the 19:08-19:22Z pack refresh of the 10 idle fleet primaries (note 007).
- **Method:** the same v3 sampler and summariser as notes 003, 006 and 007, byte-identical (`sha256sum -c` passed; see
  `data/008-a6-after-3/sampler-sha.txt`).
- **Data:** `data/008-a6-after-3/` holds the raw window (`.jsonl.gz`), the summariser output, the per-process
  decomposition and the script that produced it (`decompose3.py.txt`), a venue survey of every gate run started in the
  window across the fleet checkouts, and the gate runs behind the bursts.
- This seat's own load in the window was one spec-only commit gate (22:31-22:40Z) and its push (22:41Z), both
  `host_local` because neither is a full-suite command. Neither reaches 0.05 cores in any five-minute bucket.

| class | baseline (003) | window 1 (006) | window 2 (007) | window 3 |
|---|---|---|---|---|
| janitor-post-merge | 1.09 | 0.03 | 0.01 | 0.01 |
| commit-pre-commit-aggregate | 0.90 | 0.02 | 0.05 | 0.05 |
| adhoc-pytest-or-check | 0.49 | 0.18 | 0.42 | 0.59 |
| adhoc-gate-start | 0.12 | 0.73 | 0.54 | 1.11 |
| pre-push | 0.11 | 0.30 | 0.07 | 0.04 |
| commit-red-green-replay | 0.02 | 0.01 | 0.01 | 0.01 |
| **test/gate total** | **2.73** | **1.27** | **1.10** | **1.82** |

**Verdict: assertion 6 is NOT met by window 3.** Across 52 five-minute buckets the median is 0.79 cores and 31 buckets
are under one core. Outside the three bursts below, the other 35 buckets average 0.69 cores. Three bursts carry the
window over the bar.

1. **19:31Z to 19:57Z and 20:53Z to 21:34Z, adhoc-gate-start at 2.2 to 6.0 cores.** These are fabro engine Rust
   builds. `rustc`, `clippy-driver` and `rust-lld` inside test/gate classes average at least 0.56 cores over the whole
   window; the largest single process is `rustc --crate-name fabro` at 0.47. The gate runs behind them were started
   from the livespec-orchestrator-beads-fabro PRIMARY checkout: `engine-build-0a867.sh` (18:46-19:58Z),
   `engine-build-85af.sh` (20:51-21:18Z) and `rollout-0a867.sh` (21:42-22:15Z). All three records have no venue. That
   primary still runs the 2026-09-09 `gate-run.sh` (`41d8817e38b4`). It was the one primary note 007 could not refresh
   at 19:08Z, because it had live gates. The other 20 unrouted runs there are git commits, pushes and `gh` watchers.
2. **22:25Z to 22:45Z, adhoc-pytest-or-check at 4.2 to 6.6 cores.** These are pytest-xdist workers under
   `~/.worktrees/livespec-dev-tooling/feat/si6uu7-ci-job-attachment/.venv`. No gate-run record names that worktree after
   its 22:18-22:22Z commit gate, so this was a pytest started directly, not through `just gate-start`. Assertion 4's
   default-to-cluster routing therefore never saw it.

The routed primaries behaved as intended. In livespec-dev-tooling, 47 gate runs in the window were all `host_local`
with reason "command outside full-suite set": commits, pushes and watchers, which assertion 4 leaves on the host. One
orchestrator worktree full suite (`bd-ib-yuwftp`, 20:12-21:19Z) ran as a `cluster_job`. Its later re-runs were
`--local`, which assertion 4 permits as an explicit, recorded choice.

## What this says about the remaining work

- **The stale-primary-pack cause is still live and is now the largest single source.** It is the cause js3cum fixes:
  gate-start refreshes a stale pack before any gate runs, by rename. A by-hand refresh of the orchestrator primary
  remains possible only when no `gate-run.sh` runs from it. A fabro engine build is not a test suite, but by the unchanged
  method it counts in adhoc-gate-start. The class definition is not being changed mid-measurement. The plan-level A6
  proof needs either js3cum shipped, or engine builds routed elsewhere by their owning seat (fabro-currency).
- **A direct pytest outside the gate runner is a gap no current carrier closes.** Assertion 4 routes only runs started
  through the sanctioned gate runner. The agent-session gate-command guard (contracts.md §"Agent-session gate-command
  guard") refuses a foreground hook-running `git commit` or `git push`, and a bare-backgrounded `just check*`, `git` or
  `gh pr` command. It does not refuse a foreground `pytest`. A seat that runs `uv run pytest -n auto` directly in a worktree is invisible to both. Window 2 showed the
  same shape (the lhjjqm-triage pytest, 2.6 to 3.0 cores). This is recorded here as a finding. Whether it needs a
  carrier, such as extending the guard to full-suite pytest invocations, is reconsidered when the plan-level A6 proof
  is taken. It is not filed as a child now, because the ratified text does not yet require it and the coordinator rules
  on new fleet guards.

## Next

A fourth window is worth taking only after js3cum ships (or after the orchestrator primary is refreshed with no gate
running). It uses the same method.
