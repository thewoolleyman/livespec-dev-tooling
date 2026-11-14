---
proposal: gate-lane-reconciler-unread-reading-alarm.md
decision: accept
revised_at: 2026-11-11T17:03:35Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accept as filed. The gate placement reconciler (livespec-dev-tooling-gvo7fa) is not yet installed on any node, and its unread-reading fallback is silent to an operator: one unread lane reading returns the whole gates queue to static order and leaves only a log line. kubernetes-sandbox-backend measured the same shape on the factory-pressure steer, which stayed disabled for two days unnoticed; its fix is a named ALARM line plus exit status 3, so the unit reports failed. legacy-coordinator-agent ruled on 2026-11-11 (~14:42Z) that the alarm is a new item, livespec-dev-tooling-ln7q3b, rather than a rework of gvo7fa, and that ln7q3b merges before the reconciler is installed on any node. The two sentences extend the existing fallback rule in contracts.md §"Delegated pre-push gate" bullet "Placement by node pressure" without changing it, and the new scenario sits beside the existing fallback scenario, which still holds. The co-edited tests/heading-coverage.json row is a spec-first consumer-tier TODO owned by ln7q3b, registered in the debt register in the same commit. Delegated decision with an independent sonnet review of the exact bytes.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T17:03:01Z
verdict: NO BLOCKERS
proposal_stem: gate-lane-reconciler-unread-reading-alarm
content_digest: 3c53fd060cdd3be40f67edbd434ae19e4158a8ed5e73feca5de4caf937c40f24
