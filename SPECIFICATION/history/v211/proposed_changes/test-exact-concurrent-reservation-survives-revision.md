---
proposal: test-exact-concurrent-reservation-survives.md
decision: modify
revised_at: 2026-11-13T13:01:06Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified on legacy-coordinator-agent's grade of livespec-dev-tooling#4518 (PASS-WITH-ONE-FIX, 2026-11-13). The proposal's bullet lands verbatim, as the coordinator's queue slot for dqndbz (ruled ~09:38Z: v209, o4hkgh, then dqndbz, then rgiufy). The proposal was graded PASS and merged as livespec-dev-tooling#4395. Every fact it cites still holds on master 84370f014: test_incident_recovery_journal.py still bounds its reserve threads with Barrier(2).wait(timeout=3), join(3) and assert not worker.is_alive(), and _HANG_GUARD_SECONDS = 180 still stands. The bullet is a contributor-only testing discipline, so non-functional-requirements.md is its home, and it binds this repository's tests only; the fleet half is carried by one proposal per member repository. No H2 heading is added, removed or renamed, so tests/heading-coverage.json is unchanged.

## Modifications

One sentence is appended to the end of the accepted bullet, made binding by the coordinator's grade (with its later addition that the script-driving subprocess timeouts count among the breaking sites): "This bullet is spec-first: tests in this repository still bound such waits more tightly than a hang guard, among them the fixed per-call `subprocess` timeouts of tests that drive a script or command-line entry point and the thread waits of `test_exact_concurrent_reservation_survives_restart_and_conflicting_bytes` in `tests/livespec_dev_tooling/test_incident_recovery_journal.py`, or let a worker thread's exception surface only as a short result, and work items livespec-dev-tooling-dqndbz and livespec-dev-tooling-rs6o3q own the change, except in `tests/spec/test_homelab_worker_*.py`, which plan homelab-k8s-worker-nodes (epic livespec-dev-tooling-ko26ez) owns." Without it, the clause would assert a conformance the tree does not yet have. The proposal's sweep counted 73 thread and barrier hits in 20 files, and 40 real script-driving subprocess calls bound their wait below 120 s. fleet-flaky-tests' inventory, recorded on dqndbz, names about 120 subprocess timeout sites. The homelab worker files are excluded because that plan owns them (fleet-flaky-tests, on the coordinator's ruling). The sentence follows the form of the neighbouring Host-state isolation of CLIs bullet's spec-first sentence.

## Resulting Changes

- non-functional-requirements.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T13:00:30Z
verdict: NO BLOCKERS
proposal_stem: test-exact-concurrent-reservation-survives
content_digest: f967e81c390e207f1a6e039d63594c4b6642c59fb6bd092a201408c4a30c0854
