---
proposal: release-bump-classification-check.md
decision: accept
revised_at: 2026-08-26T00:32:25Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-5
---

## Decision and Rationale

v050 ratified the release-workflow category but left it empty; this defines its first member. The change is purely additive: it names the member in the existing category sub-bullet, adds one dedicated check section, and records the check in the source_trees role key's behavioral-consumer list as that key's own rule requires. No canonical slug is added, so the wiring-completeness invariant conscripts no consumer, and adoption stays per-consumer opt-in. The section compares semver CLASSIFICATIONS rather than computed version numbers, which is correct on both sides of 1.0.0 and needs no pre-major special case, and it states explicitly that the __all__ inventory is a lower bound that cannot see behavior-only breaks.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-08-26T00:31:24Z
verdict: NO BLOCKERS
proposal_stem: release-bump-classification-check
content_digest: cd31465a39d00995be704a3e3c7b7eee6913126a6ed36ba7cf5f7accbf60f45f
