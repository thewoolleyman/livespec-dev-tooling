# 007 — Why master went red after green PRs, and what a merge queue would have prevented

Written 2026-11-14 by the stale-base-merge-options seat (hetzner-xubuntu). This note discharges work item
livespec-dev-tooling-b6lw5w, which was filed at throughput-plans-coordinator's direction (epic livespec-dev-tooling-r7iuj6,
rank 2b). It is evidence for assertion 4 of this plan's Definition of Done (note 005 §4), and it carries no assertion
of its own.

**Window:** the 7 days to 2026-11-13T22:05Z, which is throughput-track-organization's window.

**Data:** the GitHub Actions REST runs and jobs APIs, plus each failed coverage job's log. Method:
`data/master-red/collect.py.txt`. Raw failed-run records: `data/master-red/*-failed-runs-2026-11-13.json`. My counts
differ slightly from the throughput measurement (19 of 38 failed runs, by GraphQL check suites), because the two
methods cut the window edges differently. Neither method changes a classification.

## 1. livespec-dev-tooling

748 master `push` runs of `ci.yml`: 349 success, 362 cancelled (superseded by a newer merge) and 37 failed. 18 of the
37 failed on `check-per-file-coverage`. Each of those 18 is classified below.

### Stale-base semantic conflict: 7 runs, 4 episodes

In each episode a PR was green on its own base. A commit in the same area landed after that base and before the merge.
The composed tree failed, and it stayed red until a fix that names the interaction.

| Episode | PR, merged | Same-area commit that landed after its tested base | Red master runs | Fix |
|---|---|---|---|---|
| A | livespec-dev-tooling#4224 (bf3aab28), 2026-11-12 01:15:37Z | 323d37ed, the gate_repro reproduction route, landed **1 s earlier** | 2 (7ce9ecf5f, c3d4a34e1) | 1364fa2a: "read the Job in sequence, not through one terminal wait's argv" |
| B | livespec-dev-tooling#4339 (b9838b28), 2026-11-12 16:09:03Z | 4793883d added a converge step, which renumbered the step labels the test sliced on | 1 (6201dcdb2) | 8b3d6340. Its own comment says: "a step added ahead of this one renumbers the labels (4793883d8 did)" |
| C | livespec-dev-tooling#4138 (37f7caa7), 2026-11-11 11:15:58Z | 0088dfc7 renamed the fixture `union_key_block`, **6 s earlier**. Both commits were under the same work item, bqnzcm | 1 (37f7caa7f) | Reverted (bc333050). The collection error read: `cannot import name 'union_key_block'` |
| D | livespec-dev-tooling#4449 (da0264ace), 2026-11-13 05:33:59Z | livespec-dev-tooling#4442 (fba395aa), 87 s earlier. The test monkeypatched the loader that #4449 moved | 3 (da0264ace, 01a87e860, 517f396ff) | 785e0b96. This is incident livespec-dev-tooling-3hilpy |

**A full-suite merge queue would have prevented all 4 episodes and all 7 red runs.** The queue tests each PR on top
of the PRs ahead of it, so in each case the second PR's `merge_group` run would have failed, and the queue would have
removed that PR without merging it. That holds only under note 005's conditions:
- (a) `merge_group` runs the full aggregate, because every one of these failures surfaced only in `check-per-file-coverage`;
- (b) every path to master goes through the queue. Three of the four pairs merged within 87 s of each other, and two within
  6 s, so any path that skips the queue reopens exactly this window.

### Flake or nondeterministic coverage: 11 runs

The next completed master run was green in every case, and no commit between the two touched the failing test. A merge
queue would NOT have prevented any of these. It would have ejected an innocent PR instead, at the same per-run rate.

