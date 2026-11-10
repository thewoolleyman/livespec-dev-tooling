---
proposal: llm-spend-s-spend-account.md
decision: modify
revised_at: 2026-11-10T10:25:01Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The motivation was measured on 2026-11-10. The protected account anthropic-0 billed pay-as-you-go from 02:12Z, reaching $204.91 and its cap by 05:42Z, and llm-spend could not name the consumer. Every emitter infers spend.account from caam's selection or active timeline, so every Claude cost row in the window was labelled anthropic-1, and anthropic-0 appeared only on $0 rotator rows. The observed/inferred marker, the factory dispatcher's projected-credential record and the unattributed-usage trigger would each have named the consumer, or shown that it was outside the fleet, in one query. The section is non-functional because llm-spend is fleet-internal infrastructure that no governed project inherits. It sits beside §"LLM-spend telemetry pricing", which already scopes every emitter of the dataset. It records account labels only and never a credential value or digest. livespec-dev-tooling-n277mo realizes it and owns both owed tests. Independent sonnet review recorded NO BLOCKERS on these exact bytes.

## Modifications

Formatting only. The scenario's Given/And/When/Then lines are separated by blank lines, matching the convention of every other scenario in scenarios.md. The section and scenario text are otherwise verbatim from the proposal. Two spec-first TODO rows are added to tests/heading-coverage.json, one for each new heading. Each names the integration tier and carries work_item livespec-dev-tooling-n277mo.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T10:24:03Z
verdict: NO BLOCKERS
proposal_stem: llm-spend-s-spend-account
content_digest: 0c94209718b920ee5aa1a7c9fd631c1a9153577907049b5aec15612596c54a4f
