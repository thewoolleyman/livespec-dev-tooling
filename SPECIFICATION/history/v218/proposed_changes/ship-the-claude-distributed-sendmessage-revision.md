---
proposal: ship-the-claude-distributed-sendmessage.md
decision: modify
revised_at: 2026-11-14T09:31:10Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:distributed-send-message
---

## Decision and Rationale

Accepted with modifications. It records the rule plan distributed-sendmessage shipped in livespec-dev-tooling#4595 and proved live on 2026-11-14: seats message by SendMessage, never by typing into a Claude seat's pane, enforced by the claude_distributed_sendmessage managed-policy role. The scenario is covered at the consumer tier by tests/consumer/test_claude_messaging_guards.py.

## Modifications

Six changes, all from the independent sonnet ratification review of the first draft:
- The admit list said own-pane and no-agent input was admitted for tmux as well, but the guard grants those exemptions only to herdr. The list is now scoped to herdr text input, and key-only send-keys (herdr or tmux) is a separate sentence.
- The Scope paragraph limited the section to the dev host. It gains one sentence extending the messaging rule to every interactive host.
- The guard's deliberate fail-open on its own internal error is now stated.
- 'every interactive session joins Remote Control' becomes 'every interactive session signed in to claude.ai'.
- The own-pane admission is marked as local-herdr only.
- The scenario uses this file's plain Given/When/Then paragraphs instead of bullets.
The heading-coverage reason also names the sibling tests.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T09:30:30Z
verdict: NO BLOCKERS
proposal_stem: ship-the-claude-distributed-sendmessage
content_digest: 424eb4d3b3e054b1968febb8516e04674d74ae1a08e33accb7ae441be0d3977a
