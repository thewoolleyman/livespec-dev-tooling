---
proposal: measure-the-fleet-test-count.md
decision: accept
revised_at: 2026-11-06T17:09:01Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn). The delegated decider is the plan session for fleet-mutation-testing-rule-26 (epic livespec-dev-tooling-oi2two), which acts under the maintainer's 2026-11-06 direction to drive that plan. livespec-dev-tooling-phakbp, the plan's test-count and runtime baseline, was ticketed and then refused before listing as spec-change tier. The judgement linked this topic and named §"Rule-26 mutation kill matrix" as the heading to generalize, because no ratified text describes `just fleet-test-baseline`. This revise adds that contract as one bullet in the section and adds one scenario. The bullet and scenario are applied exactly as filed. No design record is cited or contradicted. An independent read-only sonnet reviewer found NO BLOCKERS on these exact bytes. Its non-blocking notes go to the implementing item: decide whether the keep-out guard should also cover fleet-test-baseline, define where each repository's test-only command and toolchain versions come from, word the shell count as one per discovered script, and compare totals within rounding.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-06T17:08:36Z
verdict: NO BLOCKERS
proposal_stem: measure-the-fleet-test-count
content_digest: f79e713270701d9d77a2954271f36251570f223a854487c40926ab59aafbe3ff
