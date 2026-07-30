---
proposal: guarded-bd-path-fallback.md
decision: accept
revised_at: 2026-07-30T09:49:16Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: codex-gpt-5
---

## Decision and Rationale

The detector must distinguish an absent optional override from an unavailable command. Falling back to PATH when the override is unset matches the lifecycle-guarded host entry-point contract while preserving explicit override precedence.

## Resulting Changes

- contracts.md
