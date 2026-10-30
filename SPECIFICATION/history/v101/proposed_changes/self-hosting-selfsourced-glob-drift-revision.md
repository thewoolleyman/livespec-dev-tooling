---
proposal: self-hosting-selfsourced-glob-drift.md
decision: accept
revised_at: 2026-10-30T20:12:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as written. Clause (ii) of §"Self-hosting" now names the uses: ref format's full scan set by reference instead of restating a stale *.yml glob, so it cannot drift again. The independent review confirmed the shipped release-time self-reconcile already discovers pins through the full autodiscovery walk, so no behaviour changes. Decided under delegated revise_decision_mode by the delegated-gate-fleet-rollout seat.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-30T20:02:36Z
verdict: NO BLOCKERS
proposal_stem: self-hosting-selfsourced-glob-drift
content_digest: 772cceae6355afe4e00dbe3a2ae3b7959de6de2eacd53f4ee446c3c482fc8e5f
