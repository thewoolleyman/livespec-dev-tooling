---
proposal: a-released-adopter-incident-ci.md
decision: accept
revised_at: 2026-11-14T19:53:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as proposed (livespec-dev-tooling-hhxmgv). A freshness read re-renders every committed adopter incident CI inventory entry from the adopter's current default-branch head before each release, refusing the release by name on any difference, and on a schedule, reporting the difference to needs-attention. Without it a released entry silently stops matching its adopter's CI until the next incident mis-selects.

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
proposal_stem: a-released-adopter-incident-ci
content_digest: 17933de215c84838ffc72a947ae90a522c4156e0a19cd777f00fb6024cae89c3
