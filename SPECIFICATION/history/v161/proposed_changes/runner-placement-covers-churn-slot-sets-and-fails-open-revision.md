---
proposal: runner-placement-covers-churn-slot-sets-and-fails-open.md
decision: modify
revised_at: 2026-11-08T19:12:53Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Two live scale sets (poweredge-xubuntu-k3s and the macbook homelab worker) request no churn slot and cannot follow a slot-fraction rule, and the ratified clause said nothing about a down scheduler, while the fail-open reconciler (livespec-dev-tooling#3717) is live. Code and spec would otherwise disagree. Carries livespec-dev-tooling-mtvxde.

## Modifications

Doctor LLM phases on the draft, walked through live state 2026-11-07 (ci-runner-scheduler 2/2 ready, 14 pods naming it, reconcile-runner-scheduler-fail-open.timer active, the exempt sets' values carrying no churn-slot request): (1) the existing scenario 'runner pods select the committed runner scheduler profile and every other pod keeps the default profile' said every CI runner pod names the runner scheduler, contradicting the exemption, so its body is narrowed to a runner pod that requests a churn slot, with its heading unchanged; (2) the reconciler re-points the runner and deletes the pod and ARC then recreates it, so the 30-second bound is stated on that act and the recreation follows from it (worst case 90 s after the scheduler drops, inside the 120 s unscheduled-runner threshold); (3) the fail-open rule became its own paragraph, 'Runner placement fails open while its scheduler is down', for readability; the scheduler-profile sentence and the per-node limit now say 'those runner pods'.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T19:12:04Z
verdict: NO BLOCKERS
proposal_stem: runner-placement-covers-churn-slot-sets-and-fails-open
content_digest: 44c1d02869f5082970c47a2efba53ffd6c5a81d3cc16e6115aef912aab3d1810
