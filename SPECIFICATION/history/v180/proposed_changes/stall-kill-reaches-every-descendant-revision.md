---
proposal: stall-kill-reaches-every-descendant.md
decision: modify
revised_at: 2026-11-10T04:30:17Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted with one modification. The SIGTERM-first stall kill now cites the ratified v178 clause it exists to serve. It makes a stalled gate's kill reach every process attributed to the run, including a descendant that entered a new OS session (homelab's orphaned PID 210253, which ran for about 9 h). It uses a SIGTERM, 30 s grace, then SIGKILL order, so a check runner's v178 cleanup can run. Five independent doctor passes on the proposal ended NO BLOCKERS. No H2 heading changes.

## Modifications

In the contracts.md Progress bound insertion, the sentence 'That order lets a terminated process, such as a check runner, run its own cleanup on SIGTERM before it can be killed.' now ends ', as non-functional-requirements.md §"Enforcement-suite invocation" requires of a check runner's coverage directories.' That clause was ratified in v178 (livespec-dev-tooling#3977) after this proposal was filed, so the two clauses now cross-reference each other as one design, on legacy-coordinator-agent's direction.

## Resulting Changes

- contracts.md
- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T04:29:33Z
verdict: NO BLOCKERS
proposal_stem: stall-kill-reaches-every-descendant
content_digest: 9e640dd892bb0a3aaef735b4a108f3c1602ec742bf2d83a198d560d35325a8f2
