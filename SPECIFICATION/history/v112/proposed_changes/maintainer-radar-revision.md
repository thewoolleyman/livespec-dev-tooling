---
proposal: maintainer-radar.md
decision: modify
revised_at: 2026-11-02T16:09:20Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:radar-and-deterministic-admission
---

## Decision and Rationale

The radar has no governing heading, and plan radar-and-deterministic-admission's slice-1 children were classified spec-change tier for that reason. The proposal states the maintainer's 2026-11-02 rulings as BCP14 clauses, each backed by one of three scenarios. It sits in non-functional-requirements.md under the Boundary litmus, because it is fleet coordinator infrastructure that no governed project inherits. It keeps ledger-reading validation out of `just check`, consistent with constraints.md 'No network I/O'.

## Modifications

Resolves the ratification reviewer's blocker: the validity and readiness rules contradicted each other on closed targets. A closed entry is now DONE. Load reports it as a finding, and `just radar-validate` refuses it on edit. It no longer invalidates the radar at load, because a radar entry closing would otherwise stall every consumer, against the maintainer's 2026-11-02 rule that the factory never stalls out. The maintainer's 'open' requirement on the array is kept at edit time. A closed `blocked_by` target is a cleared blocker. Also states that the `just check` failure names each defect.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T16:09:19Z
verdict: NO BLOCKERS
proposal_stem: maintainer-radar
content_digest: 6c4cb932cf96f56e76befb537305ee641d73e6655233f24b1e589997a6838d0a
