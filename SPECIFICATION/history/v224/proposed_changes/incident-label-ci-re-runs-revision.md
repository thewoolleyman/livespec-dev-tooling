---
proposal: incident-label-ci-re-runs.md
decision: accept
revised_at: 2026-11-14T19:53:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as proposed (livespec-dev-tooling-eqtyyr). The replay gate's incident admission reads the pull request's current livespec-incident-ci block, either live through the authenticated forge read or through a fresh run the label workflow starts, never through a re-run whose event payload predates the block, and names a missing block and the source it read. Measured cause: livespec-dev-tooling#4533's CI attempt 2 replayed a stale event payload.

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
proposal_stem: incident-label-ci-re-runs
content_digest: fd3d4d74309605756c64a91300b1354837ec0175dd89ba6ac7f8859655e3dbec
