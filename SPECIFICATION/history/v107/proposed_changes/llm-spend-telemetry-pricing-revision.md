---
proposal: llm-spend-telemetry-pricing.md
decision: modify
revised_at: 2026-11-01T21:21:54Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

MODIFY. Adds non-functional-requirements.md §"LLM-spend telemetry pricing" and one scenario, ratifying how every emitter writing the fleet's livespec/llm-spend dataset prices a model response: one shared list-price table naming its source page and read date, never $0 for a token-bearing response (one documented, marked family-or-top fallback), dated ids priced as their listed model, and corrections as a once-only retract/restate pair. Plan llm-spend-pricing-correctness (epic livespec-dev-tooling-wpfmjh), assertion 4, carrier livespec-dev-tooling-6vnjbi; the host emitter (~/token-spend-report, local git 1150df9, 0dd5238, a4703d7) is the implementation, verified in Honeycomb 2026-10-31 and 2026-11-01. Placement per §Boundary: fleet telemetry contributors read, beside the runner-pool telemetry sections. Spec-led, not drift-origin; no design record cited or contradicted. Decided under delegated revise_decision_mode by the plan seat on the coordinator's ruling (legacy-coordinator-agent, R301, 2026-11-01). Independent review: separately spawned read-only sonnet agent, NO BLOCKERS on these exact bytes. First review returned one blocker (the family fallback did not say which listed member; now the newest listed model) and nits taken: highest output price names the top fallback, the dated-id clause is scoped to Anthropic, the retraction negates numeric fields and carries consumer and account fields, cache write per lifetime. Nits left for livespec-dev-tooling-mnj7: scenarios for the one-table, dated-id and correction-once clauses.

## Modifications

Relative to the proposal: (1) a lookup table an emitter keeps MUST be derived from the shared table — the factory Claude path's node_join.PRICE was a second copy, now derived (a4703d7); (2) list prices are the provider's standard tier at its shortest context or prompt-length band, matching what both tables hold; (3) a listed model is marker-free only when priced entirely from its own entry, and a response priced from other rates (an OpenAI model met in a Claude Code transcript) is fallback-priced, matching prices.claude_price; (4) long sentences split. Heading-coverage rows for both new headings are spec-first TODOs owned by livespec-dev-tooling-mnj7, at the integration tier or above, because the emitter is host-local.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-01T21:21:48Z
verdict: NO BLOCKERS
proposal_stem: llm-spend-telemetry-pricing
content_digest: a9686c999ed06e32a8a0e85a81540dee82b1f3868c831d0ff38f466f3a09d862
