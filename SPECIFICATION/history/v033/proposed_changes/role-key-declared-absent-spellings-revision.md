---
proposal: role-key-declared-absent-spellings.md
decision: accept
revised_at: 2026-07-28T15:49:48Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-5
---

## Decision and Rationale

MAINTAINER RULING 2026-07-28: ACCEPT ALL FOUR proposals, relayed through the rop-railway-enforcement supervisor. Accepted as filed; no proposal was reworded while being applied. Proposal 1 retires declared-empty as the sanctioned opt-out for the five UNION role keys and replaces it with the four blessed declared-absent spellings, each requiring a non-empty payload, plus the transitional status of a bare []/'' (accepted with a WARN today; a hard load-time error once every consumer has migrated, which all eight Python-bearing consumers now have). Proposal 2 preserves [] as a legitimate spelling for the five CLEAN keys and states the partition criterion normatively, because for those keys emptiness removes exemptions rather than files and 'tidying' them into the union would be a measured regression. Proposal 3 ratifies the ratified-constraint discriminator and the cross-tracker liveness requirement for unarmed_until; the maintainer accepted it on the stated terms that it binds future consumers AND gives the four repos currently declaring pure_trees = unarmed_until a spec-level obligation to eventually arm it rather than defer indefinitely. Proposal 4 adds the five acceptance scenarios that pin the observable behavior, since this project requires behavior to be carried by a Gherkin scenario rather than by prose alone. The heading-coverage registry entries land atomically in the same commit; they are recorded as TODO with the required integration-tier acknowledgement and each names the unit-tier test that already asserts the property, except the unarmed_until liveness scenario, which is deliberately unimplemented pending a cross-tenant vantage decision.

## Resulting Changes

- contracts.md
- scenarios.md
