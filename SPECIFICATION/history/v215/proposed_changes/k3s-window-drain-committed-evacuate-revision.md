---
proposal: k3s-window-drain-committed-evacuate.md
decision: accept
revised_at: 2026-11-13T19:47:20Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-2:homelab-k8s-worker-nodes
---

## Decision and Rationale

Accepted as written (graded PASS by legacy-coordinator-agent). It states the committed node hold, the evacuation play and the lost-node play that ansible/k3s-window-drain.yml already implements (livespec-dev-tooling#4404), and adds their four scenarios. No existing sentence changes.

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
proposal_stem: k3s-window-drain-committed-evacuate
content_digest: d9c18c43436616d45ff3eb6b4bb0a57bd99c101205e36d65ad009f0822410195
