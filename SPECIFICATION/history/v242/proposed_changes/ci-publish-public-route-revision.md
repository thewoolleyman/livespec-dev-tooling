---
proposal: ci-publish-public-route.md
decision: accept
revised_at: 2026-11-17T02:31:37Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

The released 1.215.0 observer already serves POST /ci/publish; contracts.md required publication but never made the route public, so the identity policy cannot be provisioned. The proposal ratifies the route as public only for a provisioned installation, authenticated by the forge-issued identity token alone, and adds the funnel scenario. Independent review found no contradiction with the 'those same routes, and only those' sentence, which the new paragraph reads together with.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-17T02:30:46Z
verdict: NO BLOCKERS
proposal_stem: ci-publish-public-route
content_digest: aac5da8e29fe8273a901fdb57b69f12b7166552e8a87f673ad5efd94f1b57b53
