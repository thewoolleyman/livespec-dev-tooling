---
topic: pressure-telemetry-also-export-the
author: claude-opus-5-5
created_at: 2026-11-07T20:05:17Z
---

## Proposal: The pressure emitter also exports a configured cgroup's CPU pressure

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend the pressure emitter from host-level pressure stall information to an optional, per-host list of cgroups. For each configured cgroup it reads that cgroup's `cpu.pressure` and sends `livespec.cgroup.pressure.cpu.*` datapoints carrying a `cgroup` attribute, in the same request as the host datapoints, and `poweredge-xubuntu` configures `system.slice/k3s.service`. A configured cgroup whose file is missing fails the run under the rule that already forbids zeros in place of a missing reading. A host that sets no list is unchanged.

### Motivation

§"Execution-target pressure telemetry" states host-level pressure only, so Honeycomb carries `livespec.host.pressure.*` from `/proc/pressure` and nothing from a cgroup. That leaves a question the fleet needs answered unanswerable after the fact: whether the k3s server was starved of CPU during a node saturation window. livespec-dev-tooling-cetudy (the k3s server's protected CPU share) has a host-captured assertion on exactly that reading, a read of the k3s server cgroup's `cpu.pressure` on `poweredge-xubuntu` during a saturation window. Saturation windows cannot be predicted, and the fleet host guard rightly refuses a looping ssh sampler, so the reading must already be exported when the window happens. A single live read returns a value, so the data exists and is only unexported.

The work is carried by livespec-dev-tooling-3gm5rb, filed 2026-11-06 and routed by the coordinator. Its spec-change-tier judgement reported `partial` against this section: the shared fail-closed, host-stamping and convergence rules cover it, and the per-cgroup export does not appear. No proposal for its linked topic was filed at the time, so the pre-dispatch wall refuses the item with `unratified-topic`. This proposal is that topic.

The agents' cgroup, `system.slice/k3s-agent.service` on `gmktec-xubuntu` and `hp-xubuntu`, is deliberately not required here. The list exists so it can be added later as an inventory change, with no spec or emitter change.

The missing-file rule fails the whole run rather than sending the host datapoints alone, and that costs a gap in the host's pressure telemetry while the cgroup is gone. Measured on `poweredge-xubuntu`: `k3s.service` runs `KillMode=process` and `Restart=always`, so an ordinary k3s restart leaves the container shims in the cgroup and its `cpu.pressure` stays readable. The file goes only when every process in the cgroup goes, which is a full stop with the node out of service, and that host's hostmetrics still arrive through its separate collector. The narrow gap is the accepted cost of keeping the emitter's all-or-nothing request, and the clause states the precedence so the 15-minute rule is not silently contradicted.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Execution-target pressure telemetry", insert this paragraph directly after the paragraph headed "Pressure stall information on every execution target.":

**A configured cgroup's CPU pressure.** The pressure emitter MUST accept a per-host list of cgroup paths relative to `/sys/fs/cgroup`, supplied by this repository's Ansible tree and empty by default. A host that sets no list MUST emit only its host pressure datapoints. For each configured cgroup the emitter MUST read that cgroup's `cpu.pressure` file and send the metrics `livespec.cgroup.pressure.cpu.{some,full}.{avg10,avg60,avg300}`. Each of those datapoints MUST carry a `cgroup` attribute equal to the configured path and `host.name` equal to the host's own name, and MUST be sent in the same request as that host's pressure datapoints. A configured cgroup whose `cpu.pressure` file is missing MUST make the emitter exit non-zero with a log line naming the missing file, and the emitter MUST NOT send any datapoint in that run, because a zero reading would be read as an idle cgroup and a partial request could look like a complete sampling pass. This failure takes precedence over the 15-minute coverage rule above: a host whose configured cgroup has gone reports no pressure datapoints until the cgroup returns or the list changes, and the failed emitter unit is the signal. `poweredge-xubuntu` MUST configure `system.slice/k3s.service`, so that the k3s server's CPU pressure during a node saturation window can be read from Honeycomb after the window.

In `SPECIFICATION/scenarios.md`, insert these three scenarios directly after `## Scenario: a host with no pressure file makes the emitter fail rather than report zero`:

## Scenario: a configured cgroup's CPU pressure is queryable in livespec by cgroup and host

Given the pressure emitter is converged on `poweredge-xubuntu` with `system.slice/k3s.service` configured

When 15 minutes pass with the host running

Then the `livespec` environment's metrics dataset MUST hold the metrics `livespec.cgroup.pressure.cpu.{some,full}.{avg10,avg60,avg300}` stamped `cgroup` = `system.slice/k3s.service` and `host.name` = `poweredge-xubuntu` within that window

## Scenario: a configured cgroup with no pressure file makes the emitter fail rather than report zero

Given a host configured with a cgroup whose `cpu.pressure` file does not exist

When the pressure emitter runs

Then the emitter MUST exit non-zero with a log line naming that `cpu.pressure` file

And no datapoint MUST be sent for that host in that run

## Scenario: a host with no configured cgroup emits only host pressure

Given a host whose pressure telemetry configuration sets no cgroup list

When the pressure emitter runs

Then the request it sends MUST hold that host's pressure datapoints

And the request MUST NOT hold any `livespec.cgroup.pressure.cpu.*` datapoint

The co-edit for these three headings belongs to the revise commit, not to this file: `tests/heading-coverage.json` gains one row for each, naming livespec-dev-tooling-3gm5rb as the owning work item, and `tests/heading-coverage-debt.json` is regenerated.
