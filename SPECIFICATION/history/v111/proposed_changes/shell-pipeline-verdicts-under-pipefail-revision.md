---
proposal: shell-pipeline-verdicts-under-pipefail.md
decision: accept
revised_at: 2026-11-02T15:50:19Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:dev-host-test-gate-load
---

## Decision and Rationale

No ratified H2 governed shell-pipeline robustness under pipefail, and livespec-dev-tooling-ftgiu4 (the sweep of about 47 scripts) was refused at pre-dispatch for that reason. The proposal states the rule as BCP14 clauses with a Given/When/Then scenario. It is a contributor-side rule for this repository's own scripts, so it is placed in non-functional-requirements.md, beside Hooks and CI. It contradicts no existing statement: a grep for pipefail, SIGPIPE and grep -q finds no ratified text.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T15:49:02Z
verdict: NO BLOCKERS
proposal_stem: shell-pipeline-verdicts-under-pipefail
content_digest: f80d6463acdd410bb4591c282517b3bfea26e3551c91009094bd07656bd3109b
