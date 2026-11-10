---
proposal: scratch-incident-observer-and-incident-scratch-ci.md
decision: accept
revised_at: 2026-11-10T02:44:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:expedited-incident-response-flag
---

## Decision and Rationale

Accepted as filed. Intake classed livespec-dev-tooling-32qdja and livespec-dev-tooling-7w757z spec-change tier (verdict-kind partial at v175): contracts.md §"Expedited incident execution" admitted a scratch-branch principal for proof or drill (v173) but stated no side-by-side installation, production invariance or committed teardown, and constraints.md §"CI matrix shape" stated no ci.yml push run on a scratch branch. The accepted clauses add both: a scratch installation runs beside production through the committed observer role with its own configuration, manifest, state, clone, port and units, publishes no public ingress, leaves production's rendered and running installation unchanged, is removed by a committed teardown and is never counted as master recovery capability; and ci.yml pushes to incident-scratch/** run the complete master job graph and policy with no master-only side effect, while other non-master pushes run nothing. Every master-facing obligation is unchanged. One scenario states both; its heading-coverage co-edit (spec-first TODO at the integration tier, owned by livespec-dev-tooling-32qdja, registered in the debt register) rides in the revise commit. Independent review (sonnet, 2026-11-10T02:41:41Z) reported NO BLOCKERS over the exact bytes after walking ci.yml, the incident_observer role and the observer code. Its non-blocking notes go to the implementers: test_ci_matrix_shape.py pins the master-only trigger and export-telemetry's push condition, so 7w757z changes both; a scratch observer receives no webhook deliveries and proves through forge polling; sharing production's secrets and recovery App credential is permitted; and production's receiver seeing scratch-branch workflow_job events needs an implementation test that its branch filter refuses them. Slot assigned by legacy-coordinator-agent after v176 (livespec-dev-tooling#3967).

## Resulting Changes

- contracts.md
- constraints.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T02:41:41Z
verdict: NO BLOCKERS
proposal_stem: scratch-incident-observer-and-incident-scratch-ci
content_digest: 013198dff554209eaea4ec5537e2eca695d5fdefff09f20431e4db96519ceab8
