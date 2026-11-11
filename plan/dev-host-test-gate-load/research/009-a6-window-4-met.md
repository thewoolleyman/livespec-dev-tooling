# 009 — A6 after-window 4: 0.71 cores, under the one-core bar

Recorded 2026-11-11 by seat dev-host-test-gate-load. This note follows note 008 (window 3, 1.82 cores, not met).

## Window 4

- **Window:** 2026-11-10 20:52:04Z to 2026-11-11 01:18:51Z, 1560 intervals of 10 s, 4.33 hours. The unit was the
  transient `vpsload-a6-after-4`. It ran independently of any session and went inactive by itself at 01:19Z.
- **Method:** the same v3 sampler and summariser as notes 003 and 006-008. Both are byte-identical to the baseline's
  (`sha256sum -c` passed; see `data/009-a6-after-4/sampler-sha.txt`). The class definitions did not change. The
  decomposition reuses note 008's `data/008-a6-after-3/decompose3.py.txt` unchanged.
- **Data:** `data/009-a6-after-4/` holds:
  - the raw window (`.jsonl.gz`);
  - the summariser output and the per-process decomposition;
  - the processes behind each burst at or above one core (`bursts.txt`);
  - a venue survey of every gate run that overlapped the window across the fleet primaries;
  - the list of in-window non-routine runs that peer seats reported (`known-runs-in-window.txt`).
- This seat ran no test or gate load in the window.

| class | baseline (003) | window 1 (006) | window 2 (007) | window 3 (008) | window 4 |
|---|---|---|---|---|---|
| janitor-post-merge | 1.09 | 0.03 | 0.01 | 0.01 | 0.03 |
| commit-pre-commit-aggregate | 0.90 | 0.02 | 0.05 | 0.05 | 0.04 |
| adhoc-pytest-or-check | 0.49 | 0.18 | 0.42 | 0.59 | 0.49 |
| adhoc-gate-start | 0.12 | 0.73 | 0.54 | 1.11 | 0.06 |
| pre-push | 0.11 | 0.30 | 0.07 | 0.04 | 0.07 |
| commit-red-green-replay | 0.02 | 0.01 | 0.01 | 0.01 | 0.02 |
| **test/gate total** | **2.73** | **1.27** | **1.10** | **1.82** | **0.71** |

**Verdict: window 4 meets assertion 6's bar.** Routine test and gate load averaged 0.71 cores over 4.33 hours, by the
baseline's method. That is 5.2% of the 13.77 attributed cores; the host accounted 14.53 of 18. Across 52 five-minute
buckets, the median is 0.62 cores, 45 buckets are under one core, and the maximum is 1.95.

This is a measurement for the plan's own record. It is not the plan Proof of Done. The plan-level proof for assertion 6
is a `host_captured` record that a different session must replay before the archive gate counts it.

## What changed since window 3

- **adhoc-gate-start fell from 1.11 to 0.06 cores.** Window 3's largest source was fabro engine Rust builds run through a
  stale primary pack. No Rust compile appears inside any test/gate class this time (window 3: 0.56 cores). The venue
  survey has no unrouted run from the orchestrator primary in the window. The only `(none)` venue rows are 8 short
  `livespec-runtime` runs, 25.8 wall-minutes in total.
- **The residue is direct pytest in worktrees, as in windows 2 and 3.** adhoc-pytest-or-check is 0.49 cores, about
  two-thirds of the total. The bursts above one core are pytest-xdist workers under individual worktree virtualenvs. In
  the window's gate-run records, no full-suite command ran as a `cluster_job` or `--local`; the two `--local` runs were
  `gh run watch` watchers. So these suites were started outside the sanctioned gate runner, either directly or as a
  hook's scoped test run that the unchanged classifier counts as ad hoc. Examples:
  - orchestrator `fix/pack-prepare-payload-helpers` at 22:14Z;
  - dev-tooling `fix/livespec-dev-tooling-ri2lwi-release-keyed-serving-build` and `feat/gate-job-resources-declaration`
    at 23:46Z;
  - dev-tooling `feat/ci-infra-rerun-cetyrq` and `hp-factory-trial` at 01:03-01:13Z.

  Note 008 recorded this gap: assertion 4's routing sees only runs started through the gate runner. It remains a finding,
  not a child. Window 4 meets the bar with this residue included.
- **A janitor still runs checks on the dev host: livespec-driver-claude's.** The janitor-post-merge class reached 0.41
  cores at 00:58Z. Its top processes are a `janitor-reconcile-livespec-driver-claude-*` virtualenv python and `pyright`.
  verj3y moved only livespec-dev-tooling's janitor to `cluster_job`. Over the window this class is 0.03 cores.

## Known non-routine runs in the window

These are listed in `known-runs-in-window.txt` and accounted for here.

- **dev-host-disk-retention's manual run, 20:58:43-21:05:10Z.** Its only test/gate-class step was the pytest-scratch
  `rm`, 21:05:06-21:05:10Z. That is 4 s, below 0.01 core in its five-minute bucket. Its ownership `find`, uv prune and
  uvx loop count as "other".
- **The two independent replay runs, 21:10:30-21:16:51Z and 21:40:32-21:46:06Z.** Neither removed pytest scratch, so
  both are "other". The same holds for the read-only sizing `find`, 21:09:05-21:38:11Z.
- **The 23:12:56Z scheduled retention timer run.** It was held from 21:46Z for this window. The window's data shows no
  retention activity at that time.

Removing every one of these runs would lower the total by less than 0.01 core.

## Side observation

The venue survey excluded 158 gate-run records that started before the window and never wrote `finished_at`. Most of
them are early-November orchestrator and overseer review or commit runs. Those directories are part of the run-directory
count that `livespec-dev-tooling-2zotza` (the `gate-run.sh list` fork cost) re-measures after the retention prune.

## Next

The window-4 measurement and its data are the input to the plan-level `host_captured` record for assertion 6. That record
is taken with the plan Proof of Done, after the remaining children close. That proof uses this method unchanged.
