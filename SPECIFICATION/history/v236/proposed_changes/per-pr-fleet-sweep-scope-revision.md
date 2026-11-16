---
proposal: per-pr-fleet-sweep-scope.md
decision: accept
revised_at: 2026-11-16T04:11:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Accept as proposed and graded. The throughput-plans-coordinator graded the proposal PASS-WITH-FIXES (2026-11-16 03:2xZ) and the fixes (import-closure trigger set with an every-member fallback, two scenario headings, head sha on the skip line) are in the proposal's bytes. It narrows the per-PR conformance run to the running member unless the change touches the checker's import closure. That is a ratification because the ratified text said the CI job asserts every member. Master push, the scheduled sweep and the release preflight keep the full sweep, so the surfacing duty at contracts.md:949 moves to the master push CI. The rejected head-keyed result cache is recorded in the proposal's motivation. No design-record contradiction: the change narrows no cited design record. An independent read-only sonnet subagent, spawned by the stale-base-merge-options seat (session 7eb80365) separately from the decider's context, returned NO BLOCKERS on the exact final bytes. Realization is owned by livespec-dev-tooling-p7mlz2.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-16T04:10:32Z
verdict: NO BLOCKERS
proposal_stem: per-pr-fleet-sweep-scope
content_digest: ea94eb4c6dcc50ebe9bdf8bbd853e4445b10e56437fcfed5632797136008f822
