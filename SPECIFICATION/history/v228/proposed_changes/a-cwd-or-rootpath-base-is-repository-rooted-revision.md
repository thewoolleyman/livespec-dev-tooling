---
proposal: a-cwd-or-rootpath-base-is-repository-rooted.md
decision: accept
revised_at: 2026-11-15T00:34:08Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:throughput-plans-coordinator-helper
---

## Decision and Rationale

Accepted as written. legacy-coordinator-agent pre-graded this proposal ACCEPT under the maintainer's delegated revise authority (R301). It names the working directory and pytest's root path as repository-rooted bases in the Untouched-test retry bullet, which errs toward touched, the direction the bullet already prefers, and adds one scenario covering both bases. Carrier: livespec-dev-tooling-wc23r2. Re-cut on the installed livespec build 9106ef675f5f; supersedes livespec-dev-tooling#4735.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-15T00:33:50Z
verdict: NO BLOCKERS
proposal_stem: a-cwd-or-rootpath-base-is-repository-rooted
content_digest: 1581bbf9a286215ad731a7cbd8f2f2bf01524443118823ebabc243463c13d9c2
