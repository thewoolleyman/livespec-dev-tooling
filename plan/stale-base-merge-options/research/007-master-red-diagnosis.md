# 007 — Why master went red after green PRs, and what a merge queue would have prevented

Written 2026-11-14 by the stale-base-merge-options seat (hetzner-xubuntu). This note discharges work item
livespec-dev-tooling-b6lw5w, which was filed at throughput-plans-coordinator's direction (epic livespec-dev-tooling-r7iuj6,
rank 2b). It is evidence for assertion 4 of this plan's Definition of Done (note 005 §4), and it carries no assertion
of its own.

**Window:** the 7 days to 2026-11-13T22:05Z, which is throughput-track-organization's window.

**Data:** the GitHub Actions REST runs and jobs APIs, plus each failed coverage job's log. Method:
`data/master-red/collect.py.txt`. Raw failed-run records: `data/master-red/*-failed-runs-2026-11-13.json`.

The REST listing returned 37 failed runs, 18 of them on coverage. The throughput measurement, which used GraphQL check
suites, found 38 and 19. I re-ran the GraphQL query to settle the difference. It returns exactly one run the REST listing
omitted: 43128348212, commit ce6288d2f (livespec-dev-tooling#4214), created 2026-11-12 00:35:08Z, which failed on
`check-per-file-coverage`. It is classified below, so **no coverage red is in dispute: the set is 19 of 38**.

## 1. livespec-dev-tooling

749 master `push` runs of `ci.yml`: 349 success, 362 cancelled (superseded by a newer merge) and 38 failed. 19 of the
38 failed on `check-per-file-coverage`. Each of those 19 is classified below.

### Stale-base semantic conflict: 7 runs, 4 episodes

In each episode a PR was green on its own base. A commit in the same area landed after that base and before the merge.
The composed tree failed, and it stayed red until a fix that names the interaction.

| Episode | PR, merged | Same-area commit that landed after its tested base | Red master runs | Fix |
|---|---|---|---|---|
| A | livespec-dev-tooling#4224 (bf3aab28), 2026-11-12 01:15:37Z | livespec-dev-tooling#4177 (085a0983), 2026-11-12 00:39:22Z. It is a **revert** of the client's terminal watch, which the suite's stub answered. It landed after #4224's last rebase (base b1a2f1f32, which does not contain it). 323d37ed is #4224's own first commit, not the conflicting change | 2 (7ce9ecf5f, c3d4a34e1) | 1364fa2a. Its message: "livespec-dev-tooling#4177 reverted the watch at 00:39Z, after livespec-dev-tooling#4224's last rebase and before its auto-merge … The branch was green and the merged tree red" |
| B | livespec-dev-tooling#4339 (b9838b28), 2026-11-12 16:09:03Z | 4793883d added a converge step, which renumbered the step labels the test sliced on | 1 (6201dcdb2) | 8b3d6340. Its own comment says: "a step added ahead of this one renumbers the labels (4793883d8 did)" |
| C | livespec-dev-tooling#4138 (37f7caa7), 2026-11-11 11:15:58Z | 0088dfc7 renamed the fixture `union_key_block`, **6 s earlier**. Both commits were under the same work item, bqnzcm | 1 (37f7caa7f) | Reverted (bc333050). The collection error read: `cannot import name 'union_key_block'` |
| D | livespec-dev-tooling#4449 (da0264ace), 2026-11-13 05:33:59Z | livespec-dev-tooling#4442 (fba395aa), 87 s earlier. The test monkeypatched the loader that #4449 moved | 3 (da0264ace, 01a87e860, 517f396ff) | 785e0b96. This is incident livespec-dev-tooling-3hilpy |

**A full-suite merge queue would have prevented all 4 episodes and all 7 red runs.** The queue tests each PR on top
of the PRs ahead of it, so in each case the second PR's `merge_group` run would have failed, and the queue would have
removed that PR without merging it. That holds only under note 005's conditions:
- (a) `merge_group` runs the full aggregate, because every one of these failures surfaced only in `check-per-file-coverage`;
- (b) every path to master goes through the queue. Episode A's culprit was itself a REVERT (#4177). A server-side or expedited-incident revert that lands outside the
  queue is exactly the bypass condition (b) guards against: the queue cannot test a PR against a change that never
  entered it. So the incident recovery path's direct push must either be followed by re-queuing every armed PR, or must
  itself go through the queue whenever master is not red. Two of the four pairs merged within 87 s of each other, and one
  within 6 s.

### Flake or nondeterministic coverage: 12 runs

For each of these, a later master run passed `check-per-file-coverage` with the failing test, or for the coverage
cases the code involved, untouched by any commit in between. That is NOT always the very next run. After 75e99de9c, the
next run (8c0900840) also failed coverage, as one of the nondeterministic-coverage runs below. After d273b7a9d, the next
runs failed on other jobs (export-telemetry), not on coverage. None of the 12 had a same-tree re-run (every run is attempt
1), so the classification rests on "passed later without a change", not on a re-run of the same tree. A merge queue would
NOT have prevented any of these. It would have ejected an innocent PR instead, at the same per-run rate.

Each is routed below to fleet-flaky-tests (epic livespec-dev-tooling-zwveqp) by item:

| Run(s) | Failure | Routed to |
|---|---|---|
| b795877a6, ce6288d2f, 8c0900840, d8d23caec, 37850ee7d (5 runs) | `FAIL Required test coverage of 100.0% not reached. Total coverage: 100.00%` | livespec-dev-tooling-e34ks3 (pending-approval): a timed wait loop covers its sleep line only when the wait is slow. That fits better than this note's earlier retry hypothesis, which is withdrawn |
| 4e154e493 | `test_node_status_credential_pull_on_rejection::test_a_missing_node_is_still_waited_for` | livespec-dev-tooling-xrdhfl, root-fixed and closed 2026-11-12T00:11Z, after this failure |
| 3e060c120, 63302bba5 | `test_delegated_gate_declared_recipe_scenarios::test_a_red_verdict_names_the_members_…[last-is-bash-stdout / -stderr]` | livespec-dev-tooling-wv57ma, closed 2026-11-09T20:26Z, after both failures |
| 75e99de9c | `test_gate_run::test_an_idle_detached_gate_run_and_an_idle_waiter_spawn_no_per_tick_process` | livespec-dev-tooling-oczx3k, closed 2026-11-13T11:12Z; its siblings x5z6ly and qohfro are also closed |
| b082d9a87 | `test_incident_recovery_principal_target_branch::test_moved_scratch_head_without_overlap_…` | livespec-dev-tooling-63ig7h, closed 2026-11-13T20:47Z |
| d273b7a9d | `test_incident_recovery_principal::test_genuine_overlap_with_later_work_…` | livespec-dev-tooling-vzfxlg (active): the recovery principal's tests see a "pending" outcome on a loaded runner |
| d2f49db53 | `test_incident_recovery_principal_refusals::test_crash_before_the_commit_exists_is_provably_inert`. Its detail is "incident git diff exceeded its 10 s ceiling" (`INCIDENT_GIT_TIMEOUT_SECONDS`) | livespec-dev-tooling-vm4vcn, whose bullet 3 raises that ceiling to the hang guard in incident test worlds. fleet-flaky-tests routed it there on 2026-11-14 ~03:05Z and recorded the sighting on vm4vcn. It is not vzfxlg's forge-timeout class |

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

- **Prevented by the queue:** 7 of livespec-dev-tooling's 19 coverage reds (37%). That is every stale-base case, and
  each cost a red master plus a fix-forward or revert. In the orchestrator, 0 of 11.
- **Not prevented:** 12 of 19 in dev-tooling and 11 of 11 in the orchestrator. In a queue, each of those becomes an
  ejected innocent PR, followed by a re-queue. That makes flake reduction (fleet-flaky-tests) a direct input to queue
  throughput, and the semantic-conflict drill in work item livespec-dev-tooling-o6eytb should measure the ejection rate
  next to the prevention.
- Recovering from a red master stays with red-master-self-healing (scope event 2026-11-14T01:59:15Z). The seat pointed
  that plan at this item on 2026-11-14.
