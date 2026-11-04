---
topic: radar-admission-function
author: claude-opus-5-5
created_at: 2026-11-04T18:38:46Z
---

## Proposal: Radar admission function: one pure function decides every ready radar target, with recorded rules and numbers

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add an H2 `## Radar admission function` to non-functional-requirements.md and five scenarios. The H2 makes one pure function, fed only by the validated radar, its readiness snapshot, a committed execution-target inventory, a committed thresholds file and the Honeycomb snapshot, decide for every READY radar target whether it is admitted and where, recording the rule and the numbers behind every admit and every refusal. It fixes the two placement rules (the highest-ordered ready target goes to any target with headroom for its run-class p90 cost; a lower-ordered one only backfills a target no higher-ordered waiting target can use), puts thresholds in data with enter and exit values, derives every cap from a named throughput measurement, makes a new execution target one inventory entry, and holds the function in shadow mode: its decisions are logged and no launcher acts on them until this specification names that launcher.

### Motivation

Plan radar-and-deterministic-admission (epic livespec-dev-tooling-w7ley3), slice 3, plan assertions 13-15. Slice 1 (`## Maintainer radar`) and slice 2 (`## Scheduler Honeycomb input contract`, `## Execution-target pressure telemetry`) are ratified; the function that consumes them has no governing heading, so any slice-3 child would be refused at screen as spec-change tier. The maintainer's words, attended, 2026-11-02: "All of the inputs to the pure function are also codified and not non-deterministic via LLMs."; "the data going into this function should always come from Honeycomb unless Honeycomb is actually down or inaccessible". Coordinator ruling R301 (2026-11-02) and `.ai/ci-node-capacity-reads.md` require caps derived from throughput, never from a utilisation percentage alone, because load average and utilisation misread capacity on this fleet (2026-09-08). Placement: the admission function is the fleet coordinator's own scheduling infrastructure, which no project merely governed by livespec inherits, so per the Boundary litmus it belongs in non-functional-requirements.md beside the three radar clauses. Hysteresis is reconstructed from the Honeycomb snapshot's own series rather than from a stored previous state, so the function keeps exactly the five inputs plan assertion 13 names and stays pure. Shadow mode is the charter's slice-3 rule: launch authority moves only in a later slice, after shadow-mode disagreements are resolved. Topic slug default-aligned with the open spec work surveyed on 2026-11-04 (alert thresholds, dev-host platforms, runner placement, local gate concurrency, sandbox naming, agent hook refusal); none touches the radar clauses.

### Proposed Changes

1. Add to `SPECIFICATION/non-functional-requirements.md`, after `## Execution-target pressure telemetry`, a new H2, `## Radar admission function`, with this body:

The radar admission function decides, for every radar target that §"Maintainer radar" reports READY, whether it is admitted and on which execution target. It MUST be one pure function in this repository's `livespec_dev_tooling/radar/` package. Its inputs MUST be exactly these five:

- the validated radar returned by the radar load entry point;
- the readiness snapshot computed from that radar;
- the committed execution-target inventory file;
- the committed thresholds file;
- the Honeycomb snapshot read under §"Scheduler Honeycomb input contract", or that clause's fallback defaults.

The function MUST perform no I/O: it MUST NOT read the ledger, query Honeycomb, read a file or read the clock. Its callers read the inputs and pass them in. The same inputs MUST produce the same output byte for byte.

**Every ready target gets a decision.** The output MUST hold exactly one decision for every READY target, in radar order, and a READY target MUST NOT be omitted. A decision MUST be either `admit`, naming the execution target and the rule id that admitted it, or `refuse`, naming the rule id and the numbers it compared: the measured value, the threshold or cost it was compared with, and the execution target. DONE and NOT READY targets receive no decision. A decision made from fallback inputs MUST carry `inputs: fallback` with the failure reason, as §"Scheduler Honeycomb input contract" requires.

**Placement rules.** A run class is the key that per-run cost is grouped by. For a factory run it is the name of the Fabro workflow the run executed, such as `implement-work-item`, as the run's terminal dispatch span reports it. For local work on the dev host it is the kind of that work: `gate`, `replay` or `interactive`. Each READY target has a run class, and each run class has a cost read from the Honeycomb snapshot: its p90 CPU-seconds, its p90 peak memory and its concurrency cost. An execution target's headroom is what its measured readings and its thresholds leave free, less the cost of every target already admitted to it in the same decision. The function MUST decide targets in radar order and apply these two rules:

- The highest-ordered READY target not yet decided MUST be admitted to an execution target whose headroom covers its run-class cost, whenever any inventory target accepting its run class has such headroom.
- A lower-ordered READY target MUST be admitted to an execution target only when no higher-ordered READY target that was refused could use that execution target's remaining headroom. A lower-ordered target MUST NOT take capacity a higher-ordered waiting target could have used.

