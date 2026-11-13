---
proposal: arc-listener-pods-spread-across-always-on-nodes.md
decision: accept
revised_at: 2026-11-13T19:47:20Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-2:homelab-k8s-worker-nodes
---

## Decision and Rationale

Accepted as written (graded PASS by legacy-coordinator-agent, livespec-dev-tooling#4490). Applied after arc-listener-pods-run-only, whose paragraph and scenario it names. It is spec-first; livespec-dev-tooling-zrsyfp owns the implementation.

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
proposal_stem: arc-listener-pods-spread-across-always-on-nodes
content_digest: f4186ebb259a0ccef888ae7b919e79cd8ae6501d9d40c04c69a31551b3900479
