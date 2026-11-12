---
topic: test-exact-concurrent-reservation-survives
author: claude-opus-5-5
created_at: 2026-11-12T21:40:00Z
---

## Proposal: A test's verdict does not depend on how fast the host runs it: waits on required progress carry no short wall-clock bound, and a worker thread's exception fails the test

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Adds one bullet, **Load-independent concurrency waits**, to non-functional-requirements.md, section "Testing approach". It goes after the bullet that begins "**Host-state isolation of CLIs.**" and before "**Import-Linter.**". No heading is added, removed or renamed, so `tests/heading-coverage.json` does not change.

The bullet states three things:
- a test that waits for something the code under test is required to do does not fail just because that took longer than a short fixed time;
- a bound on such a wait is a hang guard only: one shared value per repository, at least 120 seconds, and its expiry fails the test as a hang naming what it waited for;
- an exception raised in a test's worker thread fails the test, and the report names that exception.

It names the two kinds of wait the rule does not govern. It binds this repository's tests only; the fleet half is carried by one proposal per member repository (see "Fleet scope").

### Motivation

Work item livespec-dev-tooling-dqndbz (plan expedited-incident-hardening, epic livespec-dev-tooling-dh3hub) is the coordinator-duties §2 root fix for a flake. `tests/livespec_dev_tooling/test_incident_recovery_journal.py::test_exact_concurrent_reservation_survives_restart_and_conflicting_bytes` failed `assert not True` at line 220 in CI run 43287363009. That run was on livespec-dev-tooling#4359, a warm-cache-only diff that touched no incident code. The failure blocks unrelated pull requests.

The test starts two `reserve()` threads behind `Barrier(2).wait(timeout=3)`, then runs `worker.join(3)` and `assert not worker.is_alive()`. On a loaded runner the file-locked reserve takes longer than 3 s, so the join returns with the thread still alive and the assert fires. Nothing is wrong with the code under test. A worker exception is also swallowed: it shows up only later, as a length mismatch on the results list.

At filing (2026-11-12T21:20:33Z, spec v206) intake routed dqndbz to the spec-change tier with verdict-kind unstated. The generalization target was `## Testing approach` and the linked topic was this one. The judge's rationale: nothing in that section states that a test must avoid wall-clock bounds on its worker threads, or must surface a thread's exception. legacy-coordinator-agent checked that hold at ~21:22Z and confirmed it is real. The section's **Untouched-test retry** bullet re-runs such a failure in place, but it treats the symptom. It also does not apply when the change set touches the test, and the per-node-id root-fix item it requires has no clause to fix against. This proposal supplies that clause.

The fleet already uses the idea of a "hang guard", a bound that exists only to report a wedged party. Examples are `_HANG_GUARD_SECONDS = 180` in `tests/livespec_dev_tooling/test_check_per_file_coverage_xdist_controller_watchdog.py`, and `# a hang guard, not a bound` in livespec-orchestrator-beads-fabro's `test_dispatcher_watchdog.py:1301`. But no rule sets a floor on that bound. In practice hang guards of 2, 3, 5 and 10 seconds sit beside the 180-second one, and a 3-second "hang guard" is exactly what failed here. The 120-second floor is 40 times the bound that fired, and below the 180 seconds the fleet already uses for its slowest guarded call. A repository may choose any longer value.

### Fleet scope (rule K)

The rule names the repositories whose tests carry the shape. Every fleet repository under `/data/projects` that carries a `.livespec.jsonc` was swept at its checked-out `HEAD` on 2026-11-12 ~21:25Z. The search covered test files (`*test*.py`, `tests/**/*.py` and `conftest.py`, excluding vendored trees), using this pattern:

```text
\.join\(\s*(timeout\s*=\s*)?[0-9][0-9.]*\s*\)|\.wait\(\s*timeout\s*=\s*[0-9]|assert\s+not\s+.*\.is_alive\(\)
```

These repositories had no hits: dolt-server, hetzner-xubuntu-info, livespec, livespec-console-beads-fabro, livespec-driver-claude, livespec-driver-pi, livespec-orchestrator-git-jsonl, livespec-runtime, livespec-tdd-proof, openbrain and resume. homelab's only hit is a teardown wait (`tools/shared_credentials_provisioning/tests/fake_service.py:35`, `process.wait(timeout=5)` falling through to `kill()`), which the rule exempts.

The hits below are PATTERN hits. Each has not yet been judged against the rule, because one pattern covers all three of the rule's cases: some lines are verdict-bearing bounds, some are teardown waits, and some are expected-expiry windows. Two expected-expiry windows in livespec-orchestrator-beads-fabro are already excluded (`test_dispatcher_secret_review_fixes.py:355` and `test_session_wait_deadline_safety.py:511`). Each repository's root-fix item classifies its own lines against the ratified bullet. It fixes every verdict-bearing bound and every swallowed worker exception, and records why it left each exempt line alone.

