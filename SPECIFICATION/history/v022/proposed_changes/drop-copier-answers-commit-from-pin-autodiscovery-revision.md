---
proposal: drop-copier-answers-commit-from-pin-autodiscovery.md
decision: accept
revised_at: 2026-06-27T16:03:29Z
author_human: Test <test@example.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accept: drop the `.copier-answers.yml` `_commit` pin format from contracts.md §"Pin autodiscovery rules". `_commit` is copier render-provenance, not a version pin; the dev-tooling code (livespec-zs22.7.9.6 part 1, dt v0.26.0) already dropped it from the autodiscovery walk so the fan-out stops poisoning the marker. This revision keeps the governed spec in lockstep with the implementation.

## Resulting Changes

- contracts.md
