---
proposal: the-incident-ci-inventory-renderer.md
decision: accept
revised_at: 2026-11-14T19:53:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as proposed (livespec-dev-tooling-yzr6ad). An inventory member is keyed by job and check slug together, so a workflow declaring one check in two jobs renders; the entrance runs each slug once per run and attributes its outcome to every declaring job; a conditional job is listed as not run, never dropped, without parsing a workflow expression. Measured cause: livespec's release-gate-pre-tag job at a91c015d made the render refuse, so no livespec inventory could be released.

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
proposal_stem: the-incident-ci-inventory-renderer
content_digest: b6e44571b19fdca2053f56e7eec09326db06efddba5e6e21884d5ae814c31883
