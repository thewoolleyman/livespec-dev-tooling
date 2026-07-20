---
proposal: reusable-release-park-parity.md
decision: accept
revised_at: 2026-07-20T23:23:45Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-fable-5
---

## Decision and Rationale

Accepted as proposed, after two independent adversarial reviews: the first found one blocker (the sweep covered contracts.md but not the spec.md sentence defining the cross-repo coordination category), the proposal was amended to add the spec.md sweep, and the second review of the amended text returned no blockers. The change gives the SHIPPED .github/workflows/reusable-release-park.yml its missing contract coverage at parity with the three pin-and-bump subsections, describing the TWO-leg design from the cited design record (a parked open release-please pull request measured from createdAt, and an unreleased feat/fix backlog with no release pull request open) rather than the shipped one-leg implementation, per the design-record-authority rule; the missing leg (b) stays a tracked work-item. The three drift sweeps requalify the "three thin shim workflows" count, the inventory intro, and spec.md's category definition so no statement is left asserting the category is pin-and-bump-only. No H2 heading changes, so no tests/heading-coverage.json co-edit.

## Resulting Changes

- contracts.md
- spec.md
