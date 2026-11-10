---
proposal: homelab-worker-ci-overflows-to.md
decision: accept
revised_at: 2026-11-10T05:21:26Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:homelab-k8s-worker-nodes
---

## Decision and Rationale

Accepted as written under delegated mode. It records route (a) of plan homelab-k8s-worker-nodes (research/010), which legacy-coordinator-agent gave GO at about 03:3xZ on 2026-11-10 on epic livespec-dev-tooling-ko26ez: CI reaches a container worker only as a second Kueue churn-slot flavor, after the amd64 fleet flavor is full, and never by pinning a lane. The sonnet ratification reviewer found no blockers; its non-blocking findings (same queues not same flavor, measured split governs over equal split, eligibility source of truth) are for livespec-dev-tooling-eorpen's implementation to record.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T05:18:17Z
verdict: NO BLOCKERS
proposal_stem: homelab-worker-ci-overflows-to
content_digest: 01db25e6c185b5a825c85ad0f99e1b5437e2f6e41f01776e5283e55b938fef67
