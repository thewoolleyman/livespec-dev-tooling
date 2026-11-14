---
proposal: a-pin-bump-pr-whose.md
decision: accept
revised_at: 2026-11-14T19:53:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as proposed (livespec-dev-tooling-m5cpnl). It states the stale-base refresh of an open bump PR: reset the bot-owned branch to the default tip, re-run the same rewrite for the PR's source and tag, and push with --force-with-lease, so every discovered pin on the refreshed head names the target tag; pin-freshness is the backstop for the refresh-to-merge race, and a no-op refresh pushes nothing. Measured cause: livespec-overseer master red at 88221220 after bump PR #2966 merged with a stale image line. Revise order ruled by legacy-coordinator-agent.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T19:50:56Z
verdict: NO BLOCKERS
proposal_stem: a-pin-bump-pr-whose
content_digest: 52f50a85adfe0e7d3f37e8ba8ae3bf04ef9a4ce4f486d64e778d510cb1f1af51
