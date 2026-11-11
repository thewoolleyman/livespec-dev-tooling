---
proposal: a-consumer-declares-its-gate-job-resources.md
decision: accept
revised_at: 2026-11-11T02:21:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted unmodified. The plan owner, the gate-job-resources seat (plan epic livespec-dev-tooling-ukoeah), reviewed the proposal. An integer gate_cpu is enough: the coordinator's point that a cpu request may sit below the worker count holds because the gate Job carries no cpu limit, so no fractional cores are needed. The Lane capacity clause's reading of ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml stays valid, because that file remains the committed source of the fleet gates flavors. This pass was first cut as v186 against v185; master's own v186 (a delegated pre-commit pass standing in for the pre-push gate) landed first, so the proposal's edits are re-applied on top of it. The only adjacency is v186's Evidence for the pre-push gate bullet beside the delegated pre-commit Absent verdict bullet, and both are kept unchanged apart from this proposal's appended configuration-refusal sentence. The spec-first bullets' owning work items: Declared gate resources -> livespec-dev-tooling-c3nd2h; Lane capacity -> livespec-dev-tooling-yznwz7; Replay Job size -> livespec-dev-tooling-lfkkaf; Gate lane headroom -> livespec-dev-tooling-brggiu. The eight new scenarios are registered as spec-first TODO rows in tests/heading-coverage.json owned by the same items.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T02:17:56Z
verdict: NO BLOCKERS
proposal_stem: a-consumer-declares-its-gate-job-resources
content_digest: bcebb53d015d5da4d93578d09027ef88c7740447f46a6c8b29588897b75b7a8a
