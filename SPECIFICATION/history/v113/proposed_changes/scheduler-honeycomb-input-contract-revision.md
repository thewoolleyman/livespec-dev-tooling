---
proposal: scheduler-honeycomb-input-contract.md
decision: modify
revised_at: 2026-11-02T16:09:48Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:radar-and-deterministic-admission
---

## Decision and Rationale

The Honeycomb input contract is the plan's stated prerequisite and has no governing heading. The proposal states the maintainer's 2026-11-02 rulings as BCP14 clauses, each backed by one of three scenarios. Inputs come from Honeycomb by code and never by an LLM. They are codified and protected from drift by integration and unit tests. One holistic view gathers them. Sensible fallback defaults cover an outage. It honours the Pro-plan constraint by routing through the MCP endpoint, and it leaves the budget number to measurement per coordinator ruling R301.5. The reviewer made non-blocking notes: the admission function and the coordinator printout are defined by later slices, and the reader item must expose the endpoint override used in the outage scenario.

## Modifications

Adds the reviewer's two non-blocking notes to the clause. The reader accepts an endpoint override, which the outage scenario already uses. The reader and the live contract test sit outside `just check`.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T16:09:45Z
verdict: NO BLOCKERS
proposal_stem: scheduler-honeycomb-input-contract
content_digest: ca8ae762b666f63860f5d7345e146027a7ea7a85360e98dbe9ae0cc7d538c4bd
