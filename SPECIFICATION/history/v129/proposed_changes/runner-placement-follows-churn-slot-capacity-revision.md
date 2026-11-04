---
proposal: runner-placement-follows-churn-slot-capacity.md
decision: modify
revised_at: 2026-11-04T10:23:58Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5 (session kubernetes-sandbox-backend)
---

## Decision and Rationale

Modified, not accepted as filed. The clause text is ratified exactly as proposed. The post-revise LLM doctor on the first cut (v129, closed unmerged as PR #3381, head preserved at refs/heads/backup/spec-revise-runner-placement-v129) found two of the clause's MUSTs with no scenario (doctor-llm-objective-delta-uncovered-behavior): the free-churn-slot restriction and capacity being the only per-node limit. It also found an undefined scenario term ('the runner-host label') and a scenario Then-line not caused by its When step. This modification adds scenarios for both MUSTs, names the k3s-role=arc-runner-host label, and splits the default-profile requirement into its own scenario. Every new scenario has a heading-coverage TODO naming the integration tier and owner livespec-dev-tooling-mtvxde. Dismissed doctor warnings: (d) 'where churn slots in use are read from' is undefined. Dismissed because the CI-facilities posture clause defines capacity as the churn-slot units a node advertises, standard extended-resource accounting fixes in-use as the requests of pods bound to the node, and mtvxde's Definition of Done asserts that source. (h) no tie-break between nodes with equal fractions. Dismissed because any tie-break satisfies the clause and the choice carries no observable requirement. Decision ordered by legacy-coordinator-agent under R301.

## Modifications

Added three scenarios: a runner pod is never placed on a node with no free churn slot; a node takes runner pods up to its declared churn-slot capacity and no fewer; and a pod that is not a CI runner pod keeps the default scheduler profile (split out of the original scenario's last Then line). Named the `k3s-role=arc-runner-host` label in place of 'the runner-host label'. Added heading-coverage TODO rows for the three new scenarios, owned by livespec-dev-tooling-mtvxde at the integration tier, and regenerated the debt register. The clause text is unchanged from the proposal.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T10:23:24Z
verdict: NO BLOCKERS
proposal_stem: runner-placement-follows-churn-slot-capacity
content_digest: c1c5b949996f143852f810829ec7e80b4740f01706a04961d1301687ed752d5b
