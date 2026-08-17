---
proposal: self-hosted-ci-posture.md
decision: accept
revised_at: 2026-08-17T14:13:56Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-5
---

## Decision and Rationale

Ratifies the routing posture this repository actually adopts, replacing a stale hosted-only-posture premise that seven sibling fleet repositories already contradict. The independent pre-ratification review returned BLOCKERS FOUND on its first pass and both blockers were fixed before this accept: an incomplete drift sweep that left the same stale premise in contracts.md (now the proposal's second edit), and a universal claim about sibling repositories in durable spec text (reworded to name a pattern rather than assert sibling compliance). The re-review returned NO BLOCKERS with both fixes verified and every previously-passing item re-confirmed against the regenerated file.

## Resulting Changes

- constraints.md
- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-08-17T14:13:14Z
verdict: NO BLOCKERS
proposal_stem: self-hosted-ci-posture
content_digest: 6920dcf47b445284bfc817fc59cc9393da9f8f416d092db2dfa880cc55122e15
