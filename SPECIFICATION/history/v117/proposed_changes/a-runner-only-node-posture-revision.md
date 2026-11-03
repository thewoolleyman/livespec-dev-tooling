---
proposal: a-runner-only-node-posture.md
decision: modify
revised_at: 2026-11-03T00:36:40Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Delegated decision by fleet coordinator legacy-coordinator-agent under R301 delegated revise authority, 2026-11-03 (relayed by cross-session message to the kubernetes-sandbox-backend lane): ACCEPT the runner-only posture as proposed, including the Rehearsed-before-trusted clause, narrowed so that it applies ONLY to a transition that touches no storage tier. A none to runner-only move carves and empties nothing, so an empty-storage rehearsal would exercise none of what changed while destroying hp-xubuntu's live sandbox stores. The provisioning apply that carries the node to a CI job executing on it is the rehearsal of what changed. A move to or from full still requires the empty-storage rehearsal, and the ledger item names the apply run, the pod and node, and the job id. Independent sonnet ratification review returned BLOCKERS on the first draft (undefined profile keys and terms, rehearsal narrowing without a scenario, several behaviours without scenarios). All were fixed: profile keys and terms defined, seven scenarios added, and the posture move distinguished from a rebuild. The second review returned NO BLOCKERS on these exact bytes. No design record is contradicted: the hp-xubuntu profile header itself records that opening the node later is a profile edit plus an apply. Implementation: livespec-dev-tooling-zreev4.

## Modifications

Narrowed the Rehearsed-before-trusted exception to none<->runner-only moves only, with the ledger evidence named. Defined CI_NODE_FACILITIES, ADMISSION_CAPACITY_C, NODE_TAINTS, RUNNER_WORKVOL_DIR, CI-closing taint and cohort churn-slot quota. Added the refusal of an empty RUNNER_WORKVOL_DIR, and the statement that a posture move is not a rebuild. Added seven scenarios beyond the proposal's five: unknown posture, empty work-volume directory, closed profile with capacity or no taint, hook plus factory label, cache reach over the node network, none-to-runner-only rehearsal, and the empty-storage rehearsal still required for full.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T00:35:50Z
verdict: NO BLOCKERS
proposal_stem: a-runner-only-node-posture
content_digest: eaac62763eba80c93ad1a8368fb2ea8610900d8362e3ab34f9083ce541d4a9b7
