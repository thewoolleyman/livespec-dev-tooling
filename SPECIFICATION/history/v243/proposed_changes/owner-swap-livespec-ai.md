---
topic: owner-swap-livespec-ai
author: claude-sonnet-5-5
created_at: 2026-11-17T04:39:25Z
---

## Proposal: Fleet repository and image references name the livespec-ai owner

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Replaces the retired owner thewoolleyman with livespec-ai in every repository slug (uses: refs, git URLs, bump-PR title) and every ghcr.io image reference in spec.md, contracts.md and scenarios.md. No behaviour changes; the references now name where the repositories and the fabro-sandbox image actually live.

### Motivation

The fleet moved to the livespec-ai organization (plan stale-base-merge-options, epic livespec-dev-tooling-xowhol, DoD 7). The ratified text still names thewoolleyman/livespec-dev-tooling and ghcr.io/thewoolleyman/livespec-fabro-sandbox, which no longer match the repository's own workflows. Left unchanged: the retired App bot login thewoolleyman-factory-bot in contracts.md (the workflows still recognise both spellings, a separate change) and thewoolleyman/otel-collector in non-functional-requirements.md (that repository has not moved).

### Proposed Changes

In spec.md, contracts.md and scenarios.md, replace `thewoolleyman/livespec-dev-tooling` with `livespec-ai/livespec-dev-tooling` and `ghcr.io/thewoolleyman/livespec-fabro-sandbox` with `ghcr.io/livespec-ai/livespec-fabro-sandbox`, verbatim otherwise. No heading changes.
