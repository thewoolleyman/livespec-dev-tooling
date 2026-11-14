# The one metric: definition, validation and baseline (2026-11-13)

The maintainer's metric (note 002): PRs per repository per hour, merged to the main branch and passing as green.

## Definition

- **A merged PR** is one pull request whose `mergedAt` falls in the window. A rebase-merge can land several commits;
  they are grouped by the commit's `associatedPullRequests`, so a PR counts once however many commits it lands. Its
  **merge head** is the newest of its commits on the default branch.
- **Green** (the headline, "merged green"): the first default-branch `CI` push run at or after the PR's merge head
  that reached a verdict (`SUCCESS`, `FAILURE`, `TIMED_OUT`, `STARTUP_FAILURE`) concluded `SUCCESS`. A cancelled run
  is not a verdict: the workflow's concurrency rule cancels a master run when a newer merge arrives, and the newer
  head's run then covers every commit beneath it.
- **Own-run green** (reported beside it): the push run on the PR's own merge head concluded `SUCCESS`. This is the
  strict reading of the coordinator's wording ("the main-branch CI run for the resulting head concluded success").
- **Window**: trailing 24 h for the live panel, trailing 7 d for the baseline and for judging the track. Rate is
  count / window hours. Times are UTC.

Why the headline is not own-run green: in livespec-dev-tooling 362 of 745 merge-head runs over 7 d were cancelled by
a newer merge (101 of 144 in the last 24 h). Under the strict reading a repository's score FALLS as it merges
faster, which is the opposite of what the metric is for. Both are reported so the gap stays visible; the gap itself
(merges whose own head was never tested) is the stale-base and bisect exposure owned by stale-base-merge-options.

This is a session decision under CLAUDE.md "Decision authority", reported for objection.

### Covering-run attribution: covered-by-red-run (added 2026-11-14)

A merge whose own master run was cancelled is judged by its covering run, and that run can fail for a reason that has
nothing to do with the merge, typically a flake on a newer merge's head. Such a red is charged to the merge by
attribution only. The rule, agreed by throughput-plans-coordinator, throughput-metric and stale-base-merge-options
(whose note 007 classifies the same master reds per run, with job ids):

- A not-green merge is **covered-by-red-run** when its own master run was `CANCELLED` by a newer merge, its covering
  run failed, and each check that failed on the covering run (the `ci-green` aggregate excluded) passes on the next
  completed default-branch run that executes it, with no commit headlined `Revert` landing in between. If the same
  check fails again first, the red is real and the merge stays in its ordinary not-green class.
- The headline definition is unchanged: such a merge still counts NOT GREEN in M1. The headline shows it as its own
  not-green class, and a separately labelled diagnostic rate (never quoted as M1) counts it green.
- Known limit: a fix-forward that edits the failing test (rather than reverting) cannot be told apart from check runs
  alone, because the failing test's identity is in the job logs, not the check name. Note 007's per-run attributions
  are the cross-check for that case.

First measurement, livespec-dev-tooling, trailing 24 h at 2026-11-14 ~11:1xZ: 5 merges fall in the class, among them
#4617 and #4640, whose covering run 43575401935 failed on the flake `test_gate_sandbox_range_and_bootstrap.py:351` that
passed 40 min later. The implementation is the stopgap `~/.local/share/pr-throughput/headline.py` on hetzner-xubuntu
(plan throughput-metric, livespec-dev-tooling-oe7cfw); its committed successor is livespec-dev-tooling-sikvra.

## Baseline (GitHub GraphQL, the authority)

Windows: 24 h = 2026-11-12T22:04:21Z to 2026-11-13T22:04:21Z; 7 d = 2026-11-06T22:05:04Z to 2026-11-13T22:05:04Z.
Method and raw results: `data/measurement-scripts.md` (merged-green-baseline), `data/merged-green-24h-2026-11-13.json`,
`data/merged-green-7d-2026-11-13.json`.

