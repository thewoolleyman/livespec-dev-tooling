---
proposal: mandatory-aggressive-jit-startup-admission.md
decision: accept
revised_at: 2026-08-14T05:46:52Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: gpt-5.6
---

## Decision and Rationale

Maintainer-directed auto-revise accepts this narrow correction without rewriting v044. The v045 contract makes the startup burst load-bearing: it MUST immediately admit every current deduplicated demand item permitted by the existing logical desired formula, remaining physical capacity, and remaining 450-point budget, with no unconditional sleep, while retaining the 450-point ceiling. It retains the corrected five-points-per-content-generating-POST / ten-points-per-complete-mint-pair arithmetic and its approximately 45-pair consequence.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: manual-spawn
reviewer_model: gpt-5.6
reviewer_identity: gpt-5.6
separate_reviewer: True
read_only: True
reviewed_at: 2026-08-14T05:46:26Z
verdict: NO BLOCKERS
proposal_stem: mandatory-aggressive-jit-startup-admission
content_digest: 72b0c7c9270f5226ff0e318d928fc316c2ce0cb43ec751f89aa05d5a1dc49bcf
