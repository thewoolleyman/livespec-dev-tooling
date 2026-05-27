---
proposal: no-stale-revise-branches-check.md
decision: accept
revised_at: 2026-05-27T06:35:47Z
author_human: E2E Test <e2e-test@example.com>
author_llm: claude-opus-4-7
---

## Decision and Rationale

Impl→spec ratification of the no_stale_revise_branches shared check (impl already landed via PR #21, li-hy6pfb closed). Adds the check to §"Shared check inventory" CI-alignment family, specs its algorithm/inputs/outputs/override flag, and documents the canonical_branch carve-out from the consumer configuration schema (read directly from .livespec.jsonc rather than the role-key inventory, to avoid duplicate config for a project-wide invariant).

## Resulting Changes

- contracts.md
