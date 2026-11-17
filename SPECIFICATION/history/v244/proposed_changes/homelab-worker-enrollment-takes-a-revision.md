---
proposal: homelab-worker-enrollment-takes-a.md
decision: modify
revised_at: 2026-11-17T13:19:07Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Modified under delegated decision mode after the pre-merge doctor LLM pass walked the proposal's text through live code and returned three high findings: a zero gate share would still yield one gate (converge-worker-queues.sh floors whole gates at one), a zero CI share would be overridden by enroll-workload-classes.sh's at-least-one churn-slot floor, and a zero factory share was undefined because factory enrollment is only a label. The modification keeps the proposal's three rules (a measured split recorded in the host declaration, a zero share named, an invalid split refused before any write) and makes them implementable and unambiguous. The independent sonnet review returned NO BLOCKERS on the final bytes. This releases livespec-dev-tooling-dwewrc's spec-change tier (legacy-coordinator-agent, 2026-11-15). Re-cut onto current master for livespec-dev-tooling#4789 after the earlier cut's version was taken (legacy-coordinator-agent, 2026-11-16); the decision and the modifications are unchanged, and a fresh independent sonnet review returned NO BLOCKERS on the rebuilt bytes.

## Modifications

(1) A zero share means the class is not enrolled on that worker; its enrollment ends as 'Leaving a workload class' states, and the output names the class, its zero share and the reason. (2) The at-least-one-unit floor applies only to a share above zero, for churn slots and for whole gates alike. (3) Shares summing under one hundred percent leave the remainder unallocated as the host's measured reserve. (4) A share recorded for a class whose images do not publish the worker's architecture is ignored and named, with no rescaling; the existing lending sentence is scoped to the equal default. (5) The declaration is named: homelab-worker/hosts/<host>.env for the host in the homelab-worker.livespec.dev/host label, parsed without executing it; no host label or no recorded split keeps the equal default. (6) Refusals also cover an omitted enrolled class, a non-whole percentage and a missing reason. (7) The 'Automatic enrollment by workload class' clause gains a cross-reference naming the split as its one per-host input. (8) A third scenario covers the ignored share for a class the worker cannot run.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-17T13:18:39Z
verdict: NO BLOCKERS
proposal_stem: homelab-worker-enrollment-takes-a
content_digest: 1c685c302a2b95b8ec075a055505847d446a6b8b02a501ba25a455830e27d0fa
