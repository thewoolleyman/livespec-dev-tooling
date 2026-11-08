---
proposal: record-every-mandatory-reuse-outcome.md
decision: modify
revised_at: 2026-11-08T19:12:53Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

A refusal alone would not report evidence that stops arriving; the fallback ran about two days with nobody told. Recording each outcome and a scheduled detector that also watches its own staleness closes that. Carries livespec-dev-tooling-akljpy.

## Modifications

Defined a mandatory coverage consumer job (a gating job that runs scripts/just/check-coverage.sh over a producer's uploaded data), which the proposal used undefined. Made the duration baseline exact: the job's 90th-percentile duration over the preceding 7 days, rather than an unspecified 7-day baseline. Scoped the step-change rule to fleet CI jobs. The scenarios follow the same wording.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T19:12:04Z
verdict: NO BLOCKERS
proposal_stem: record-every-mandatory-reuse-outcome
content_digest: c7a0130fd391e3c526d587d7e75af8d815c64ac07d3d93bf2157078ac584903c
