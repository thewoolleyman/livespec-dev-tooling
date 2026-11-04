# 007 — A6 after-window 2 (1.10 cores, not met) and the stale primary packs behind it

Recorded 2026-11-04 by seat dev-host-test-gate-load. This note follows note 006, the first A6 after-window (1.27 cores, not
met).

## Window 2

- **Window:** 2026-11-04 14:24:49Z to 18:56:57Z, 1560 intervals of 10 s, 4.33 hours. The unit was `vpsload-a6-after-2`.
- **Method:** the same v3 sampler and summariser as notes 003 and 006, byte-identical (`sha256sum -c` passed; see
  `data/007-a6-after-2/sampler-sha.txt`).
- **Data:** `data/007-a6-after-2/` holds the raw window (`.jsonl.gz`), the summariser output, the decomposition and the window
  notes. The notes list the k3s-side converges and churn-slot re-stamps of that afternoon. They also list a 15:57Z dev-host
  overload: load 137, idle 9%, sys 50%. Its largest reducible source was 39 petri dispatch launchers, which this seat reported
  to legacy-coordinator-agent at 16:1xZ.
- This seat ran no test or gate load on the dev host during the window.

| class | baseline (003) | window 1 (006) | window 2 |
|---|---|---|---|
| janitor-post-merge | 1.09 | 0.03 | 0.01 |
| commit-pre-commit-aggregate | 0.90 | 0.02 | 0.05 |
| adhoc-pytest-or-check | 0.49 | 0.18 | 0.42 |
| adhoc-gate-start | 0.12 | 0.73 | 0.54 |
| pre-push | 0.11 | 0.30 | 0.07 |
| commit-red-green-replay | 0.02 | 0.01 | 0.01 |
| **test/gate total** | **2.73** | **1.27** | **1.10** |

**Verdict: assertion 6 is NOT met by window 2.** Across 52 five-minute buckets, the median is 0.85 cores and 29 buckets are
under one core. Two bursts carry it over the bar:

1. **14:24Z to 14:35Z, adhoc-pytest-or-check at about 2.6 to 3.0 cores.** A local pytest ran in
   `~/.worktrees/livespec-overseer/lhjjqm-triage`.
2. **17:10Z to 18:46Z, adhoc-gate-start at 1 to 2 cores.** These are gate runs started from the livespec-orchestrator-beads-fabro
   PRIMARY checkout. They include `dmjsmd/gate.sh` (17:09Z to 18:31Z), fabro engine Rust builds (`engine-build-0a867.sh` from
   18:46Z, and `rustc`/`clippy-driver` at least 0.25 cores over the window), and several commit and push wrappers. Every one of
   those gate-run records has an empty `venue` and `venue_reason`.

## The cause: a primary checkout's worktree pack never refreshes

`just gate-start` runs `./dev-tooling/gate-run.sh`, the gitignored worktree pack. Only `just bootstrap` and the commit/push hooks'
`00-install-worktree-pack` install that pack. A primary checkout never commits (no-commit-on-master), so its pack freezes at its
last bootstrap.

The survey at 19:05Z is `data/007-a6-after-2/primary-gate-run-survey-1905Z.txt`. 11 of 13 fleet primaries ran a `gate-run.sh`
with no venue routing, that is 0 occurrences of `venue`. For example, the orchestrator primary pins livespec-dev-tooling v1.172.0,
whose pack `gate-run.sh` is `f16d03464a8b` (16 references). It ran its 2026-09-09 copy, `41d8817e38b4`. Every `gate-start` there
ran on the dev host, including full-suite commands that assertion 4 says run as gate Jobs. This is also most of window 1's
`adhoc-gate-start` class: those were the same primary's engine builds and gate scripts (note 006).

The installer (`install_worktree_pack.py`, `path.write_text`) rewrites each file in place, on the same inode. bash reads a running
script incrementally, so refreshing `gate-run.sh` under a live gate can corrupt that gate.

## What was done

- **Interim refresh**, authorized by legacy-coordinator-agent R493 at 19:1xZ as reversible (gitignored copies of each pinned
  package's pack). `just install-worktree-pack` ran in the 10 primaries with no gate running, 19:08Z to 19:22Z. The before and
  after sha of every pack file is in `data/007-a6-after-2/primary-pack-refresh-1908Z-1922Z.log`.
  - Six now carry venue routing: dolt-server (13 references, at its v1.153.0 pin), livespec, livespec-driver-claude,
    livespec-driver-pi, livespec-orchestrator-git-jsonl and livespec-overseer (16 each).
  - Four do not, because their pinned package predates venue routing: hetzner-xubuntu-info (v1.143.2),
    livespec-console-beads-fabro (v1.143.1), livespec-runtime (v1.134.2) and livespec-tdd-proof (v1.96.1).
  - The orchestrator primary had live gates, which the in-place write could corrupt. A detached waiter refreshes it once no
    gate-run.sh process runs from it. Its result is recorded on the plan epic.
- **Durable fix filed: livespec-dev-tooling-js3cum.** `gate-start` refreshes a stale pack from the installed package before any
  gate runs, and the refresh writes by rename. js3cum carries assertion 4 in the carrier-map scope event of 2026-11-04 ~19:30Z.
  The pin bumps for the four old-pin repos are an explicit deferral in that event.

## Next

- **Window 3 is running.** The unit is `vpsload-a6-after-3`, started 2026-11-04 19:30:58Z, after the refresh of the 10 idle primaries. It ends about 23:51Z.


A third A6 window, measured after the refresh, will show what the refresh removed. The plan-level proof for assertion 6 waits
for a window under one core by the unchanged method, preferably after js3cum ships.
