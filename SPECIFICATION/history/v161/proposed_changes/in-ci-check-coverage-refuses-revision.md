---
proposal: in-ci-check-coverage-refuses.md
decision: accept
revised_at: 2026-11-08T19:12:53Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

From commit 34f370e1 (2026-11-04) the CI coverage consumer treated a failed reuse as a green path and re-ran the whole suite at about 15 times the cost, with one log line as its trace (plan ci-runtime-and-cost research 006). The clause makes the consumer refuse by name in CI while a local run still measures. Carries livespec-dev-tooling-s2esff.

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
proposal_stem: in-ci-check-coverage-refuses
content_digest: 55ed1af914c26ceb37421a9147b1377d127891a5e62424a5838b619979e16925
