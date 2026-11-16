---
proposal: cite-the-core-heading-for-the-master.md
decision: accept
revised_at: 2026-11-16T17:06:41Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5 (master-green-external-outage plan seat)
---

## Decision and Rationale

The reword is accepted as proposed: the opening sentence of 'Master-green gate and external red' cites livespec core's real heading 'CI as a merge gate (branch protection)', already allowlisted, and names the bold paragraph in prose. It is one line, no heading changes, and it removes the doctor-no-cross-spec-reference failure that blocks every dev-tooling revise (incident livespec-dev-tooling-mafayz). The coordinator decided the normal lane with --skip-pre-check; the post-step doctor must come back clean.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-16T17:06:12Z
verdict: NO BLOCKERS
proposal_stem: cite-the-core-heading-for-the-master
content_digest: 504c7487a03a2b8a8aaac1f1e23bf9cd9465cf8b2812fa4721a1fab4a88e9220
