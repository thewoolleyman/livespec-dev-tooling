---
proposal: sweep-fleet-hosts-daily-for.md
decision: accept
revised_at: 2026-11-16T19:07:24Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5 (no-local-agent-memory seat)
---

## Decision and Rationale

Accepted as filed: graded PASS by legacy-coordinator-agent on livespec-dev-tooling#4774 (merged 2026-11-15T20:24:56Z as 4c20cd474), after the grade required that a migration item never copy the file's content, and after a full doctor LLM pass. Carries livespec-dev-tooling-jk54mp (plan no-local-agent-memory). The new section lands between 'Dev host disk retention' and 'Fleet manifest adopter profiles'; its six scenarios precede 'a managed hook refuses a local agent-memory write on an interactive host'. Re-cut as v239 on master 4d7a9e71d after revise v238 (cite-the-core-heading-for-the-master, livespec-dev-tooling-mafayz) took v238, following earlier re-cuts after v235, v236 and v237; the text is unchanged. No conflict with v234's interactive_claude_macs Scope amendment: the sweep only reads hosts over ssh and converges nothing on them. The independent sonnet review of the re-cut bytes reported NO BLOCKERS.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-16T19:06:57Z
verdict: NO BLOCKERS
proposal_stem: sweep-fleet-hosts-daily-for
content_digest: a6c3e0e0c40dc8d5bbc5fdfe8f64403c6fd253a6076154ccb9f21b4a465d409a
