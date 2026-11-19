---
proposal: factory-workspace-sweep-safety-guarantees.md
decision: accept
revised_at: 2026-11-19T19:03:53Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: ci-runtime-and-cost-session
---

## Decision and Rationale

Accepted as filed under R301 on legacy-coordinator-agent's ruling of 2026-11-19: the clause states data-loss safety guarantees for the factory-host workspace sweep (never remove a workspace whose item is blocked, needs-human or in acceptance, whose tenant is unreadable, with no run end time or under 24 hours old; archive with a verified sha256 before removal; report-only default), which the 2026-11-16 criteria send to the spec. No ratified clause stated them. No design-record contradiction. The first review draft of the resulting files was refused for a truncated non-functional-requirements.md; the rebuilt bytes were re-reviewed with NO BLOCKERS.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-19T19:03:29Z
verdict: NO BLOCKERS
proposal_stem: factory-workspace-sweep-safety-guarantees
content_digest: 661edb5cd00e8a994d6ecccfa1272f5ccbd87d130ac2211f33e8a7fb6bcc372d
