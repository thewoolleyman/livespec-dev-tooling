---
proposal: neutral-shared-hook-body-verifier.md
decision: accept
revised_at: 2026-07-13T10:17:31Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Independent Fable review returned NO BLOCKERS. Documents the shipped Neutral-shared-hook-body Verifier + neutral_hook_body_path role key in dev-tooling's contracts.md, realizing the five-slot expansion S1 deferred here (livespec core contracts.md 'Cross-Driver single-sourcing'). Names, exit codes, and failure modes verified byte-for-byte against the merged S2 code (PR #367, released v0.44.0). One H3 added, no H2 change.

## Resulting Changes

- contracts.md
