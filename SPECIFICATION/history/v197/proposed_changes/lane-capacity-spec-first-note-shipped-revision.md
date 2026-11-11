---
proposal: lane-capacity-spec-first-note-shipped.md
decision: modify
revised_at: 2026-11-11T21:52:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in substance: livespec-dev-tooling-yznwz7 implemented Lane capacity (livespec-dev-tooling#4199, e8908b3e6), so the note's own instruction that a revise ratifying Lane capacity's implementation MUST update it now applies. MODIFIED because a pre-merge live-state check found the proposal's ownership claim false. The two Lane capacity scenario rows in tests/heading-coverage.json still named the now-closed yznwz7, and 4g7als, which is active and dispatched so its brief is frozen, owns only the other gate-resource scenarios.

## Modifications

The replacement sentence names the correct owners. 4g7als owns the consumer-tier tests of the scenarios of the other sub-bullets. The new plan child livespec-dev-tooling-jgabjo owns those of Lane capacity's two scenarios. The revise commit repoints those two heading-coverage rows from yznwz7 to jgabjo and regenerates tests/heading-coverage-debt.json. Those files are outside the spec target, so they are not carried in resulting_files.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T21:51:35Z
verdict: NO BLOCKERS
proposal_stem: lane-capacity-spec-first-note-shipped
content_digest: 624d1d38a4c519ddc79f14678d4568e33c53965f96775a6a826f028012767180
