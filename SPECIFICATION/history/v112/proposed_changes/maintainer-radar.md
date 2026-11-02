---
topic: maintainer-radar
author: claude-opus-5-5
created_at: 2026-11-02T15:42:25Z
---

## Proposal: Maintainer radar: one typed ordered array, its validation, and blocks-only readiness

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add an H2 `## Maintainer radar` to non-functional-requirements.md and three scenarios. The H2 makes one committed, type-checked, ordered Python tuple the single source of the coordinator's priority order, with no priority number, override or length limit. It defines what a valid radar is, splits validation between `just check` (file-only defects) and one load-time entry point every consumer calls (ledger defects), and computes readiness from `blocks` edges only, with a plan's children taken as the union of dotted-id descendants and `parent-child` edges.

### Motivation

Plan radar-and-deterministic-admission (epic livespec-dev-tooling-w7ley3) is the maintainer's priority 1 (2026-11-02). Its slice-1 children were classified spec-change tier at filing because no ratified heading states this behaviour (livespec-dev-tooling-xhbgdg, linked topic radar-typed-radarentry-schema-the). This proposal gives slice 1 its governing heading and scenarios. The maintainer's words, attended, 2026-11-02: "I would like it represented in some sort of code form as an array so that the ordering cannot be corrupted or misinterpreted with duplicated items"; "There should be a single source of truth, and it should be this type-safe, ordered list of only the things I have told you to have on your radar."; "re override - No ... Overrides will be represented by changing the order."; "agreed, if blocks is the right field ... then use it." The radar is the fleet coordinator's own infrastructure, which no project merely governed by livespec inherits, so per the Boundary litmus it belongs in non-functional-requirements.md. The edge-type and key-spelling rules come from measurements recorded in CLAUDE.md, in the beads read-surface trap catalogue.

### Proposed Changes

1. Add to `SPECIFICATION/non-functional-requirements.md` a new H2, `## Maintainer radar`, with this body:

The coordinator's priority order MUST be held in one committed, type-checked Python module of this repository, `livespec_dev_tooling/radar/radar.py`, which exports `RADAR`, an immutable tuple of `RadarEntry` values. Each entry MUST carry exactly these fields:

- `kind`: `plan` or `item`.
- `tenant`: the ledger tenant that holds the target.
- `id`: the target's id.
- `words`: the maintainer's words that put the target on the radar.
- `said_at`: the date of those words.
- `blocked_by`: zero or more `<tenant>:<id>` references, for blockers the ledger cannot express across tenants.

The tuple index MUST be the only order. An entry MUST NOT carry a priority number, an override or slot marker, and the tuple MUST NOT be length-bounded: urgency is expressed only by reordering, and the radar's length is the maintainer's signal to drop entries. Only the maintainer orders the radar. A session that has evidence the order should change MUST report it as a finding and MUST NOT edit the array itself.

A radar is VALID only when ALL of the following hold:

- No `(tenant, id)` pair appears twice.
- No `item` entry is a child of a `plan` entry listed elsewhere in the radar.
- Every entry, and every `blocked_by` reference, resolves in its tenant's ledger and is not closed.
- Every `plan` entry's epic has a `plan/<slug>/` directory in its tenant's repository.
- Every `blocked_by` reference has the form `<tenant>:<id>` with both parts non-empty.

Defects that need only the committed file MUST fail `just check`. These are duplicate pairs, malformed references and schema violations, the last through the repository's type gate. Defects that need the ledger MUST NOT be checked inside `just check`, because `just check` also runs where no ledger is reachable, and per constraints.md §"No network I/O" a check module performs no network I/O. They MUST instead be checked by the ONE load-time entry point every radar consumer calls, and by a `just radar-validate` recipe run through the credential wrapper. That entry point MUST refuse an invalid radar, naming every defect, and MUST NOT return a partial, cached or previously valid radar in its place.

An entry's target is NOT READY when it is closed, or when any of its blockers is not closed. Its blockers are its ledger `blocks` edges and its declared `blocked_by` references. `parent-child`, `relates-to`, `discovered-from`, `related` and `duplicates` edges MUST NOT block. A plan's children MUST be computed as the union of its dotted-id descendants and the items carrying a `parent-child` edge to its epic, because neither source is complete alone. Readers MUST accept both dependency-row spellings the ledger emits: `depends_on_id` with `type` (from `bd list`) and `id` with `dependency_type` (from `bd show`). Readers MUST read an absent `dependencies` key as no edges.

2. Add to `SPECIFICATION/scenarios.md` three new scenarios:

## Scenario: a radar that lists the same target twice fails just check

Given the committed `RADAR` lists tenant `livespec-dev-tooling`, id `livespec-dev-tooling-abc123` at index 2 and again at index 5
When `just check` runs
Then the aggregate MUST fail
And the failure MUST name `livespec-dev-tooling-abc123` and both indexes

## Scenario: a radar consumer refuses an item already covered by a listed plan

Given the committed `RADAR` lists `plan` entry `livespec-dev-tooling-p1` and, at a later index, `item` entry `livespec-dev-tooling-p1.3`
And `livespec-dev-tooling-p1.3` has a null `parent` field and no `parent-child` edge
When a radar consumer calls the radar load entry point
Then the call MUST refuse with a defect naming `livespec-dev-tooling-p1.3` as a child of `livespec-dev-tooling-p1`
And the consumer MUST receive no radar entries

## Scenario: a related edge does not block a radar target

Given item `I` has a `relates-to` edge to an open item `J`, a `discovered-from` edge to an open item `K`, and a `blocks` edge to a closed item `L`
And `I` is listed on the radar with an empty `blocked_by`
When readiness is computed for `I`
Then `I` MUST be ready
And no open item MUST be named as its blocker
