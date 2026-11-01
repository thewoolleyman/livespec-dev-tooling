## The maintainer's statement of what done means

You should not have given that to Token Spend Analysis. You should have made a new plan for it. That's not the purpose of that plan.

## Definition of Done assertions derived from that statement

- Every gpt-6.1-sol response the spend emitter writes to Honeycomb dataset llm-spend after the fix carries a non-zero cost_usd computed from a listed price.
- The 226 previously zero-priced gpt-6.1-sol events from 2026-10-25 to 2026-10-30 are restated in llm-spend with non-zero cost, and a query over that window sums them at the corrected price.
- A response for a model absent from the emitter's price table that carries tokens is never written with cost_usd 0; it is priced by the documented fallback and marked as fallback-priced.
- The governed specification carries a heading that states the LLM-spend telemetry pricing contract, so the carrying work-item's References line names it.

# Charter: llm-spend-pricing-correctness

Created 2026-10-31 ~14:0xZ by the gitops-fleet-capacity-monitoring coordinator, at the maintainer's direction (attended): "You should not have given that to Token Spend Analysis. You should have made a new plan for it. That's not the purpose of that plan."

## Problem (measured by token-spend-analysis, Honeycomb env livespec, dataset llm-spend)

The spend emitter prices gpt-6.1-sol responses at $0. Over 7 d, 13.9M local Codex tokens were priced at $0; 226 zero-priced events (21.4M input tokens, 10-25 to 10-30) are already ingested. The emitter has a gpt-5.6-sol fallback for unlisted models, but these events don't take that path, so diagnosis comes first. Every burn-lever ranking reads this data, so a $0 row understates real spend.

## Carrier

livespec-dev-tooling-6vnjbi (bug, P1, host work on the VPS emitter), re-parented here from no parent. Its References line is empty because no spec H2 governs LLM-spend telemetry. A propose-change for that heading is in this plan's scope, as assertion 4.

## Definition of Done derivation

The maintainer gave no DoD wording; the assertions below are DERIVED by the coordinator from 6vnjbi's measured scope and are reported to the maintainer for objection.
