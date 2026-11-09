---
proposal: rule-26-kill-matrix-engine.md
decision: modify
revised_at: 2026-11-09T11:29:21Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The maintainer's attended ruling of 2026-11-09 (scope event on epic livespec-dev-tooling-oi2two) requires a rule-26 kill matrix that is pure code with no LLM, gives periodic answers on which tests can be killed, and is fast: parallel, building results up over runs. The shipped engine starts one pytest process per selected test per applied mutant; the orchestrator effects/ probe gave 1,372 mutants from 1,725 lines, about 165,000 for the package. The proposal's text was modified because two doctor LLM passes found the first drafts could give wrong test-deletion advice: an unsound cache key, baseline failures listed as removable, and tests whose only mutant failed to apply listed as removable. The recipe keeps every exclusion from just check, hooks and required per-PR jobs, so plan assertion A5 is unaffected. Carrier: livespec-dev-tooling-dkgwsm.

## Modifications

Modified over three independent review rounds (a sonnet ratification reviewer, and doctor LLM passes walked through the live engine), without changing the proposal's intent. The enumerated cache key became an outcome-level guarantee: reuse a cached outcome only when the engine can determine from file and setting contents that re-testing would give the same outcome, otherwise re-test, and identical inputs re-test nothing. Cached killers that are no longer tests are dropped. Added: a baseline run, so a test that fails or times out on unmutated source is a baseline failure, excluded from attribution and never a redundancy candidate; a timeout counts as a kill; a test whose shared process dies is re-run alone; workers apply mutants in separate source trees, with parallel equality excepting timeout-decided outcomes; zero applied mutants exits non-zero; generated, applied and unapplied counts; unapplied-coverage tests (never redundancy candidates); one unified redundancy-candidate definition; run-metadata versus matrix-content fields; per-mutant function digests, with 'function changed' and 'function unknown' marks; the what-changed summary's input path, documented location, machine-readable format, identity rules and new/changed marking; a scheduled job that is never a required status check, a CI workflow triggered only by schedule or manual dispatch, and an explicit no-previous-report path. The Test-suite baseline bullet restates its exclusions instead of cross-referencing the kill-matrix recipe. There are 15 scenarios.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T11:27:59Z
verdict: NO BLOCKERS
proposal_stem: rule-26-kill-matrix-engine
content_digest: 228dfd45a268b846af64a19442825078e8768307b26564e34d3947497ee138fa
