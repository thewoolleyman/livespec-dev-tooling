---
topic: dev-host-no-data-triggers
author: claude:kubernetes-observability-seat-230b17
created_at: 2026-11-13T18:18:27Z
---

## Proposal: A silent dev host fires a per-host no-data trigger

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend §"Execution-target pressure telemetry" so that a dev host which stops sending its host metrics to the `livespec` environment fires a trigger. For every `livespec.host.role` a committed collector shape stamps, the fleet carries one ungrouped no-data trigger per host. Each trigger is generated from one committed host list per role, converged by `apply-triggers.sh` and covered by its drift mode, and notifies the same recipients as that role's value triggers. Add a scenario that proves the trigger fires on a stopped collector and resolves when it restarts.

### Motivation

Filed 2026-11-13 by the kubernetes-observability seat on legacy-coordinator-agent's direction (work item livespec-dev-tooling-exx6f5, a child of plan epic livespec-dev-tooling-s2aqob). livespec-dev-tooling#4542 adds three dev-host value triggers: available-memory share, tmpfs fill, and the 8 GiB available-memory floor. All three are broken down by `host.name`. A host that stops reporting leaves no group, so none of them can fire on silence. In the 2026-11-13 ~15:32Z vmi3006760 outage, memory exhaustion OOM-killed Dolt and pushed load toward 400, and a host in that state can stop exporting entirely. The spec already requires an ungrouped per-node dead-man for every k3s pool node (§"Runner-pool node telemetry") because a grouped query cannot fire on a silent subject. The spec-change tier record for exx6f5 (spec v212) found no clause requiring the same for a dev host, nor a committed host list that generates the triggers.

### Proposed Changes

1. `non-functional-requirements.md` §"Execution-target pressure telemetry": add a paragraph after **The dev host's host metrics reach `livespec`.**:

```markdown
**A silent role-stamped host fires its no-data trigger.** For every value of `livespec.host.role` that a committed otel-collector shape stamps on its host metrics (`dev-host` is the first), the fleet MUST carry, as code under `ci-runner/observability/triggers/` converged by `apply-triggers.sh`, one no-data trigger per host of that role. Each trigger MUST be ungrouped and filtered to that one `host.name` and role, because a grouped query cannot fire on a silent subject. Each MUST fire when that host sends no `system.linux.memory.available` datapoint to the `livespec` environment for 20 minutes, and MUST notify the same recipients as that role's value triggers. The per-host definitions MUST be generated from one committed host list per role, so that enrolling a host of a covered role changes only that list. The applier's drift mode MUST cover every generated definition. Every trigger description MUST name the emitter path, the receiver path, the owning work item and a runbook, as the pool's existing triggers do. A forced-fire proof MUST stop the host's collector unit rather than load the host.
```

2. `scenarios.md`: add a scenario:

```markdown
## Scenario: a dev host that stops sending host metrics fires its no-data trigger

Given the committed dev-host host list names a host, and the no-data triggers generated from that list have been applied to the `livespec` environment

When that host's otel-collector unit is stopped, so it sends no `system.linux.memory.available` datapoint

Then within two evaluations of its 20-minute window that host's no-data trigger MUST fire to the dev-host recipients, naming the host

And when the unit is started again and datapoints resume, the trigger MUST resolve

And adding a second host to the dev-host list and running the generator MUST add exactly one trigger definition, for that host, and MUST leave every existing definition byte-identical
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the same commit.
