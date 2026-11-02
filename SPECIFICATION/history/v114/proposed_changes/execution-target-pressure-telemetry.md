---
topic: execution-target-pressure-telemetry
author: claude-opus-5-5
created_at: 2026-11-02T16:05:51Z
---

## Proposal: Execution-target pressure telemetry: pressure stall information on every execution target and the dev host's host metrics in livespec

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add an H2 `## Execution-target pressure telemetry` to non-functional-requirements.md and three scenarios. The section requires every execution target (gmktec, hp, poweredge and the dev host) to emit cpu, memory and io pressure stall information (some and full; avg10, avg60, avg300) to the livespec metrics dataset at most every 60 seconds, stamped with host.name. A host without a pressure file must fail loudly and never emit zeros. The emitter must be converged by Ansible. The dev host's host metrics, including available memory, must reach livespec and not only agent-activity.

### Motivation

This is slice 2 of plan radar-and-deterministic-admission (epic livespec-dev-tooling-w7ley3), the maintainer's priority 1. Its admission function reads its inputs from Honeycomb, and two of those inputs do not exist, measured 2026-11-02. First, cpu and memory pressure are emitted nowhere: io `full avg300` comes only from poweredge's heartbeat, and gmktec, hp and the VPS emit no pressure at all. Second, the VPS ships its host metrics only to the agent-activity environment's `livespec-host-metrics` dataset. A prior-art scan of both ledgers found no item covering either. The maintainer, 2026-11-02: "the data going into this function should always come from Honeycomb". .ai/ci-node-capacity-reads.md records that load average is not CPU busy and that a cap set from a utilisation reading throttled a drain for hours; pressure stall time measures waiting for a resource directly. A host that silently reports zero pressure would admit work onto a saturated host, which is why a missing pressure file must fail.

### Proposed Changes

1. Add to `SPECIFICATION/non-functional-requirements.md` a new H2, `## Execution-target pressure telemetry`, with this body:

**Scope.** This section covers every host the radar admission function can place work on. Those hosts are the execution targets `gmktec-xubuntu`, `hp-xubuntu` and `poweredge-xubuntu`, and the dev host (the VPS) for local work. It is the input side of §"Scheduler Honeycomb input contract", and it adds to §"Runner-pool node telemetry" without replacing it.

**Pressure stall information on every execution target.** Every execution target MUST emit the kernel's pressure stall information to the Honeycomb `livespec` environment's metrics dataset. That means the `some` and `full` lines of `/proc/pressure/cpu`, `/proc/pressure/memory` and `/proc/pressure/io`, each with its `avg10`, `avg60` and `avg300` values. Every datapoint MUST be stamped with `host.name` equal to the host's own name. The emission interval MUST be at most 60 seconds, so every 15-minute window of a running host carries datapoints. A host whose kernel does not expose a pressure file MUST make the emitter exit non-zero with a log line naming the missing file. It MUST NOT emit zeros in its place, because a zero pressure reading would be read as an idle host.

**The dev host's host metrics reach `livespec`.** The dev host's host metrics MUST also arrive in the `livespec` environment's metrics dataset stamped with its `host.name`, not only in the `agent-activity` environment. That includes `system.linux.memory.available`.

**Converged, never hand-installed.** The pressure emitter on every execution target MUST be converged by this repository's Ansible tree from the control node. A hand-run installer MUST NOT be the deployment path, and the drift report of the playbook that converges it MUST report a host whose emitter differs from the merged definition.

2. Add to `SPECIFICATION/scenarios.md` three new scenarios:

## Scenario: an execution target's pressure stall readings are queryable in livespec by host

Given the pressure emitter is converged on `gmktec-xubuntu`
When 15 minutes pass with the host running
Then the `livespec` environment's metrics dataset MUST hold `some` and `full` readings for cpu, memory and io with `avg10`, `avg60` and `avg300` values stamped `host.name` = `gmktec-xubuntu` within that window

## Scenario: a host with no pressure file makes the emitter fail rather than report zero

Given a host whose kernel exposes no `/proc/pressure/memory`
When the pressure emitter runs
Then the emitter MUST exit non-zero with a log line naming `/proc/pressure/memory`
And no memory pressure datapoint MUST be emitted for that host in that run

## Scenario: the dev host's available memory is queryable in livespec

Given the dev host's collector is converged from the merged configuration
When 15 minutes pass
Then the `livespec` environment's metrics dataset MUST hold `system.linux.memory.available` stamped with the dev host's `host.name` within that window
