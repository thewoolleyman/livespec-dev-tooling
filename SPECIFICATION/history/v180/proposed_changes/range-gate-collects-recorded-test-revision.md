---
proposal: range-gate-collects-recorded-test.md
decision: accept
revised_at: 2026-11-10T04:30:17Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as filed. The commit-range validation judged a Red+Green commit only by the presence of its trailer keys, and livespec-dev-tooling#3913's 31d49d7a and 42f3537a passed although their recorded test raises ImportError on their own trees (reproduced). Collect-only per commit closes that at a measured 2-4 s per commit plus a worktree. A re-run costs about 4x, and a checksum check would miss this case because both checksums matched. It reconciles the adjacent 'judged exactly as before' sentence and adds one scenario, whose heading-coverage TODO row is co-edited in this revise commit. resulting_files carry the cumulative contracts.md and scenarios.md, including the stall-kill decision's edits applied before it.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T04:29:33Z
verdict: NO BLOCKERS
proposal_stem: range-gate-collects-recorded-test
content_digest: 1a2745ec5f0563371fb5170fb130df996d0c5caf0a7a322adc249e8f033ec229
