---
proposal: retire-auto-update-branches-ref.md
decision: accept
revised_at: 2026-06-22T20:42:36Z
author_human: E2E Test <e2e-test@example.com>
author_llm: retire-auto-update-ref
---

## Decision and Rationale

Accept verbatim: the auto-update-branches.yml workflow has been removed family-wide, so contracts.md must no longer cite it as an App-token precedent. The reworded sentence preserves the App-token-over-GITHUB_TOKEN rationale while pointing at the surviving precedents (auto-enable-merge.yml and the bump-pin shim workflows).

## Resulting Changes

- contracts.md
