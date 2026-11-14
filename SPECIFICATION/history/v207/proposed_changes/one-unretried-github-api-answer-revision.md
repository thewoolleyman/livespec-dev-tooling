---
proposal: one-unretried-github-api-answer.md
decision: modify
revised_at: 2026-11-12T22:10:48Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Plan expedited-incident-response-flag (epic livespec-dev-tooling-bqnzcm), ratified in one v207 pass at the head of the dev-tooling revise queue on legacy-coordinator-agent's order after the maintainer's 24-hour direction (2026-11-12 ~19:2xZ). Graded PASS-WITH-FIXES and then CLEARED by legacy-coordinator-agent on livespec-dev-tooling#4353 (rate-limited answers retried; ci-green and the label workflow covered; once per trust boundary with an equality test). Carries livespec-dev-tooling-levu6j.

## Modifications

Relative to the proposal: (1) the sentence requiring every incident-ci, ci-green and label-workflow forge call to go through the forge-read command now excepts the released incident CI entrance's own read, which the same text sends through budgeted_gh and never the Action; the doctor pass found the two sentences otherwise both bind the entrance; (2) a job's timeout must exceed the call's bound plus the time its other steps take, not the call's bound alone; (3) the forge-read Action is not added to the minimum set of the Composite Actions wire contract, which stays at four: that set is the semver-stable surface every release must resolve (tests/consumer/test_semver_stable_surface.py refused the first cut's push), and the Action does not ship yet. Its wire contract, unchanged, is instead a paragraph of the Expedited incident execution section, which says it joins the minimum set in the first revise after a release ships it.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T22:10:02Z
verdict: NO BLOCKERS
proposal_stem: one-unretried-github-api-answer
content_digest: 8331b27c87e4b75bee78e4279cb7daa292c13e3a4527399f33d67bca10f86610
