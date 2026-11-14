---
proposal: branch-protection-alignment-retries-a.md
decision: accept
revised_at: 2026-11-14T19:53:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as proposed (livespec-dev-tooling-zx2ouv, carrying livespec-dev-tooling-lr3tfv). A failed ruleset read is retried up to four attempts with growing waits summing to at most 30 seconds, and ruleset_unreadable is reported only when every attempt failed, naming the endpoint and the first and last failure. Measured cause: a transient forge read refused a correct gate on 2026-11-12 12:53:39Z. legacy-coordinator-agent ruled under R301 that this plan's revise carries the topic because its own seat is drained.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T19:50:56Z
verdict: NO BLOCKERS
proposal_stem: branch-protection-alignment-retries-a
content_digest: 0b6b3f9ee964677b6bda32f67152848a2194fdea47e5d6f5ca7a98610b436d8c
