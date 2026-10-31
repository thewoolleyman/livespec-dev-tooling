---
topic: llm-spend-telemetry-pricing
author: claude-opus-5-5
created_at: 2026-10-31T17:10:38Z
---

## Proposal: LLM-spend telemetry pricing contract

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add an H2 §"LLM-spend telemetry pricing" to non-functional-requirements.md, and a scenario to scenarios.md. Together they state how every emitter writing the fleet's `llm-spend` dataset prices a model response. A listed model is priced at its published list price from one shared table. A token-bearing response on an unlisted model is never priced at $0: it gets one documented, marked fallback. A dated model id that names a listed model is that listed model. A cost correction is a retract/restate pair that negates exactly what the original event carried, and it runs once per response.

### Motivation

Plan llm-spend-pricing-correctness (epic livespec-dev-tooling-wpfmjh), assertion 4, carried by livespec-dev-tooling-6vnjbi. The host spend emitter sent 784 gpt-6.1-sol and 455 gpt-6-luna local Codex responses to the livespec Honeycomb dataset `llm-spend` at cost_usd 0 between 2026-10-21 and 2026-10-30, because codex_cost() returned 0.0 for any model missing from its price table. The Claude path had the same $0 branch, and a dated id (claude-haiku-4-5-20251001) missed its own table key. A provisional fix then priced gpt-6.1-sol at twice its list price for a day. Every burn-lever ranking reads `llm-spend`, so each defect misranked spend with no error. No spec heading governs this telemetry, so 6vnjbi could carry no References line and rests at pending-approval with a mechanical Definition-of-Done finding. The fix that now runs (2026-10-31, ~/token-spend-report local git 1150df9 and 0dd5238, verified in Honeycomb) is the behaviour this heading ratifies. Placement follows the §Boundary litmus: the dataset is fleet infrastructure that contributors read, not something a project governed by livespec inherits, so it sits beside §"Runner-pool cache telemetry" and its sibling telemetry sections in non-functional-requirements.md.

### Proposed Changes

Add the following H2 section to SPECIFICATION/non-functional-requirements.md, after §"Runner-pool workload and control-plane telemetry":

## LLM-spend telemetry pricing

**Scope.** This section governs the cost that every emitter writing the fleet observability surface's `llm-spend` dataset (the `livespec` Honeycomb environment) records for a model response: local or factory, Anthropic or OpenAI, one event per response. Every spend and burn ranking the fleet makes reads that dataset, so a mispriced event misranks spend without raising any error.

**One price table, list prices.** Every emitter that writes `llm-spend` MUST price from ONE shared price table, never from a per-emitter copy. Each entry MUST hold the model's published list price per token class (input, cached input or cache read, cache write where the provider charges one, and output), and the table MUST name the provider page each price was read from and the date it was read. A response on a listed model MUST carry `cost_usd` computed from that entry and MUST NOT carry a fallback marker. A dated or suffixed model identifier that names a listed model (for example `claude-haiku-4-5-20251001` for `claude-haiku-4-5`, or a `[1m]` context suffix) MUST be priced as that listed model.

**Never $0 for a token-bearing response.** A response that carries non-zero tokens on a model the table does NOT list MUST NOT be written with `cost_usd` 0. It MUST be priced by the table's one documented fallback: as the listed model of its family, named by a family token in the model identifier (for OpenAI `sol`, `terra`, `luna`, `astra`; for Anthropic `fable`, `opus`, `sonnet`, `haiku`), or, when no family token matches, as the provider's most expensive listed model, so an unknown model never understates spend. A fallback-priced event MUST carry `spend.price_fallback` = `true` and a `cost_note` naming the listed model it was priced as. An emitter MAY keep a placeholder model name for a response whose model is not yet known (such as a factory turn that has not landed), priced at a stated provisional model, provided the event carries the same marker.

**Corrections are retract and restate, once.** A sent event's cost MUST NOT be corrected by deleting or overwriting it. A correction MUST be written as a pair: a retraction (`spend.correction` = `retract`) that negates exactly what the original event carried, meaning its `cost_usd`, its token fields and its per-component USD fields, plus its consumer and account fields only when the original carried them; and a restatement (`spend.correction` = `restate`) at the corrected price. Sums over any time window, model and consumer then come out correct. A correction MUST be applied at most once per response, and the emitter's state MUST record that it ran, so a second run is refused rather than retracting events already sent at the corrected price.

Add the following scenario to SPECIFICATION/scenarios.md:

## Scenario: a token-bearing response on a model the LLM-spend price table does not list is sent at a marked fallback price

Given the shared LLM-spend price table lists `gpt-6.1-sol` and does not list `gpt-7-sol`

When an emitter sends a response on `gpt-7-sol` that carries non-zero tokens to the `llm-spend` dataset

Then the event's `cost_usd` MUST be non-zero and computed at `gpt-6.1-sol`'s list price

And the event MUST carry `spend.price_fallback` = `true` and a `cost_note` naming `gpt-6.1-sol`

And a response on `gpt-6.1-sol` itself MUST be sent at its list price with no fallback marker

The revise that accepts this proposal MUST co-edit tests/heading-coverage.json with an entry for each of the two new H2 headings, and MUST register any spec-first TODO row in tests/heading-coverage-debt.json. A TODO row's reason MUST name the tier the owed test runs at and the work item that owns it (livespec-dev-tooling-6vnjbi); the owed test is host-captured, at the integration tier or above, because the emitter is host-local.
