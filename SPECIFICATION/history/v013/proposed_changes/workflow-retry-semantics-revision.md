---
proposal: workflow-retry-semantics.md
decision: accept
revised_at: 2026-06-12T06:45:29Z
author_human: Test <test@example.com>
author_llm: claude-fable-5
---

## Decision and Rationale

Accepted as proposed (user pre-authorized). The rerun-vs-fresh-dispatch distinction is structural (gh run rerun replays the original event payload pinned to the original github.sha and can never observe post-event commits), was observed live on the v0.12.1 bump failure, and currently has no normative home anywhere in the family. The new §"Retry semantics (rerun vs fresh dispatch)" subsection lands verbatim between §"Fallback to known-good pin" and §"Self-hosting" in contracts.md §"Cross-repo coordination automation surface", making this repo the canonical home sibling surfaces reference. The mechanical guard on reusable-bump-pin-from-dispatch.yml is a behavioral addition with no new inputs; its IMPLEMENTING commit carries a feat: subject (MINOR) per §"Semver discipline". This file's content is cumulative over the prior decision's contracts.md (both accepted decisions touch the same file).

## Resulting Changes

- contracts.md
