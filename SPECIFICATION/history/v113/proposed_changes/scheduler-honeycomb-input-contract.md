---
topic: scheduler-honeycomb-input-contract
author: claude-opus-5-5
created_at: 2026-11-02T15:45:51Z
---

## Proposal: Scheduler Honeycomb input contract: named query specs, a counted per-tick budget, contract tests and a flagged fallback

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add an H2 `## Scheduler Honeycomb input contract` to non-functional-requirements.md and three scenarios. Every measured input to the radar admission function becomes a named query spec in code, read through the Honeycomb MCP endpoint with no LLM involved. The per-tick query set is counted against a measured budget constant and cached for the tick. A live contract test fails on a missing column, a type change or stale data. The specs publish one required-attribute file and generate the `scheduler inputs` board, which has a drift mode. When Honeycomb is unreachable, the reader returns fixed fallback defaults, flags every decision made from them, prints an outage line above the radar, and files a work item.

### Motivation

This is slice 2 of plan radar-and-deterministic-admission (epic livespec-dev-tooling-w7ley3), the maintainer's priority 1, and its prerequisite. The maintainer, attended, 2026-11-02: "the data going into this function should always come from Honeycomb unless Honeycomb is actually down or inaccessible. In that case, there should be some sensible fallback defaults ... All of the inputs to the pure function are also codified and not non-deterministic via LLMs." and "making all of the Honeycomb data available and codifying it so that the API is extremely clear and doesn't drift or get broken should be a prerequisite of this plan. There should be clear integration tests and unit tests ... ideally this is some holistic grouping or view or report that gathers all of the stuff this script or scripts rely on". The Pro-plan constraint (no REST Query Data API) is recorded in .ai/honeycomb-query-credential.md. Coordinator ruling R301.5 says the budget is measured, not guessed, so the clause requires a measured constant rather than naming a number.

### Proposed Changes

1. Add to `SPECIFICATION/non-functional-requirements.md` a new H2, `## Scheduler Honeycomb input contract`, with this body:

Every measured observable that the radar admission function consumes MUST be read from the Honeycomb `livespec` environment by code, never by an LLM. That covers host pressure, available memory, node allocatable against requested resources, live runs per execution target, and per-run-class cost percentiles. The reader MUST query through the Honeycomb MCP endpoint (`https://mcp.honeycomb.io/mcp`) with the MCP key that `with-livespec-env.sh` injects, because the team's Pro plan has no REST Query Data API.

Each query MUST be a named query spec committed in code. A spec names:

- its dataset;
- its calculations, filters and breakdowns;
- its time window;
- every expected result column with that column's type;
- a staleness bound.

The set of specs one admission tick runs MUST be fixed and counted. A unit test MUST fail when that count exceeds the committed per-tick budget constant. Results MUST be cached for the duration of a tick, so a repeat read inside the tick spends no query. The constant MUST be set from a measurement of the other callers' share of the MCP key's hourly budget, recorded beside it, and MUST NOT be set from an estimate.

A contract test, run against live Honeycomb through the credential wrapper, MUST fail for a spec in each of these cases:

- a result is missing an expected column;
- a column's parsed type differs from the spec;
- the newest row is older than the spec's staleness bound.

The required attribute and column set MUST be published from one committed file that other repositories' gates read, never duplicated. A Honeycomb board named `scheduler inputs` MUST be generated from the specs by a committed applier, whose read-only drift mode reports every difference between the live board and the generated definition.

When the endpoint is unreachable, returns an error, or the per-tick budget is exhausted, the reader MUST return the fixed conservative defaults from a committed fallback table. Every decision made from those defaults MUST carry `inputs: fallback` together with the failure reason. The coordinator's printout MUST show a `HONEYCOMB UNREACHABLE since <UTC>` line above radar entry 1, and a work item for the outage MUST exist in the ledger within one tick. The reader MUST NOT reorder or edit the radar array.

2. Add to `SPECIFICATION/scenarios.md` three new scenarios:

## Scenario: a Honeycomb query spec whose result lacks an expected column fails its contract test

Given a committed query spec that expects column `p90_cpu_seconds` of type float
When the contract test runs that spec against live Honeycomb and the result has no `p90_cpu_seconds` column
Then the contract test MUST fail naming the spec and the missing column

## Scenario: an unreachable Honeycomb endpoint yields flagged fallback decisions

Given the MCP endpoint override names a host that does not resolve
When an admission tick runs
Then every decision in that tick MUST carry `inputs: fallback` with the failure reason
And the coordinator printout MUST show a `HONEYCOMB UNREACHABLE since <UTC>` line above radar entry 1
And the radar array MUST be unchanged

## Scenario: a per-tick query set larger than the budget constant fails the unit tests

Given the per-tick budget constant is N
When a change adds query specs so that one tick would run N + 1 queries
Then the unit test that counts the per-tick set MUST fail naming the count and the constant
