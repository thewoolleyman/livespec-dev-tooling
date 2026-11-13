---
proposal: arc-listener-pods-run-only.md
decision: accept
revised_at: 2026-11-13T19:47:20Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-2:homelab-k8s-worker-nodes
---

## Decision and Rationale

Accepted as written (graded PASS by legacy-coordinator-agent). It states the always-on posture key, its node label, listener placement by that label, and the committed read-back, all implemented by livespec-dev-tooling#4414 and host-verified on livespec-dev-tooling-crvvxt.

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
proposal_stem: arc-listener-pods-run-only
content_digest: dedf113373b464016633effdd50ccdec98b5401c98e56f3af494c199c0688768
