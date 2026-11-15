---
topic: gate-job-cpu-limit
author: claude-opus-5-5
created_at: 2026-11-15T07:00:51Z
---

## Proposal: A full-size gate Job's CPU limit equals its CPU request

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Every full-size delegated gate Job sets a CPU limit equal to its effective CPU request: the declared gate_cpu, or the renderer's default when gate_cpu is absent. This replaces the deliberate no-CPU-limit posture, so a gates-cq lane quota bounds real cores.

### Motivation

A gate Job today requests CPU but sets no CPU limit, so an admitted gate bursts onto every idle core. The quota only counts requests. Measured over the 12 h to 2026-11-15 ~07:00Z (Honeycomb k8s.pod.cpu.usage), livespec-orchestrator-beads-fabro gate pods requesting 5 cpu reached a P90 of 26.2 cores on gmktec-xubuntu and 48.4 on poweredge-xubuntu. Two such gates in gmktec's 10-cpu lane took 32.4 of 32 cores by node cgroups, and the BestEffort CI runner slice read full avg60 38-40. Because BestEffort pods carry the minimum CPU weight, they lose to any Burstable gate under contention. A lane quota therefore stops meaning cores, and CI starves. Plan gate-job-resources research note 004 records the measurements. Item (i) first fixes the request (the orchestrator declares gate_cpu 10 and gate_parallelism 10), and that limits co-resident gates through admission only. This proposal is the queued next lever. It is to be revised only if the +2 h read after item (i) shows CI starvation persisting. It aligns with the in-flight livespec-dev-tooling#4565 (per-node-cpu-budget-honest-requests), which resizes requests to measured draw. Once a limit exists, a request is also a ceiling, so #4565's default must be sized from P90 draw rather than from the mean.

### Proposed Changes

In SPECIFICATION/contracts.md, §"Delegated pre-push gate", **Declared gate resources**, *Keys*: change the `gate_cpu` bullet to read: "`gate_cpu` is a positive TOML integer, the gate Job container's CPU request AND its CPU limit." Then append to *Passing*, after the defaults sentence: "Every full-size gate Job MUST set its container's CPU limit equal to its effective CPU request: the declared `gate_cpu`, or the renderer's default CPU when `gate_cpu` is absent. A gates-cq lane's nominal CPU quota then bounds the cores its admitted gates can use. A Red-leg or Green-leg replay Job of **Replay Job size** MUST likewise set its CPU limit equal to its CPU request of `2`." In `ci-runner/k3s/phase2/gates/gate-job-template.yaml`, the realization replaces the comment 'No cpu limit, deliberately' with a `cpu: "@@CPU@@"` limit; the template is outside the spec tree and is named only so the implementing item can find it. In SPECIFICATION/scenarios.md add:

## Scenario: a full-size gate Job's CPU limit equals its CPU request

Given a consuming repository that declares `gate_cpu = 10` under `[tool.livespec_dev_tooling]`
And a second consuming repository that declares no `gate_cpu`
When the gate client renders a full-size pre-push gate Job for each
Then the first Job's container MUST request CPU `10` and MUST carry a CPU limit of `10`
And the second Job's container MUST request the renderer's default CPU and MUST carry a CPU limit equal to that default

The implementing change MUST add that scenario's row to `tests/heading-coverage.json` in the same commit.
