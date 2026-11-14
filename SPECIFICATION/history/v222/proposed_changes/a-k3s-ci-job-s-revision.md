---
proposal: a-k3s-ci-job-s.md
decision: accept
revised_at: 2026-11-14T17:03:54Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as graded. livespec-dev-tooling-qeou2e: k3s CI jobs of this repository ran uv sync with the hosted uv download settings because ci.yml keyed UV_CONCURRENT_DOWNLOADS and UV_HTTP_TIMEOUT on CI_RUNNER_LABELS at workflow level, while the jobs route to self-hosted capacity through other variables; master run 43532626286 failed its uv sync with 5 retries in about 4 s, resets under 50-way concurrency, and made 3 of 4 not-green master merges since 2026-11-13 19:42Z. The constraint keys both variables per uv-sync step on runner.environment, forbids workflow- and job-level settings, and requires a guarding test; the scenario states the observable behaviour. throughput-plans-coordinator graded the proposal (livespec-dev-tooling#4634) FAIL at 2ae85e367 and PASS at 8ee1e4e6; the automatic re-run first proposed was dropped at that grade as a band-aid for a self-inflicted fault, with its reopen condition on qeou2e. Decided under delegated revise_decision_mode by the ci-reliability-leftovers plan seat (epic livespec-dev-tooling-7y2jqw) in the revise slot throughput-plans-coordinator ordered on 2026-11-14 while legacy-coordinator-agent was unreachable. Spec-led, not drift-origin; no design record is contradicted. Implementation note carried on qeou2e, not the spec: the shared check self_hosted_uv_lane must accept the per-step form as well as the consumers' top-level form.

## Resulting Changes

- constraints.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T17:03:12Z
verdict: NO BLOCKERS
proposal_stem: a-k3s-ci-job-s
content_digest: 5917fb9e1b66546f945b9581d481989cdad509b98bd49dcc039a7857fb5f89bc
