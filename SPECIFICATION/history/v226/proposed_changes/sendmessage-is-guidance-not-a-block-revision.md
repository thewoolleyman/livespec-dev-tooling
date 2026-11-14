---
proposal: sendmessage-is-guidance-not-a-block.md
decision: accept
revised_at: 2026-11-14T21:23:17Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:distributed-send-message
---

## Decision and Rationale

Accepted. Maintainer ruling 2026-11-14: sessions must not be prevented from typing into panes; SendMessage is explicit guidance. livespec-dev-tooling#4707 stops the claude_distributed_sendmessage role wiring the pane-input guard, removes the guard from hosts and rewrites the managed CLAUDE.md guidance; this revision makes the spec say the same.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T20:39:40Z
verdict: NO BLOCKERS
proposal_stem: sendmessage-is-guidance-not-a-block
content_digest: 18af231df6ae0f9a93067cf4f2e056fa3c0da1b14ea8d5390d747e5cf068ce19
