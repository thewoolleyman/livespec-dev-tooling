---
proposal: scale-set-ceiling-bounded-to-fair-share.md
decision: accept
revised_at: 2026-09-06T09:16:21Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-fable-5-1 (poweredge-raid-array-maintenance plan session, Claude Code)
---

## Decision and Rationale

Accept: in section "Adaptive JIT runner admission budget" replace the sentence requiring each repository's logical ceiling to be doubled with one requiring it to be BOUNDED to a small multiple of the repository's fair share of host-wide capacity (large enough to borrow, never so large that a backlog is materialized as pending admission objects; the multiple and floor are pool facts recorded with the admission derivation), keeping the physical-cap sentence and the min() formula verbatim; and in scenarios.md replace the matching Given step of "JIT fleet capacity borrows fairly without exceeding 482 runners", heading unchanged. Design record: ci-runner/k3s/phase2/kueue/DERIVATION.md "Bounding maxRunners to the quota (2026-09-06)" (maxRunners = max(2 x nominalQuota, 6); ten ceilings 76 against 574; the 2026-09-06 07:38Z-07:50Z backlog measurement) and livespec epic livespec-ifwnqj. Maintainer-directed 2026-09-06 in session. Both replace targets verified verbatim exactly once in the pre-revise files (the non-functional-requirements.md target hard-wraps across two lines); the resulting text is the proposal's quoted replacement, re-wrapped to the file's line width; no `## ` heading added, changed, or removed, so no tests/heading-coverage.json co-edit. Independent adversarial review (Fable, read-only) returned NO-BLOCKERS with eight nits, the four doc nits folded in the same pull request (#1805); the configured fable ratification reviewer then returned NO BLOCKERS on these exact resulting bytes with the digest recomputed independently. Companion clause in core: livespec proposed change ci-host-backlog-object-bound. The pending sibling proposal pin-uses-ref-template-scan-set is left in place (single-proposal pass).

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-06T09:08:53Z
verdict: NO BLOCKERS
proposal_stem: scale-set-ceiling-bounded-to-fair-share
content_digest: 7dd71e01c6d4a1849be2167c80eccfae22c0206541d823a7fc29f1ccd9d6fb1c
