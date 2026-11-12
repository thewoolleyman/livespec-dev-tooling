---
proposal: an-expedited-pull-request-s.md
decision: modify
revised_at: 2026-11-12T22:10:48Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Plan expedited-incident-response-flag (epic livespec-dev-tooling-bqnzcm), ratified in one v207 pass at the head of the dev-tooling revise queue on legacy-coordinator-agent's order after the maintainer's 24-hour direction (2026-11-12 ~19:2xZ). Graded PASS-WITH-FIXES by legacy-coordinator-agent on livespec-dev-tooling#4311 (five fixes, then two wording fixes, all in the proposal). Carries livespec-dev-tooling-bqnzcm.4.

## Modifications

Relative to the proposal: a sentence states each record kind's identity (a published record's key and aggregate digest; an unpublished record's key and content), so a repeated write of either answers the retained record; the doctor pass found 'idempotent by digest' undefined for an unpublished record, which has no digest.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T22:09:14Z
verdict: NO BLOCKERS
proposal_stem: an-expedited-pull-request-s
content_digest: ce0f5578baf2b83db8deff1fd41fb00c40b6f23d73a1c843fe97b7cfd6af90c1