- **4 runs: nondeterministic coverage.** These are 42382775178, 42458558770, 43029995883 and 43151602585 (commits
  b795877a6, 8c0900840, d8d23caec and 37850ee7d). Each failed with `FAIL Required test coverage of 100.0% not reached.
  Total coverage: 100.00%`. A few lines were covered on some runs and not others, and the total rounds to 100.00%. Two of
  the four also logged a `FLAKE-RETRIED` test in the same session. One hypothesis, unproven, is that a retried test's
  first attempt leaves lines uncovered. That belongs to fleet-flaky-tests, not here.
- **7 runs: isolated test failures.** In each, the next run was green with no fix to the test:
  - 4e154e493: `test_node_status_credential_pull_on_rejection::test_a_missing_node_is_still_waited_for`;
  - 3e060c120: `test_delegated_gate_declared_recipe_scenarios::test_a_red_verdict_names_the_members_…[last-is-bash-stdout]`;
  - 63302bba5: the same test, `[last-is-bash-stderr]`. It failed twice in 4 hours, so it is a repeat offender;
  - 75e99de9c: `test_gate_run::test_an_idle_detached_gate_run_and_an_idle_waiter_spawn_no_per_tick_process`;
  - b082d9a87: `test_incident_recovery_principal_target_branch::test_moved_scratch_head_without_overlap_…`;
  - d273b7a9d: `test_incident_recovery_principal::test_genuine_overlap_with_later_work_…`;
  - d2f49db53: `test_incident_recovery_principal_refusals::test_crash_before_the_commit_exists_is_provably_inert`.

  Three of the seven are in the incident recovery principal's tests. That cluster is a lead for fleet-flaky-tests.

## 2. livespec-orchestrator-beads-fabro (fleet scope, as the item asks)

492 master `push` runs: 369 success, 112 cancelled and 11 failed. **None is a stale-base conflict.** Every failure was
green again within one to three runs, with no fix to the failing code:

- **3 runs failed with no failing job.** These are 35d0a1716, cc55fc7ea and fdccf17a6. In two, every job concluded
  success or skipped. The third created no jobs at all. These are run-level failures on the forge side, the same shape
  as livespec-dev-tooling-nofeol's missing legs.
- **3 runs are runner or forge infrastructure:**
  - 0823f3d91 and 6f7b88531: the uv binary was not found on the runner
    (`/opt/ci-runner/uv-proxy/uv: … uv-x86_64-unknown-linux-musl/uv: not found`);
  - 8669d587d: an artifact upload got an HTML error page from the forge.
- **2 runs are nondeterministic coverage** in `check-per-file-coverage (nonroot)`:
  - 50b966f98: a test file read 99.73% with 0 missing lines, which is a branch-coverage swing;
  - 5a628efd5: `_dispatcher_sandbox_image_readiness.py` read 94.3%. That commit was spec-only, and the next run went green
    on a release commit with no code change.
- **3 runs are `check-metadata-batch`:**
  - bf9363999 exited 56, a curl receive error;
  - 7c4d7cafb and 9a8ad7334 (2026-11-13 11:57Z and 19:10Z) both failed target `check-fleet-launch`, and each was green
    on the next run. The same check failing twice in one day is a lead for fleet-flaky-tests.

A merge queue would have prevented 0 of the orchestrator's 11.

## 3. What this means for the plan

- **Prevented by the queue:** 7 of livespec-dev-tooling's 18 coverage reds (39%). That is every stale-base case, and
  each cost a red master plus a fix-forward or revert. In the orchestrator, 0 of 11.
- **Not prevented:** 11 of 18 in dev-tooling and 11 of 11 in the orchestrator. In a queue, each of those becomes an
  ejected innocent PR, followed by a re-queue. That makes flake reduction (fleet-flaky-tests) a direct input to queue
  throughput, and the semantic-conflict drill in work item livespec-dev-tooling-o6eytb should measure the ejection rate
  next to the prevention.
- Recovering from a red master stays with red-master-self-healing (scope event 2026-11-14T01:59:15Z). The seat pointed
  that plan at this item on 2026-11-14.
