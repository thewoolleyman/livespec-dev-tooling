---
proposal: pin-currency-escalation-predicate.md
decision: modify
revised_at: 2026-07-31T06:56:17Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-5
---

## Decision and Rationale

ACCEPTED with modifications. The substance stands and is measured rather than reasoned: all four pin-currency rows escalate on exactly one condition -- stale AND a bump PR for the latest release is already open -- so the 'never fired' half of the staleness partition, which produced both the 2026-07-30 seven-hour dev-tooling outage and the still-unrepaired sixteen-hour livespec v0.21.1 outage, could never enter the escalating class whatever severity that class carried. The proposal's two retractions were re-verified against the code before accepting: _pin_currency_outcome already carries the lane-scoped escalation vt61 recommends, and _rows_files._freshness_outcome already covers the pyproject [tool.uv.sources] pin for currency -- so no severity changes here, only a widening of which conditions reach the existing scoping. INTENT-PRESERVATION CHECK, run explicitly: the two design records this section cites are livespec-dh9r (the persisting-gap escalation) and livespec-dev-tooling-6ge (a can't-read is not a violation). Neither is contradicted. dh9r's class is kept verbatim and escalates at any release age; the change EXTENDS dh9r rather than departing from it, and dh9r's own founding incident was measured with 'open bump PRs fleet-wide: 0' -- precisely the state its escalation cannot see, which is the strongest available argument that the partition was always meant to be exhaustive. 6ge is preserved verbatim and reinforced: a can't-PARSE is distinguished FROM a can't-read rather than folded into it, which is 6ge's own 'can't-read is not absent' principle applied to a third input. No lever, no environment variable, no per-member exemption, and no severity is lowered anywhere; the settle window is ratified as a constant precisely so it cannot become an opt-out key.

## Modifications

The proposal targeted contracts.md alone. Per the revise authoring discipline's Behavior-implies-Gherkin split, the amendment introduces observable behavior -- a new escalating staleness class, a bounded settle window, and a can't-parse finding -- so it is malformed as filed. MODIFIED to co-edit the missing artifacts atomically: (1) three '## Scenario' entries added to scenarios.md covering the never-fired class escalating past the window, the never-fired class staying a warning INSIDE the window, and an unparseable pin file being a finding rather than a pass -- each naming the evaluating context so the lane scoping is asserted rather than implied; (2) three paired tests/heading-coverage.json entries, each carrying test: TODO with a tier-acknowledging reason per the scenarios.md integration-tier rule, to be replaced with real node ids when the implementation unit lands. No H2 heading in contracts.md is added, renamed, or removed, so that file needs no coverage co-edit. The contracts.md prose is otherwise the proposal's own, with the settle window fixed at the proposed two hours and dh9r's zero-open-bump-PRs measurement folded into the never-fired bullet as the supporting design-record evidence.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
