---
proposal: self-hosted-routing-guarded-merge-group.md
decision: modify
revised_at: 2026-11-14T20:37:51Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified under delegated revise authority in the dev-tooling revise slot legacy-coordinator-agent sequenced for plan stale-base-merge-options (livespec-dev-tooling epic xowhol), cut as v225 directly after expedited-incident-response-flag's v224 revise. The proposal was graded PASS by throughput-plans-coordinator under rulings 1-5. One substantive modification: condition (a) of the guarded merge_group exception now also requires the guard job to be the workflow's first job, so every other job in the workflow lists it in needs:, directly or through another job that does. The ratified upstream livespec NFR (livespec v246, livespec#3223, "Event routing") defines the guarded class by "the workflow's first job" and makes every gating job's self-hosted route depend on "that first job's output". The proposal's (a)+(b) required only that gating jobs need the guard, which would admit a workflow whose non-gating jobs run before or beside the guard. The tightening keeps the dev-tooling check no looser than the livespec rule it enforces. Everything else is carried as filed: the self_hosted_routing subsection with conditions (a)-(f), the five branch_protection_alignment rules (merge_queue_absent, merge_queue_concurrency_below_floor, merge_queue_method_not_rebase, merge_queue_bypass_path, fork_approval_below_strictest) with the QUEUE_REQUIRED_REPOSITORIES constant, and the two scenarios. A second, non-spec departure is in the revise commit: the proposal asked for unit-tier spec-first heading-coverage rows, and the rows name the consumer tier instead, because this repository's scenario rows run at the consumer tier (scenario_tiers); livespec-dev-tooling-mvqo6h owns both.

## Modifications



## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T20:36:04Z
verdict: NO BLOCKERS
proposal_stem: self-hosted-routing-guarded-merge-group
content_digest: ec387b3c0d945b526df52fdd3cf1d1e27cc8d19eeeea62b41f4189e9babbbb97
