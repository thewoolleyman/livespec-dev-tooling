---
proposal: an-apply-never-installs-a.md
decision: accept
revised_at: 2026-11-03T14:47:38Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:kubernetes-sandbox-backend
---

## Decision and Rationale

Accept. No ratified heading governs sandbox-provider plugin binaries or their instance pins. The 2026-11-03 09:01Z incident (a v0.7.0 binary swap against v0.5.0 pins broke every plugin launch and killed six runs) shows the guard and the drift comparison are needed. The clause sits in non-functional-requirements.md §"Fabro factory host provisioning" because it is contributor-only fleet infrastructure. It carries a Given/When/Then scenario, a heading-coverage TODO entry tied to livespec-dev-tooling-rnsfgg, and a matching coverage-debt entry. Reviewer non-blocking notes, left to the implementing item: when no instance declares the path the apply installs as today; the item defines which host_vars key holds the pin.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T14:31:43Z
verdict: NO BLOCKERS
proposal_stem: an-apply-never-installs-a
content_digest: 333a1948923df758ca4b908cd58072e2ebcffe1134b07f67c4fa48fcb975d871
