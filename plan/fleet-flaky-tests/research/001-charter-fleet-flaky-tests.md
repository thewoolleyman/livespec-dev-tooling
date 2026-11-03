## The maintainer's statement of what done means

Flaky tests and bd-ib-gb24he. - these should all be grouped into a single high priority plan to get fixed at once , asap, with focus, not given to the individual plans to thrash on over many builds.

## Definition of Done assertions derived from that statement

- Every flaky test currently known in the fleet's CI and gates is root-fixed and closed, and the fleet's CI runs have no repeat red from a known flaky test over a 24 h window.

## Charter

Opened 2026-11-03 by legacy-coordinator-agent (epic livespec-dev-tooling-6tgd2z) on the maintainer's direction,
PRIORITY 1 in the priorities record of 2026-11-03T15:00:57Z. The seat is `fleet-flaky-tests`.

Every known flaky test in the fleet's CI and gates is fixed HERE, together, at its root, in focused batches grouped
by root-cause class, instead of one build per flake inside whichever plan happened to trip over it.

Standing rules this plan works under:

- `.ai/coordinator-duties.md` §2: a flaky check is a defect. Never retry it as a fix, never widen its timeout as a
  fix. A 429 is not a flake and is simply re-run.
- The untouched-test 3-retry plugin (Retry a failing test the run did not touch, livespec-dev-tooling-crxcy4) stays
  with plan dev-host-test-gate-load. Retries are the safety net. A retry never closes a flake item; the root fix does.
- The shared technique for every timing class: order the test by a rendezvous (a pipe, a file, a readiness signal,
  a child's exit, an injected clock) instead of a wall-clock bound. Any remaining wall-clock wait is a liveness
  guard against a hang only, never the condition that decides pass or fail.

## Ownership across tenants

Children in this repository's tenant are re-parented under this epic with `reparent_plan_child`. Items in other
tenants (livespec-orchestrator-beads-fabro `bd-ib-*`, livespec-overseer `overseer-*`, livespec `livespec-*`) cannot
carry a parent edge to an epic in another tenant. Each carries a comment naming this plan as its owner, and the
carrier-map scope event names them by id, which the carrier tenancy resolves by prefix.

## Inventory (2026-11-03 ~15:3xZ, `bd list --status all` in all five tenants)

livespec-driver-codex has no open flake item.

### Class A: wall-clock bounds and load-sensitive timeouts in tests

Shared fix: rendezvous or behaviour ordering, a liveness ceiling only.

livespec-dev-tooling:
- livespec-dev-tooling-alvhwt (ready): node-status RBAC concurrency test's negative-control arm depends on host load.
- livespec-dev-tooling-b2mnrq (active): gate renderer exit tests use a 1 s readiness wait for the stand-in PyPI proxy.
- livespec-dev-tooling-cywp72 (pending-approval): node-status credential refresh test fails intermittently with no
  cause reported; first leg is diagnostics.

livespec-orchestrator-beads-fabro:
- bd-ib-gb24he (ready, factory run in flight): the coverage-leg races, 8 flakes, under ci-runtime-and-cost until now.
- bd-ib-lwiila (ready): Scenario 297 integration test re-runs the whole fleet-launch harness under 180 s.
- bd-ib-acnvo (backlog): test_session_wait_deadline_safety 1 s pid-file wait.
- bd-ib-funlsh (ready): hung-pane wait test races its own deadline.
- bd-ib-dsprir (blocked, needs-human): streaming runner test asserts completion inside 2.0 s.
- bd-ib-ke5wkf (blocked, needs-human): replace real-sleep and wall-clock assertions and refuse new ones. This is the
  class guard for the orchestrator suite.

Fabro fork (hand-build, host-captured):
- bd-ib-gmuxd4 (ready): streaming_model_activity_in_child_branches_refreshes_the_budget races a 1000 ms stall budget.

livespec-overseer:
- overseer-1p3n, overseer-q4nq, overseer-efwz, overseer-nyul, overseer-zp9n, overseer-exxi, overseer-lcmkpu (ready):
  terminal, pager, Chrome, OTel queue and live-exercise probe tests bounded by 0.1-3.0 s windows.
- overseer-i6yp (ready) and overseer-twtw55 (blocked): Codex skill-picker e2e fixed wall-clock budget.
- overseer-jdo (ready): the check aggregate fails a watcher test under concurrency that passes standalone.
- overseer-aiht7g (acceptance): Codex herdr controller bootstrap timeout; it finishes its own acceptance.

### Class B: pipefail SIGPIPE through early-exiting readers

- livespec-dev-tooling-ftgiu4 (active): the sandbox-image-warm SIGPIPE flake and its class (grep -q, head -1).
- livespec-dev-tooling-mfk3h4 (pending-approval): sweep pipelined grep -q and lint against it. Check against
  ftgiu4's merged diff first; it may be absorbed.

### Class C: shared state or first-run install races in gates

- livespec-dev-tooling-c533rb (active): parallel check dispatcher fans out before pyright's first-run install.
- bd-ib-g5hp (backlog): sandbox pyright intermittently analyzes the uv stdlib. Very likely the same race as c533rb
  and the closed livespec-dev-tooling-nhjx; verify and close as absorbed.
- livespec-dev-tooling-3wz453 (backlog): shared `.coverage` data file corrupt under concurrent aggregates.
- livespec-dev-tooling-lndv2l (active): gate-run.sh's config-write watcher reads core.bare before the write lands.

### Class D: cause not yet known

- bd-ib-5s4egd (backlog): janitor doctor-static red, passes on rerun.
- livespec-s9il (backlog): check-doctor-static flakes in livespec core CI, passes on bare rerun.
  One investigation for both, then route by the cause found.

### Out of scope, with reason

- livespec-dev-tooling-crxcy4: the retry safety net, owned by dev-host-test-gate-load (brief rule 4).
- overseer-kuqhwn: live-herdr fixture network isolation is a hermeticity item under overseer-uzvcbn, with no observed
  flaky verdict on record.
- overseer-uzvcbn.13 (the herdr pane-environment flake) is already closed.
- livespec-dev-tooling-nk6xud, -wkkjkd, -77n72m, -nhjx are closed.

## Batch plan

1. In flight, not re-dispatched: gb24he, ftgiu4, c533rb, b2mnrq, lndv2l, aiht7g. Each is watched to close.
2. Batch A-overseer: ONE carrier in the overseer tenant fixes all ten wall-clock tests listed above with the
   rendezvous technique. The member items close as absorbed when it merges.
3. Batch A-orchestrator: ONE carrier for acnvo, funlsh and dsprir; lwiila separately (it is a test restructure);
   ke5wkf adds the guard against new wall-clock assertions once the batch lands.
4. Batch A-dev-tooling: alvhwt, plus cywp72's diagnostics leg.
5. gmuxd4: Fabro fork hand-build, routed to the fork's hand-build path.
6. Class B: mfk3h4 after ftgiu4 merges.
7. Class C: g5hp verified against c533rb and closed as absorbed; 3wz453 fixed by per-run coverage data files.
8. Class D: one investigation for 5s4egd and s9il.

Hand-land a fix whenever that is faster than a factory build and master is red (stop the line).
