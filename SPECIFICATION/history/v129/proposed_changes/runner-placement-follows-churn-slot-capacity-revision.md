---
proposal: runner-placement-follows-churn-slot-capacity.md
decision: modify
revised_at: 2026-11-04T10:37:39Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5 (session kubernetes-sandbox-backend)
---

## Decision and Rationale

Modified, not accepted as filed. The clause text is ratified exactly as proposed. The post-revise LLM doctor on the first cut (v129, closed unmerged as PR #3381, head preserved at refs/heads/backup/spec-revise-runner-placement-v129) found two of the clause's MUSTs with no scenario (doctor-llm-objective-delta-uncovered-behavior): the free-churn-slot restriction and capacity being the only per-node limit. It also found an undefined scenario term ('the runner-host label') and a scenario Then-line not caused by its When step. This modification adds scenarios for both MUSTs, names the k3s-role=arc-runner-host label, and gives the scheduler-profile requirement its own scenario: runner pods name the committed runner scheduler profile after the CI stack converge, while factory and gate pods keep the default profile. A second LLM doctor pass on an intermediate cut (head preserved at refs/heads/backup/spec-revise-runner-placement-v129-modify1) found that the profile-selection sentence still had no scenario, that one Then-line put the negation on its subject, and that one Given treated the cluster-wide profile as per-node. All three are fixed here. The independent review of that fix found that the capacity scenario's Given ('no other node has a lower churn-slot in-use fraction') held only at the start of the sequence, so its Then could contradict the lowest-fraction preference. The Given now reads 'no other pool node has a free churn slot', which holds throughout. A third LLM doctor pass found that the 'default scheduler profile MUST stay unchanged' sentence was still untested (a converge could change the default profile's plugins while every pod still named the right profile), and that the memory half of 'CPU and memory requests MUST NOT decide' had no Given. The profile scenario now asserts that the default profile carries the same plugin configuration as before the converge. The ordering and capacity scenarios now set up both CPU and memory pressure. The free-slot scenario's heading drops a clause that could not occur, and its redundant MUST NOT line is removed. Every new scenario has a heading-coverage TODO naming the integration tier and owner livespec-dev-tooling-mtvxde. Dismissed doctor warnings: (d) 'where churn slots in use are read from' is undefined. Dismissed because the CI-facilities posture clause defines capacity as the churn-slot units a node advertises, standard extended-resource accounting fixes in-use as the requests of pods bound to the node, and mtvxde's Definition of Done asserts that source. (h) no tie-break between nodes with equal fractions. Dismissed because any tie-break satisfies the clause and the choice carries no observable requirement. Decision ordered by legacy-coordinator-agent under R301.

## Modifications

Added three scenarios: a runner pod is never placed on a node with no free churn slot; a node takes runner pods up to its declared churn-slot capacity and no fewer (its Then-line reads 'a CPU or memory request of a non-runner pod on it MUST NOT stop a runner pod'); and runner pods select the committed runner scheduler profile while every other pod keeps the default profile, which replaces the original scenario's last Then line and states the profile as cluster-wide. Named the `k3s-role=arc-runner-host` label in place of 'the runner-host label'. Added heading-coverage TODO rows for the three new scenarios, owned by livespec-dev-tooling-mtvxde at the integration tier, and regenerated the debt register. The clause text is unchanged from the proposal. The default-profile scenario asserts that the default profile's plugin configuration is unchanged by the converge, and the ordering and capacity scenarios set up both CPU and memory pressure.

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
reviewed_at: 2026-11-04T10:37:10Z
verdict: NO BLOCKERS
proposal_stem: runner-placement-follows-churn-slot-capacity
content_digest: a9d3ca7b98b3dc819ff0e42d7962ddff74e2d9a4f5c4357caf25dff08d654de2
