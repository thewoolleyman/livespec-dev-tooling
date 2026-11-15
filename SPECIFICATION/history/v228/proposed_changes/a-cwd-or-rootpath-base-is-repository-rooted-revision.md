---
proposal: a-cwd-or-rootpath-base-is-repository-rooted.md
decision: accept
revised_at: 2026-11-15T00:03:37Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:throughput-plans-coordinator
---

## Decision and Rationale

Accepted as written. legacy-coordinator-agent graded the proposal PASS under the maintainer's delegated revise authority (ruling R301). The working directory and pytest's root path are the repository root in every fleet gate and CI job, and counting them as repository-rooted errs toward touched, the direction the Untouched-test retry bullet already prefers. Carrier: livespec-dev-tooling-wc23r2. The new scenario heading gets a TODO tests/heading-coverage.json row owned by livespec-dev-tooling-wc23r2 in the revise commit.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-15T00:02:44Z
verdict: NO BLOCKERS
proposal_stem: a-cwd-or-rootpath-base-is-repository-rooted
content_digest: 1581bbf9a286215ad731a7cbd8f2f2bf01524443118823ebabc243463c13d9c2
