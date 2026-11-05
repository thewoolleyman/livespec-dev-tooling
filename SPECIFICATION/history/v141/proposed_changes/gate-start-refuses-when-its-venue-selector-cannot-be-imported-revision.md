---
proposal: gate-start-refuses-when-its-venue-selector-cannot-be-imported.md
decision: accept
revised_at: 2026-11-05T15:35:44Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn). Delegated decider: legacy-coordinator-agent under R301, which pre-decided ACCEPT on 2026-11-05 when it ruled that a named refusal with a distinct exit code is new contract behaviour needing this propose-change. Carrier: livespec-dev-tooling-p3mhfh (plan dev-host-test-gate-load). Measured 2026-11-05 ~07:10Z: gate-start in a stale checkout exited a generic EX_SOFTWARE 70, the runner-fault code, with no remedy named. No ratified statement conflicts (70 stays the startup-fault code, 75 stays DIED_WITHOUT_VERDICT, and a refusal before launch creates no run, so the every-run-records-a-venue rule is unaffected) and no design record is contradicted. An independent read-only sonnet reviewer found NO BLOCKERS on the exact bytes; non-blocking notes: the exact non-70 code is left to the implementation, and the selector-stderr clause has no scenario of its own.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T15:35:41Z
verdict: NO BLOCKERS
proposal_stem: gate-start-refuses-when-its-venue-selector-cannot-be-imported
content_digest: 131639b2eaabb52762423179dd2e78e4b59c43eb6ba8ee35ccdcc3525f90b0d2