When no execution target can admit a target, its decision MUST be `refuse` naming, for each execution target that accepts its run class, the observable that did not fit and the two numbers compared.

**Thresholds are data, with hysteresis.** Thresholds MUST live in one committed data file, holding an `enter` and an `exit` value per observable and per execution target. An execution target MUST stop admitting on an observable when that observable's reading reaches `enter`, and MUST NOT admit on it again until the reading falls back past `exit`. The function MUST derive that state from the Honeycomb snapshot's own series for the observable, replayed oldest to newest from a clear state through the `enter` and `exit` rule, and MUST NOT read any stored previous state. Every concurrency cap in the thresholds file MUST name the measured throughput figure it is derived from: the figure, its unit, the date it was measured and the query that measured it. A cap MUST NOT be derived from a utilisation percentage alone. The function's load of the thresholds file MUST refuse a cap that names no throughput figure.

**Execution targets are inventory entries.** The committed inventory file MUST hold one entry per execution target, naming its `host.name` and the run classes it accepts. Adding an execution target MUST need only a new inventory entry, plus that target's thresholds-file values; it MUST NOT need a change to the function's code.

**Shadow mode.** Every decision the function makes MUST be appended to a decision log on the host that ran it. Each log record MUST carry the tick's UTC time, the radar index, the target as `<tenant>:<id>`, the run class, the decision, the execution target when admitted, the rule id, the numbers compared, and whether the inputs were `honeycomb` or `fallback`. No launcher MAY start, hold or cancel a launch on the function's output until this specification names that launcher as a consumer of the function.

2. Add to `SPECIFICATION/scenarios.md` five new scenarios:

## Scenario: the radar admission function decides every ready target identically on identical inputs

Given a radar whose readiness snapshot reports targets `A`, `B` and `C` READY and target `D` NOT READY

And a fixed inventory file, thresholds file and Honeycomb snapshot

When the admission function runs twice on those same inputs

Then the two outputs MUST be identical byte for byte

And each output MUST hold exactly one `admit` or `refuse` decision for each of `A`, `B` and `C`, and none for `D`

And every `refuse` decision MUST name its rule id and the numbers it compared

## Scenario: the highest-ordered ready target is admitted to any execution target with headroom for its cost

Given radar targets `A` at index 1 and `B` at index 2 are READY, and their run class has a p90 cost of 600 CPU-seconds, 4 GiB peak memory and 1 slot

And execution target `gmktec-xubuntu` has headroom of 0 slots, and execution target `hp-xubuntu` has headroom of 1 slot, 2000 CPU-seconds and 8 GiB

When the admission function runs

Then `A` MUST be admitted to `hp-xubuntu` with its rule id

And `B` MUST be refused with a rule id and the slot numbers compared for each execution target

## Scenario: a lower-ordered target does not backfill an execution target a higher-ordered waiting target could use

Given radar target `A` at index 1 is READY with a run class that needs 8 GiB peak memory, and target `B` at index 2 is READY with a run class that needs 1 GiB

And execution target `hp-xubuntu` has 6 GiB of memory headroom and accepts both run classes, and execution target `poweredge-xubuntu` has 12 GiB and accepts only `B`'s run class

When the admission function runs

Then `A` MUST be refused naming 8 GiB against 6 GiB on `hp-xubuntu`

And `B` MAY be admitted to `hp-xubuntu` or `poweredge-xubuntu`, because `A` could use neither

And when `hp-xubuntu`'s memory headroom is raised to 9 GiB, `A` MUST be admitted to `hp-xubuntu` and `B` MUST NOT be admitted to `hp-xubuntu` ahead of it

## Scenario: an execution target stays closed until its reading falls back past the exit threshold

Given the thresholds file sets memory pressure `enter` 20 and `exit` 10 for `hp-xubuntu`

And the Honeycomb snapshot's memory-pressure series for `hp-xubuntu` reads 5, then 25, then 15, oldest first

When the admission function runs with a READY target whose run class `hp-xubuntu` accepts

Then the function MUST NOT admit it to `hp-xubuntu`

And the refusal MUST name the memory-pressure rule and the numbers 15 and 10

And when the series instead ends 25, then 8, the function MUST treat `hp-xubuntu` as admitting again

## Scenario: a new execution target is admissible from one inventory entry

Given an inventory fixture listing `gmktec-xubuntu` and `hp-xubuntu`, both without headroom for a READY target's run class

When one inventory entry for `hetzner-xubuntu` accepting that run class is added, with its thresholds-file values and a Honeycomb snapshot giving it headroom

Then the admission function MUST admit the target to `hetzner-xubuntu`

And the change MUST touch no file other than the inventory file, the thresholds file and the snapshot fixture
