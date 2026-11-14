---
proposal: the-incident-ci-inventory-render.md
decision: accept
revised_at: 2026-11-14T19:53:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as proposed (livespec-dev-tooling-6xd3dz). The render script renders to a temporary file and moves it into place only after success, so a failed render leaves a committed entry byte-identical, and it refuses a clone whose origin does not name the repository argument, among other named refusals, each test-driven. Both failure modes were measured while preparing livespec's entry.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T19:50:56Z
verdict: NO BLOCKERS
proposal_stem: the-incident-ci-inventory-render
content_digest: 25ccb44a861230329f2e3acb0e393853c3eea364f2e4a1d2d6013e1bed42ff57
