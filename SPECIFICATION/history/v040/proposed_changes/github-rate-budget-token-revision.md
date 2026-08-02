---
proposal: github-rate-budget-token.md
decision: modify
revised_at: 2026-08-02T23:05:55Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: openai-codex-gpt-5
---

## Decision and Rationale

The incident evidence and independent Opus audit establish a recurring shared-installation quota failure, and the proposed bounded preflight preserves token scope while replacing reactive replays with deterministic waiting. The proposal is modified only to use the current v3 input name client-id instead of the deprecated app-id and to fully specify defaults, timing, retries, error markers, workflow placement, and acceptance scenarios.

## Modifications

Use actions/create-github-app-token@v3 client-id rather than its deprecated app-id alias; define exact defaults, deterministic jitter, bounded retry/wait behavior, error markers, call-site thresholds, and five Gherkin acceptance scenarios.

## Resulting Changes

- spec.md
- contracts.md
- scenarios.md
