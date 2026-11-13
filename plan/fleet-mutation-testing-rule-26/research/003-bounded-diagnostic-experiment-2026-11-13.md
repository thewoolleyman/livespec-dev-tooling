# Bounded diagnostic experiment inputs

Recorded 2026-11-13 from RULE26-DAY-RESCOPE-20261113 and coordinator grade 01a1d462-2aa2-7267-b814-35ad5cba34ed on epic livespec-dev-tooling-oi2two. These are settings of this plan's first experiment; the proposed contract enforces manifest-declared inputs without fixing these values for other callers.

The target source revision is b26c3dc2decf8ea355e247a7a17a39b45d9a5095. Freeze its catalogue and the actual executing engine digest after the provenance repair is adopted. The seed is `rule26-day-probe-v1:b26c3dc2`. Select one mutant in each of these six distinct source modules using the declared deterministic SHA-256 minimum method, with identifier tie-breaking; the engine must recompute and validate the selection before execution.

| Risk area | Module under .claude-plugin/scripts/livespec_orchestrator_beads_fabro/ |
| --- | --- |
| Dispatch authorization | commands/_dispatcher_admission_eligibility.py |
| Claim-token ownership | _store_claim_token_creation.py |
| Lifecycle transitions | commands/_drive_valve_predicates.py |
| Acceptance/reconciliation | commands/_dispatcher_reconcile_merged.py |
| Plan result/budget advancement | commands/_plan_progress_decision.py |
| Proof identity/verification | commands/_dispatcher_proof_identity.py |

The experiment manifest budgets are `max_mutants: 6`, `max_workers: 2` and `max_elapsed_seconds: 79200` (22 hours). The committed launch must request/limit the two workers and enforce the absolute deadline including setup; the engine receives the remaining time rather than another 22 hours. This is an input plan, not a completed manifest: actual identifiers and frozen catalogue/engine digests remain to be generated after ratification and implementation.

The stopped full run measured 4.784 mutants/hour across 12 workers. The six-mutant/two-worker estimate is 12.3 hours, or 19.8 hours with doubled execution time. Those estimates are advisory and never extend the absolute cap.

For this experiment, the supervisor is the plan's explicitly named operator session that owns the authorized launch, watches its Job and PVC through a bounded native background continuation, and can invoke the committed job-only stop surface. Name that session and its monitoring deadline on oi2two before launch. The first pair means the first two selected mutants with final outcomes from the two-worker execution. Once both finish, the supervisor projects the remaining runtime from the elapsed invocation time and observed outcomes; if the projection exceeds the time remaining, stop through the committed job-absent route while retaining the PVC. An unapplied result stays unapplied and is never replaced by a new selection.

No mutation Job, automatic successor or pruning is authorized by this note. hold-gmktec and S1-S5 remain binding. Ratification, implementation, fixture proof, launch authorization and hold clearance remain prerequisites. The partial diagnostic does not discharge fqnbtd's full-report obligation or plan A1/A3/A4/A7/A8. The existing PVC and old cache provenance restrictions remain as recorded in the ledger.
