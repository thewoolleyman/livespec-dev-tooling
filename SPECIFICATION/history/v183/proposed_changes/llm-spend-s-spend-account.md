---
topic: llm-spend-s-spend-account
author: claude-opus-5-5
created_at: 2026-11-10T04:27:17Z
---

## Proposal: LLM-spend account attribution: observed from the sending credential, or marked inferred, with an alarm for unattributed billing

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add §"LLM-spend account attribution". Every `llm-spend` event that carries `spend.account` MUST say whether that account was read from the credential that sent the response (`spend.account_observed`). Factory dispatchers MUST record the label of the credential they project, so factory spend is observed. A trigger MUST fire when an account consumes usage in an hour with no observed spend. A scenario pins the factory case.

### Motivation

Work item livespec-dev-tooling-n277mo. Measured 2026-11-10: the protected account anthropic-0 billed pay-as-you-go from 02:12Z ($3.85, rising to $42.29 by 04:12Z, about $37/h).

`llm-spend` could not name the consumer:
- Every emitter infers `spend.account`. Local transcripts and claude -p use caam's active timeline; factory nodes use caam's selection history, because the dispatcher records the credential it projects nowhere.
- So from 01:30Z every Claude cost row (about $560) was labelled anthropic-1, and anthropic-0 appeared only on $0 rotator rows.

The burn could only be looked for outside the telemetry, by comparing process environments by hash, and two hosts needed root to finish the check. An observed account field, plus an alarm for usage with no observed spend, would have named the consumer in one query.

The section is non-functional because `llm-spend` is fleet-internal infrastructure that no governed project inherits. It sits beside §"LLM-spend telemetry pricing", which already scopes "every emitter writing" the dataset. Fleet scope: every `llm-spend` emitter, plus each factory host's dispatcher.

### Proposed Changes

Add a new `## LLM-spend account attribution` section to `SPECIFICATION/non-functional-requirements.md`. Place it directly after `## LLM-spend telemetry pricing`, with this text:

```markdown
## LLM-spend account attribution

**Scope.** This section governs the account that every emitter writing the fleet observability surface's `llm-spend` dataset (the `livespec` Honeycomb environment) records for a model response, whether local or factory and Anthropic or OpenAI. It is a sibling of §"LLM-spend telemetry pricing", which governs the same emitters' cost fields. A spend ranking by account, and the fleet's ability to see a login it did not select billing, read these fields.

**Observed or marked inferred.** An event that carries `spend.account` MUST also carry `spend.account_observed`. It MUST be `true` only when the account was read from the credential that response was actually sent with. Two readings qualify: the account label of the credential the calling component projected into the process that sent the request, recorded by that component when it projected it; or the authenticated identity of the session that sent the response. It MUST be `false` when the account was derived from any other source, such as the account a credential rotator had selected or had active at the response's time. `spend.account_source` MUST name the method used in either case. An emitter MUST NOT record any credential value, or any digest of one, in an event; it records the account label only.

**The factory records what it projected.** Every factory dispatcher that projects an LLM credential into a run MUST write, at dispatch, a record naming the account label of each credential it projected into that run, keyed by the run's dispatch id. That record MUST be readable by the factory spend emitter on the same host. The factory spend emitter MUST take a factory node's `spend.account` from that record and set `spend.account_observed` = `true`. Only when no record exists for the dispatch MAY it fall back to an inferred account, with `spend.account_observed` = `false`.

**Unattributed billing raises an alert.** A fleet trigger MUST fire when a credential rotator's usage reading for an account shows that account consumed usage (its usage-window drop, or a pay-as-you-go or extra-usage balance where the rotator reads one) during an hour in which `llm-spend` holds no event for that account with `spend.account_observed` = `true`. The trigger MUST name the account. This makes a login that nobody selected, but that something is billing, visible within the hour rather than only from the provider's invoice.
```

Add one scenario to `SPECIFICATION/scenarios.md`, after `## Scenario: a token-bearing response on a model the LLM-spend price table does not list is sent at a marked fallback price`:

```markdown
## Scenario: a factory response sent on a credential the rotator did not select is attributed to the credential's own account

Given the credential rotator's selected Anthropic account is `anthropic-1`
And a factory dispatcher projects the credential labelled `anthropic-0` into a run and records that label against the run's dispatch id
When that run's node sends a response and the factory spend emitter writes it to the `llm-spend` dataset
Then the event carries `spend.account` = `anthropic-0` and `spend.account_observed` = `true`
And no event for that response carries `spend.account` = `anthropic-1`
```

At revise time, the new `## ` heading and the new scenario heading each need a `tests/heading-coverage.json` entry, co-edited in the revise commit. A spec-first `"test": "TODO"` row MUST name the tier the owed test runs at, carry `"work_item": "livespec-dev-tooling-n277mo"`, and be registered through `just generate-heading-coverage-debt-register`.
