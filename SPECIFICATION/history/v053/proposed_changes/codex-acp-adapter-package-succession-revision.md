---
proposal: codex-acp-adapter-package-succession.md
decision: accept
revised_at: 2026-08-26T06:59:39Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-fable-5
---

## Decision and Rationale

Both proposals are accepted as filed. The package succession is grounded in measured facts (npm marks @zed-industries/codex-acp deprecated at its terminal 0.16.0; @agentclientprotocol/codex-acp 1.6.2 bundles @openai/codex 0.148.0; both export bin `codex-acp` and a plain co-install fails with EEXIST, resolved by --force), it changes only the two sections that name the package plus the rules a succession needs that a version bump never did, and it leaves the factory gate's version-bump guarantees intact. The equivalent-proof clause is the 'later spec revision' the disabled-receiver paragraph already anticipates, scoped to exactly one case (a deliberate package succession) with three checkable parts, and it is stated as BCP14 clauses with a scenario in the same form as the existing codex-acp scenario. No cited design record is contradicted; the independent read-only Fable reviewer returned NO BLOCKERS for these exact bytes.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-08-26T06:57:44Z
verdict: NO BLOCKERS
proposal_stem: codex-acp-adapter-package-succession
content_digest: ed9fc73b57767b75cd71c9f43cb88b54d661434e980528b19a2dbce97b62cde1
