---
topic: gate-lane-headroom-floor-is-one-default-size-gate-job
author: gate-job-resources-session
created_at: 2026-11-19T23:15:04Z
---

## Proposal: The gmktec gate lane's headroom floor is one default-size gate Job

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Lower the ratified gmktec-xubuntu gates-flavor floor of section "Delegated pre-push gate" bullet **Gate lane headroom** from two default-size gate Jobs (at least 10 CPU and 12Gi memory) to ONE (at least 5 CPU and 6Gi memory), and rename and re-word the one scenario that states it. v223 lowered this same floor from three Jobs to two, so there is precedent for moving it on measurement.

### Motivation

Measured 2026-11-19 (kubectl, live, read by gate-job-resources and recorded on plan epic livespec-dev-tooling-ukoeah at 23:03:18Z, ruled on by legacy-coordinator-agent at 23:05Z): gmktec-xubuntu allocatable memory is 62.43 GiB. Its factory pods request 52.2 GiB (7 pods at 7630Mi each; committed factory_pod_budget 7), system pods 1.1 GiB. The ratified floor of two default gate Jobs is 12Gi, so floor 12 + factory 52.2 + system 1.1 = 65.3 GiB, 2.9 GiB over the node even with no repro lane; with the live 8Gi repro lane the claims are 77.3 GiB. No value satisfies the ratified floor, the committed factory budget and a gmktec repro lane together, and a gate Kueue admits can sit Pending for memory while the factory is full. The maintainer chain ruled (legacy-coordinator-agent, 2026-11-19, option B): the factory slot is the throughput resource and gate capacity elsewhere is large (poweredge-xubuntu gates quota 30 CPU / 48Gi on a node that read 90% idle, gamingpc-xubuntu 10 CPU / 16Gi, the homelab worker one 5 CPU / 8Gi arm64 lane), so keep factory at 7 pods, keep the gmktec repro lane off, and lower this floor to one gate. At one gate the claims are floor 6 + factory 52.2 + system 1.1 = 59.3 GiB against 62.43, 3.1 GiB spare. Rollback (same ruling): restore the 12Gi two-gate floor and re-enable the gmktec repro lane, with the memory budget file still in report-only mode. Related carriers on the plan: livespec-dev-tooling-zluwhb (memory budget, report-only) and livespec-dev-tooling-hosvm7 (gmktec applied resolution; blocked on this revise).

### Proposed Changes

(1) In SPECIFICATION/contracts.md section "Delegated pre-push gate", replace the bullet **Gate lane headroom** with this text, which changes only the floor figure and its two derived phrases and keeps every other sentence:

- **Gate lane headroom.** The committed `gates-flavor` lane (gmktec-xubuntu) of `cluster-queue-gates.yaml` MUST keep a nominal quota of at least one default-size gate Job, at least 5 CPU and at least 6Gi memory, so that it admits at least one default-size gate Job. This floor is part of the schema that the lane's quota must satisfy under §"Tests never pin committed configuration values". The tests of that file MUST fail, naming the lane, when its committed quota is below the renderer's default request. They assert that derivation, never a literal quota. A repository's declared resources MAY lower how many of ITS Jobs the lane admits at once. They MUST NOT be met by lowering that lane's quota below this floor.

(2) In SPECIFICATION/scenarios.md replace the scenario heading and body "## Scenario: the gmktec gate lane keeps room for two default-size gate Jobs" with:

## Scenario: the gmktec gate lane keeps room for one default-size gate Job

Given the committed `cluster-queue-gates.yaml`

When its tests run

Then they MUST fail, naming the `gates-flavor` lane, if that lane's nominal CPU quota is below the renderer's default CPU request or its nominal memory quota is below the renderer's default memory request

(3) HEADING COVERAGE: this proposal renames one `## ` heading in scenarios.md (the scenario above) and adds or removes no other. The revise commit owes tests/heading-coverage.json one row for the new heading. Its current row maps the old heading to tests.spec.test_gates_queue_gate_unit.test_the_gmktec_lane_holds_two_default_size_gate_jobs, which asserts two Jobs through the constant _HEADROOM_GATES = 2 and is renamed and changed by livespec-dev-tooling-hosvm7 together with the committed quota change, so the new row is a spec-first `"test": "TODO"` whose reason names the unit-and-spec tier, owner livespec-dev-tooling-hosvm7 (`work_item` key), and the revise registers it with just generate-heading-coverage-debt-register. The old row is dropped. The tests/spec/test_gates_queue_gate_unit.py constant and function name, ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml, its DERIVATION.md and the gmktec gate quota are implementation and are changed by hosvm7 after this revise lands, never ahead of it: until then the committed lane (10 CPU / 16Gi) still satisfies both the old and the new floor. (4) After ratification livespec-dev-tooling-hosvm7's Definition of Done References line is repointed to the new scenario heading verbatim, in the same tick as the merge.
