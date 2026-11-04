---
proposal: homelab-worker-nodes.md
decision: accept
revised_at: 2026-11-04T17:10:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratifies the portable homelab worker's governing contract so plan homelab-k8s-worker-nodes (epic livespec-dev-tooling-ko26ez, research/004) can file Phase C children whose Definitions of Done reference it. Placement is non-functional-requirements.md: the worker is this repository's own CI and factory infrastructure. Every clause is observable and each carries a scenario. The independent reviewer reported no blockers; its non-blocking suggestions (naming the delegated cgroup controllers, citing the image convention section) are left for a later revise once Phase C measures them.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T17:09:31Z
verdict: NO BLOCKERS
proposal_stem: homelab-worker-nodes
content_digest: 60407be020e41e3272f764506cee4de37f0f501b3226363807eb584c05f94400
