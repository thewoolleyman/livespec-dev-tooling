---
proposal: the-pyright-warm-up-runs.md
decision: accept
revised_at: 2026-11-14T19:53:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as proposed (livespec-dev-tooling-h73ok4). Every child process the released incident CI entrance starts, the locked pyright warm-up included, runs with the repository root as its working directory and no LIVESPEC_INCIDENT_ variable, while the entrance keeps its own credentials for controller reads; the local dispatcher passes cwd and environment to the warm-up explicitly. Carries the two hardening fixes from legacy-coordinator-agent's grade of livespec-dev-tooling#4533.

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
proposal_stem: the-pyright-warm-up-runs
content_digest: 60b3d07f64d0934a4111b396d037256ed56e10da9640524dedd3b15ffc7eef09
