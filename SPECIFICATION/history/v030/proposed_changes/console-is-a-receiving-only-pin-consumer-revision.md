---
proposal: console-is-a-receiving-only-pin-consumer.md
decision: accept
revised_at: 2026-07-22T20:19:25Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Ratifies the console reclassification under livespec-oq9w Option B after an independent NO-BLOCKERS Fable review. Applies the four verbatim replace-targets in contracts.md: the console moves from 'non-pin-consuming member / first such member / ships none of the three shims' to a 'receiving-only consumer' that ships the two receiving shims (bump-pin-from-dispatch.yml + pin-freshness.yml) but no release-dispatch.yml, aligning the PROSE half of the epic with the already-merged CODE half (dev-tooling PR #536, _contract_rows.py _RECEIVING_SHIM_CLASSES). Introduces the two-halves receiving/producing model and restates the non-pin-consuming position as a defined possibility with no current fleet occupant. No H2 heading added/removed/renamed, so no heading-coverage co-edit.

## Resulting Changes

- contracts.md
