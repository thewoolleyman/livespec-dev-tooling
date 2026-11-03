---
proposal: master-push-ci-routing.md
decision: accept
revised_at: 2026-11-03T11:49:25Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as proposed under the delegated decision mode. Measured (plan ci-runtime-and-cost research 003): livespec-dev-tooling master-push CI job wait p90 50.7 min vs pull_request 19.3 min over 24 h, because both events share one runs-on target, one scale set and one priority-0 Kueue queue. ARC creates the runner pod before job assignment, so only runs-on can separate them. A starved master makes the orchestrator master-CI preflight refuse every dev-tooling dispatch. The amendment keeps the hosted-literal floor, the manual-revert property, and the absence of any health probe, and leaves pull-request and merge-group routing unchanged. legacy-coordinator-agent ruled the change on 2026-11-03 (delegated tier). The capacity donor in the proposal's motivation was later re-ruled to livespec-orchestrator-beads-fabro (29 -> 26 churn slots); the spec text names no quota numbers, so it is unaffected. Carrier: livespec-dev-tooling-lzkzwb. Independent ratification review (sonnet, read-only): NO BLOCKERS.

## Resulting Changes

- constraints.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T11:49:16Z
verdict: NO BLOCKERS
proposal_stem: master-push-ci-routing
content_digest: d60ab8acb8d13876087282f287882843e3477b63bf80daccce61ece3b9c805c0
