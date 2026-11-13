---
proposal: the-k3s-agent-restart-play.md
decision: accept
revised_at: 2026-11-13T19:47:20Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-2:homelab-k8s-worker-nodes
---

## Decision and Rationale

Accepted as written (graded PASS by legacy-coordinator-agent, livespec-dev-tooling#4309). It states the agent restart play and that an arc-systems AutoscalingListener pod is not workload for its idle check; livespec-dev-tooling-6yxdxu owns the implementation.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T19:45:58Z
verdict: NO BLOCKERS
proposal_stem: the-k3s-agent-restart-play
content_digest: eb6c445305a97d1799237a88a6d0b5f2f11f46e398e19b425442a5276cd04f49
