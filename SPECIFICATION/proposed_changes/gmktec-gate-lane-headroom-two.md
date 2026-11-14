---
topic: gmktec-gate-lane-headroom-two
author: claude-opus-5-5
created_at: 2026-11-14T17:41:40Z
---

## Proposal: The gmktec gate lane floor drops from three default-size gate Jobs to two

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Lower the Gate lane headroom floor of the gmktec-xubuntu gates-flavor lane from three default-size gate Jobs (15 CPU, 18Gi) to two (10 CPU, 12Gi). The floor stays derived from the renderer's default request and still keeps one undeclared full-size Job admissible. A later capacity change with its own G2 read and trigger moves the committed lane.

### Motivation

The floor of three keeps the gmktec-xubuntu node's CPU mostly in gates, and that starves its CI runners. gmktec has 32 cores. Measured on 2026-11-14 (Honeycomb, SUM of k8s.pod.cpu.usage on gmktec by namespace), the shares were:
- 15:33-17:38Z: gates 73.7%, arc-runners 13.3%, factory 12.8%;
- 13:30-15:33Z: gates 67.8%, arc-runners 14.1%, factory 18.0%.

Node CPU P50 is 31.9 of 32. legacy-coordinator-agent's fleet-utilization section flagged gmktec OVERCOMMIT at 16:36Z (idle 0.2%, kubepods-besteffort cpu.pressure full avg60 35.62) and again at 17:18Z (idle 0.1%, avg60 31.37).

The six CI runners gmktec's churn slots allow are BestEffort, and three Burstable 5-CPU gates outweigh them on CFS weight. So the slots are held while the jobs crawl.

Meanwhile the gate lanes have spare capacity. Since the PowerEdge lane went 30 -> 20 CPU (livespec-dev-tooling#4635, 15:33Z), gates-cq has had 0 pending: 46 workloads were admitted with 0 min wait, and the PowerEdge lane used 10 of 20 CPU at 17:38Z. The dev-tooling gate p50 per lane after that apply was M4 10.5, gamingpc 10.7, gmktec 17.3 and poweredge 16.2 min.

A two-Job floor still keeps a full-size, undeclared Job admissible, which is what **Lane capacity** relies on.

This is plan gate-job-resources' gmktec gate-lane lever (epic livespec-dev-tooling-ukoeah), held since 2026-11-14 for #4635's +2 h read. That read found both of the lever's inputs held: gmktec runner share under 15% and gates-cq at 0 pending. legacy-coordinator-agent ruled that a cut below this floor is a propose-change to this clause, not a capacity PR.

Expected effect, so the read after the later capacity change can test it: with two gates instead of three, about 6 of gmktec's ~19 gate cores free up. They go to the BestEffort CI and factory pods, which today split CPU about evenly. gmktec's arc-runners share of pod CPU should rise from 13.3% to at least 20% over the 2 h after that apply.

The G2 pair for that capacity change:
- the +2 h read, owned by gate-job-resources: gates-cq pending, the gate p50 per lane, and gmktec's CI-slice CPU pressure and arc share;
- the revert trigger: restore 15 CPU if gates-cq holds at least 1 pending for 15 min or more in the 6 h after the apply.

Fleet scope: one lane, gmktec-xubuntu's `gates-flavor`. No other lane has a floor clause.

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated pre-push gate", replace the **Gate lane headroom.** bullet with:

```
- **Gate lane headroom.** The committed `gates-flavor` lane (gmktec-xubuntu) of `cluster-queue-gates.yaml` MUST keep a nominal quota of at least two default-size gate Jobs, at least 10 CPU and at least 12Gi memory, so that it admits at least two concurrent default-size gate Jobs. This floor is part of the schema that the lane's quota must satisfy under §"Tests never pin committed configuration values". The tests of that file MUST fail, naming the lane, when its committed quota is below two times the renderer's default request. They assert that derivation, never a literal quota. A repository's declared resources MAY lower how many of ITS Jobs the lane admits at once. They MUST NOT be met by lowering that lane's quota below this floor.
```

In SPECIFICATION/scenarios.md, replace the scenario "## Scenario: the gmktec gate lane keeps room for three default-size gate Jobs" with:

```
## Scenario: the gmktec gate lane keeps room for two default-size gate Jobs

Given the committed `cluster-queue-gates.yaml`

When its tests run

Then they MUST fail, naming the `gates-flavor` lane, if that lane's nominal CPU quota is below two times the renderer's default CPU request or its nominal memory quota is below two times the renderer's default memory request
```

The revise that accepts this proposal renames that heading's entry in `tests/heading-coverage.json` in the same commit; its test, `tests/spec/test_gates_queue_gate_unit.py::test_the_gmktec_lane_holds_three_default_size_gate_jobs`, moves to the two-Job derivation in the implementing change. Lowering the clause does not by itself change the committed lane: the gmktec `gates-flavor` stays at 15 CPU until a separate capacity change, with its own dated DERIVATION section, CI-side read and revert trigger, moves it to 10 CPU.