| Repository | 24 h merged | 24 h merged green /h | 7 d merged | 7 d merged green /h | 7 d own-run green /h | 7 d merged on a red or unverified head |
|---|---|---|---|---|---|---|
| livespec-dev-tooling | 144 | 4.21 | 745 | 3.79 | 2.05 | 108 |
| livespec-orchestrator-beads-fabro | 85 | 3.25 | 492 | 2.82 | 2.19 | 18 |
| livespec-overseer | 44 | 1.54 | 111 | 0.61 | 0.61 | 9 |
| livespec | 16 | 0.67 | 72 | 0.42 | 0.42 | 2 |
| livespec-console-beads-fabro | 9 | 0.38 | 25 | 0.14 | 0.14 | 2 |
| livespec-driver-claude | 11 | 0.46 | 41 | 0.24 | 0.24 | 0 |
| livespec-driver-codex | 12 | 0.46 | 57 | 0.33 | 0.33 | 2 |
| livespec-driver-pi | 8 | 0.33 | 37 | 0.21 | 0.21 | 1 |
| livespec-orchestrator-git-jsonl | 8 | 0.33 | 37 | 0.21 | 0.21 | 1 |
| livespec-runtime | 13 | 0.54 | 44 | 0.26 | 0.26 | 1 |
| dolt-server | 6 | 0.25 | 7 | 0.04 | 0.04 | 0 |
| homelab | 3 | 0.12 | 22 | 0.13 | 0.13 | 0 |
| hetzner-xubuntu-info | 35 | 1.46 | 71 | 0.42 | 0.42 | 0 |
| 1password-env-wrapper | 2 | 0.00 | 2 | 0.00 | 0.00 | 2 |
| openbrain | 0 | 0.00 | 3 | 0.02 | 0.02 | 0 |
| **Fleet** | 396 | 14.0 | 1766 | 9.64 | | 146 |

Readings the numbers support, and no more:

- Two repositories carry 70% of fleet merges over 7 d (livespec-dev-tooling 745, the orchestrator 492 of 1766).
- In livespec-dev-tooling 102 of 745 PRs (14%) over 7 d merged under a master run that then FAILED, and 37 of 144
  (26%) in the last 24 h. That is merged-but-not-green: it is counted out of the metric, and it is the largest
  single gap between "merged" (4.43/h) and "merged green" (3.79/h) in any repository.
- 1password-env-wrapper has no `CI` push workflow, so it can never score; it is out of the metric until it has one.
- The count is of ALL merged PRs: factory PRs, seat PRs, release-please and dependency PRs alike. Splitting it by
  author class needs a label or branch-prefix rule and is not done here.

## Can Honeycomb `github-ci` compute it? No, not as emitted today

Measured 2026-11-13 ~22:0xZ, `github-ci`, 24 h, `ci.event = push`, default branch, by `repo`:

| Repository | Honeycomb distinct `ci.run_id` | GitHub merge-head runs SUCCESS / FAILURE / CANCELLED |
|---|---|---|
| livespec-dev-tooling | 31 | 25 / 17 / 101 |
| livespec-orchestrator-beads-fabro | 43 | 41 / 2 / 39 |
| livespec-overseer | 42 | 37 / 4 / 0 |

Three defects, read from `.github/scripts/export-ci-telemetry.sh` and the rows:

1. **`ci.conclusion` is empty on almost every `ci.run` span.** The exporter is a step INSIDE the run it describes,
   so `gh run view --json conclusion` answers while the run is still in progress. Only
   livespec-console-beads-fabro's rows carried `success`.
2. **A run that fails or is cancelled before the export step emits nothing.** Honeycomb held 1 failed
   livespec-dev-tooling push run where GitHub has 17, and none of the 101 cancelled ones.
3. **No PR identity.** The span has the head SHA but no PR number and no `mergedAt`, so several commits of one
   rebase-merge cannot be grouped, and a cancelled head cannot be tied to the later run that covers it.

So the panel needs a NEW emitter: one event per merged PR, written when its covering default-branch run reaches a
verdict, carrying `repo`, `pr.number`, `pr.merged_at`, `git.merge_head_sha`, `ci.covering_run_id`,
`ci.covering_conclusion`, `pr.own_run_conclusion` and `pr.merged_green` (boolean). The panel is then
`COUNT WHERE pr.merged_green = true GROUP BY repo`, at 1 h granularity. A scheduled reconciler reading the GitHub
GraphQL API (the query in `data/measurement-scripts.md` (merged-green-baseline) costs 2 to 21 points per repository per run) can emit
them without touching the REST budget that ran out at 21:56Z today. Fleet scope: all 15 repositories above.

## Where the panel goes

The maintainer's "existing livespec board" is read as Honeycomb board `livespec family — all activity`
(id `krThv8DvcwS`), the only board named for livespec as a whole. It is NOT among the three boards committed under
`ci-runner/observability/boards/` (`ci-runner-pool`, `k8s-node-load`, `k8s-workload-control-plane`), so making the
panel its first item also means bringing that board under the committed `apply-boards.sh` path. Owner:
kubernetes-observability (livespec-dev-tooling-s2aqob), as the track's first deliverable.