- **livespec-dev-tooling** (73 hits in 20 files). The same shape as the failing test, `join(3)` followed by `assert not …is_alive()`, recurs in `test_incident_observer_invalidation.py`, `test_incident_observer_invalidation_edges.py` and `test_incident_recovery_journal_service.py`.
  - `tests/consumer/test_fabro_settings_drift_scenario.py`: 90
  - `tests/livespec_dev_tooling/fleet/test_tag_adopt.py`: 901, 903
  - `tests/livespec_dev_tooling/test_dev_host_retention.py`: 338, 521
  - `tests/livespec_dev_tooling/test_dev_host_retention_tmpfs.py`: 372
  - `tests/livespec_dev_tooling/test_dispatcher_coverage_namespaces_signals.py`: 120
  - `tests/livespec_dev_tooling/test_incident_ci_job_collection.py`: 198, 220, 236
  - `tests/livespec_dev_tooling/test_incident_conflict_chain.py`: 1327, 1328
  - `tests/livespec_dev_tooling/test_incident_conflict_sweep.py`: 176, 177, 196, 197, 221, 222, 330, 363
  - `tests/livespec_dev_tooling/test_incident_observer.py`: 361, 367, 569, 574, 578, 591, 602
  - `tests/livespec_dev_tooling/test_incident_observer_control.py`: 117
  - `tests/livespec_dev_tooling/test_incident_observer_endpoint.py`: 117, 229, 230, 231, 236, 237, 252, 272, 273, 285, 290, 303
  - `tests/livespec_dev_tooling/test_incident_observer_invalidation.py`: 170, 393, 394, 419
  - `tests/livespec_dev_tooling/test_incident_observer_invalidation_edges.py`: 82, 83, 113, 114, 123, 135, 136
  - `tests/livespec_dev_tooling/test_incident_observer_reconciler_window.py`: 159, 163, 173
  - `tests/livespec_dev_tooling/test_incident_observer_target_branch.py`: 221, 222
  - `tests/livespec_dev_tooling/test_incident_original_run_watch.py`: 257, 316, 317
  - `tests/livespec_dev_tooling/test_incident_recovery_journal.py`: 212, 219, 220 (livespec-dev-tooling-dqndbz)
  - `tests/livespec_dev_tooling/test_incident_recovery_journal_service.py`: 514, 515, 516
  - `tests/livespec_dev_tooling/test_incident_repository_fence.py`: 179, 248, 258, 286, 291, 301
  - `tests/livespec_dev_tooling/test_local_gate_slots.py`: 431, 474
- **livespec-orchestrator-beads-fabro** (48 hits in 25 files). The shared helper `end_run_and_await_launcher_return` in `tests/conftest.py:1221` bounds the launcher-thread join at `_LAUNCHER_RETURN_TIMEOUT_SECONDS = 10.0`, and every watchdog launcher fixture inherits it.
  - `tests/conftest.py`: 1221
  - `tests/e2e-cli/test_codex_skill_picker.py`: 316, 320, 323, 361, 380
  - `tests/e2e-cli/test_codex_skill_picker_pidfd_fallback.py`: 55, 78
  - `tests/e2e/test_session_wait_pane_live_herdr.py`: 162, 395, 396, 655
  - `tests/integration/test_needs_human_node_timeout_cut_scenario192.py`: 317
  - `tests/integration/test_run_wall_budget_scenario175.py`: 160
  - `tests/integration/test_session_wait_telemetry_scenario159.py`: 148, 315, 326, 327, 460, 537
  - `tests/integration/test_watchdog_bound_run_poll_scenario173.py`: 132
  - `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_heartbeat_probe.py`: 433
  - `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_reflector_oob_wiring.py`: 194, 267
  - `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_run_wall_budget_launcher.py`: 166
  - `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_run_wall_budget_terminal.py`: 132
  - `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_secret_review_fixes.py`: 359, 363
  - `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_stall_window.py`: 126
  - `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_watchdog.py`: 1291, 1301
  - `tests/livespec_orchestrator_beads_fabro/commands/test_otel_receive.py`: 980, 1039
  - `tests/livespec_orchestrator_beads_fabro/commands/test_session_obligation_delegation.py`: 175, 180
  - `tests/livespec_orchestrator_beads_fabro/commands/test_session_telemetry_export.py`: 128
  - `tests/livespec_orchestrator_beads_fabro/commands/test_session_telemetry_export_tolerances.py`: 55, 128, 129
  - `tests/livespec_orchestrator_beads_fabro/commands/test_session_wait_cli_budget.py`: 108
  - `tests/livespec_orchestrator_beads_fabro/commands/test_session_wait_deadline_safety.py`: 255, 513
  - `tests/livespec_orchestrator_beads_fabro/commands/test_session_wait_pane.py`: 196
  - `tests/livespec_orchestrator_beads_fabro/commands/test_session_wait_pane_cancel_races.py`: 131
  - `tests/livespec_orchestrator_beads_fabro/commands/test_session_wait_telemetry.py`: 326, 343, 344
  - `tests/test_provision_honeycomb_tdd_calibration.py`: 393
