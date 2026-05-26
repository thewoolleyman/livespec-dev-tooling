---
proposal: spec-amendments-from-doctor-objective-findings.md
decision: accept
revised_at: 2026-05-26T04:27:46Z
author_human: E2E Test <e2e-test@example.com>
author_llm: claude-opus-4-7
---

## Decision and Rationale

All three sub-proposals are well-rationalized, byte-precise fixes for doctor-LLM-objective findings. Sub-proposal 1 inlines the section Self-hosting bootstrap detail into contracts.md, removing the dangling cross-file reference to the section Coordination-surface bootstrap procedure (the companion NFR amendment never landed). Sub-proposal 2 deletes the section Migration notes in contracts.md (lines 183-189) which carries anachronistic future-tense MUST-language inside a ratified spec; the historical provenance is preserved in history/v002/contracts.md. Sub-proposal 3 performs 7 targeted find/replace edits across all 4 spec files to swap external Phase G.2/G.4/G.6 work-item-epic phase references for inline activity descriptions (per the mapping: G.2 -> library bootstrap, G.4 -> shared-check migration from livespec-core, G.6 -> post-release cross-repo coordination handoff), restoring standalone readability without changing any contract. All edits are pure prose; no implementation impact.

## Resulting Changes

- contracts.md
- constraints.md
- spec.md
- non-functional-requirements.md
