---
proposal: suite-green-leg-spec-first-notes-stale.md
decision: modify
revised_at: 2026-11-10T01:05:33Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified and accepted under delegated decision mode. Three spec-first notes in Suite-green replay leg described the pre-t4rx4t / pre-z5fwwn leg. The fixed 2400 s timeout is gone (DEFAULT_STALL_SECONDS = 900, optional ceiling), and same-tree reuse shipped (reuse_pre_commit_evidence). Both owning items are closed, so those notes contradicted the code. No normative clause changes. Independent sonnet ratification review: NO BLOCKERS on the final bytes.

## Modifications

Pre-merge doctor finding applied. The Progress bound note is not deleted whole, because the clause's refusal facts beyond the stall window and its variable are still unshipped: elapsed seconds, completed out of collected, the last completed test and its instant, still-running tests, received output, and the post-last-test statement. The shipped refusal names only the window, the variable, and whether any test had completed. The 2400 s note is replaced by a narrowed spec-first note naming the open owner livespec-dev-tooling-h2i4u2. The intro sentence and the same-tree-reuse note are deleted as proposed.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T01:03:51Z
verdict: NO BLOCKERS
proposal_stem: suite-green-leg-spec-first-notes-stale
content_digest: 6b2ee68d415bc2a6ad40eb0019ddab4260ef4ce9f413321f0f77a06db5b937b7