- **livespec-overseer** (26 hits in 12 files):
  - `tests/e2e-cli/test_codex_skill_picker.py`: 912, 916, 919
  - `tests/integration/test_overseer_start_public_herdr.py`: 336
  - `tests/integration/test_ready_arm_until_idle_live_tmux.py`: 674, 678, 683, 685, 687
  - `tests/test_detached_dispatch.py`: 74
  - `tests/test_herdr_absolute_bounds.py`: 271
  - `tests/test_herdr_live_server.py`: 430, 442
  - `tests/test_herdr_operator_delivery.py`: 55
  - `tests/test_lpm_acquisition_commit.py`: 120, 154
  - `tests/test_lpm_proof_runtime_effects.py`: 372, 418, 421, 433, 805, 811
  - `tests/test_lpm_review_fixes.py`: 551, 558
  - `tests/test_overseer_declare.py`: 270
  - `tests/test_supervisor_log_structured_events.py`: 224
- **livespec-driver-codex** (6 hits in 3 files):
  - `tests/dev-tooling/test_codex_config_write.py`: 94, 195
  - `tests/e2e-cli/test_codex_skill_picker.py`: 178, 182, 185
  - `tests/hooks/test_supervisor_completion_gate.py`: 611

Where the fleet half is carried. This clause binds only this repository: each member's work items are tier-judged against that member's own specification, so a dev-tooling clause cannot release them. livespec core is not the shared home either. Core's fleet-binding homes are Conformance-Pattern concerns (livespec `non-functional-requirements.md` §"Conformance Pattern"), and a concern is not adopted until all five of its slots are filled, one of which is a Verifier. This proposal deliberately defers the mechanical check that would be that Verifier (below). So the fleet half is carried by ONE PROPOSAL PER MEMBER REPOSITORY, each stating this same clause in that member's specification:
- livespec-orchestrator-beads-fabro: in `constraints.md`, section "Forbidden patterns".
- livespec-overseer: in `non-functional-requirements.md`, section "Constraints".
- livespec-driver-codex: in `non-functional-requirements.md`, section "Test discipline".

If a Verifier is later adopted, the four clauses can be folded into one core Conformance-Pattern concern.

Root-fix items, filed 2026-11-12 ~21:28Z through each repository's capture seam with a claim token. Each was routed pending-approval at the spec-change tier and waits for its own repository's clause. The cross-tenant links are recorded in prose on both sides (each item's description, and the dh3hub scope event of 21:28:51Z), never as a dependency edge.
- livespec-dev-tooling: livespec-dev-tooling-dqndbz (the failing test) and livespec-dev-tooling-rs6o3q (the other 19 files), both children of dh3hub.
- livespec-orchestrator-beads-fabro: bd-ib-4aq6ej.
- livespec-overseer: overseer-pzr23n.
- livespec-driver-codex: livespec-driver-codex-tjsdzj.

A mechanical check that refuses a short bound is deliberately not proposed here. A pattern-level check cannot tell a teardown wait or an expected-expiry window from a verdict-bearing bound without the per-line judgment above. A check can be reconsidered after the four root-fix items have closed and the remaining exempt lines show whether a static form is decidable.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "Testing approach", insert the following bullet immediately after the bullet that begins "**Host-state isolation of CLIs.**" and immediately before the bullet that begins "**Import-Linter.**". No heading is added, removed or renamed in that file.

- **Load-independent concurrency waits.** A test's verdict MUST NOT depend on how fast the host runs it. When a test waits for something the code under test is required to do — a worker thread or child process to finish, or a barrier, event or condition to be reached — it MUST wait either without a wall-clock bound or under a hang guard. A hang guard is one value the repository defines once for every such wait, MUST be no shorter than 120 seconds, and its expiry MUST fail the test as a hang that names what the test was waiting for. A test MUST NOT bound such a wait more tightly, as `join(3)` followed by `assert not worker.is_alive()`, `Barrier(2).wait(timeout=3)` or `assert event.wait(timeout=2)` do. An exception raised in a test's worker thread MUST fail that test, and the failure report MUST name that exception, never surface only as a missing or short result. Two kinds of wait are outside this rule: a teardown wait whose expiry falls through to a forced stop and decides no verdict, and a wait whose expiry is the outcome the test expects, such as a check that a blocked party has not yet proceeded. The rule applies to this repository's tests.
