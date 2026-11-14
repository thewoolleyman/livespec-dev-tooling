# Covering-run attribution: covered-by-red-run (2026-11-14)

Plan throughput-metric (livespec-dev-tooling-oe7cfw). This note refines how the throughput headline attributes a red
covering run. It does not change the metric's definition, which is throughput-track-organization's note 003
(`plan/throughput-track-organization/research/003-the-one-metric-definition-and-baseline.md`, section "Definition";
it moves to `plan/archive/throughput-track-organization/research/` when that plan archives) as ratified in
SPECIFICATION/non-functional-requirements.md section "Merged-green throughput telemetry" (proposal
a-scheduled-graphql-reconciler-emits). The definition belongs to this plan, so rules that evolve it live here.

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
- Fix-forward guard: no commit between the covering run and the run that passes its failing checks may touch a failing
  test or a file the coverage table reports with missed lines or partial branches. Both are read from the failed jobs'
  logs, by the method of stale-base-merge-options' note 007 (FAILED or ERROR `tests/...` lines, and coverage rows with
  miss or brpart above 0), and the touched files from a compare of the two commits. A pass that follows such a touch
  is a fix-forward, not a flake, and the merge stays in its ordinary not-green class.

First measurement, livespec-dev-tooling, trailing 24 h at 2026-11-14 ~11:1xZ: 5 merges fall in the class, among them
#4617 and #4640, whose covering run 43575401935 failed on the flake `test_gate_sandbox_range_and_bootstrap.py:351` that
passed 40 min later. The implementation is the stopgap `~/.local/share/pr-throughput/headline.py` on hetzner-xubuntu
(plan throughput-metric, livespec-dev-tooling-oe7cfw); its committed successor is livespec-dev-tooling-sikvra.
