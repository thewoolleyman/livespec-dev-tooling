---
proposal: the-reconcile-runs-host-timer-role.md
decision: accept
revised_at: 2026-11-18T21:31:18Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Coordinator (legacy-coordinator-agent, R301) authorized the decision on the merits. The proposal states a contract the role makes to the hosts that dispatch factory runs and a promise to operators (one committed owner of the reconcile-runs timer, one service per tenant, a serial sweep, a bounded pass retried by the next sweep, a run-time credential wrapper, a dead-man marker that is created but never refreshed), so it is spec scope and not internal. It contradicts no ratified clause: the only existing mention is the staleness-alert scenario. An independent read-only sonnet review of the exact bytes walked each MUST against the committed role ansible/roles/reconcile_runs and returned NO BLOCKERS. The five new heading-coverage rows are spec-first TODO rows naming the consumer tier and owned by livespec-dev-tooling-lo25nk, filed through capture-work-item for this purpose.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-18T21:30:37Z
verdict: NO BLOCKERS
proposal_stem: the-reconcile-runs-host-timer-role
content_digest: 2f3c538b3a04a56c660f31724f0a2efcbae987d75047d4deddb1482f6ce15887
