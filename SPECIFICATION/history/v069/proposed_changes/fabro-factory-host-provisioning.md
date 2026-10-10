---
topic: fabro-factory-host-provisioning
author: claude-opus-5-5
created_at: 2026-10-10T23:36:21Z
---

## Proposal: Fabro factory host provisioning

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a non-functional-requirements H2, "Fabro factory host provisioning", that governs ansible/fabro-hosts.yml and the roles it includes for the fleet's Fabro factory hosts: one play per host applied from the control node after a drift read, one fabro_server instance per host_vars mapping with optional per-instance binary and home axes that default to today's rendering, and a sandbox-container resource envelope whose daemon-restart-requiring settings are never applied by a converge. Add two scenarios that exercise the instance axes and the drained-restart rule.

### Motivation

The ansible/fabro-hosts.yml play and its fabro_server role exist and are applied to hp-xubuntu and vps, but no H2 of this repository's SPECIFICATION/ tree governs them; the only Ansible heading, "Runner-pool node rebuild recipe", governs the CI pool through ansible/ci-pool.yml. Two execution mirrors filed by livespec-orchestrator-beads-fabro plan fabro-currency (livespec-dev-tooling-finosf: per-instance Fabro binary and home for the hp candidate instance; livespec-dev-tooling-ig5iwg: Fabro sandbox containers bounded inside one systemd slice) were refused by the factory's Definition-of-Done gate on 2026-10-10 because their References line could name no governing heading. The fabro-currency cutover to the Petri-era Fabro build must land by 2026-11-07, and both items are on its path.

### Proposed Changes

Append to SPECIFICATION/non-functional-requirements.md, after "## Runner-pool node rebuild recipe":

## Fabro factory host provisioning

**Scope.** This section states this repository's obligation as the repository that provisions the fleet's Fabro factory hosts: the hosts that run a Fabro server and the sandbox containers its runs execute in. The play is `ansible/fabro-hosts.yml`; per-host values live in `ansible/inventory/host_vars/<host>.yml` and are documented in the inventory's `HOST_VARS.md`.

**One play, applied after a drift read.** Every service a Fabro factory host runs MUST be installed by a role that `ansible/fabro-hosts.yml` includes for that host, with every host-specific value read from that host's host_vars and never embedded in the role. A change to a factory host MUST be applied from the control node by `just ansible-apply ansible/fabro-hosts.yml`, and `just ansible-drift ansible/fabro-hosts.yml` MUST be run and read before that apply. A service installed on a factory host by hand MUST be treated as drift to be expressed in the play, never as an accepted exception.

**One instance per mapping.** Each Fabro server instance on a host MUST be exactly one mapping in that host's `fabro_server_instances`, and the `fabro_server` role MUST install exactly one instance per invocation. The role MUST refuse, before changing anything on the host, an instance list in which two instances share a `unit_name`, a `home_dir` or a `port`. An instance MAY name its own Fabro binary (`binary_path`) and its own `HOME` (`home_env`). When an instance omits either axis, the role MUST render that instance's unit exactly as it renders it without the axis existing, so that adding an optional axis never changes an instance that does not use it.

**Sandbox resource envelope.** A factory host MAY bound its Fabro sandbox containers inside one systemd slice by setting the Docker daemon's default `cgroup-parent`, with the slice's limits read from role variables. A role that edits `/etc/docker/daemon.json` MUST preserve every key it does not own. A converge MUST NOT restart `dockerd`: a setting that takes effect only on a daemon restart MUST be recorded as pending and applied only by an operator-selected restart, performed inside a window in which the host's Fabro servers carry no active runs.

**Documented beside the values.** `HOST_VARS.md` MUST document every variable these roles read, with its default. An interim control MUST also carry its operator procedure, its rollback and the condition under which it is retired.

Append to SPECIFICATION/scenarios.md:

## Scenario: a Fabro instance that names its own binary and home renders a unit that runs them

Given a factory host's `fabro_server_instances` holds one instance that omits `binary_path` and `home_env` and one instance that sets both

When the `fabro_server` role renders each instance's unit

Then the instance that omits both axes MUST render a unit byte-identical to the unit the role rendered before the axes existed

And the instance that sets both MUST render a unit whose `ExecStart` runs that binary and whose `Environment=HOME` is that home

And the role's uniqueness preflight MUST accept the list while no `unit_name`, `home_dir` or `port` repeats, and MUST refuse it naming the repeated value when one does

## Scenario: converging the Fabro sandbox envelope never restarts dockerd outside a drained window

Given a factory host whose `/etc/docker/daemon.json` already holds keys the sandbox-envelope role does not own

When the role is converged without the operator's drained-restart selection

Then the systemd slice MUST carry the memory and CPU limits named by the role variables

And `daemon.json` MUST carry `cgroup-parent` naming that slice and every key it held before

And `dockerd` MUST NOT have been restarted, and the pending restart MUST be recorded

The revise that accepts this proposal MUST add `tests/heading-coverage.json` entries for the new H2 and both scenarios. Each MAY be a `TODO` entry whose reason names the owed test and the work-item that owes it (livespec-dev-tooling-finosf for the instance axes and the first scenario, livespec-dev-tooling-ig5iwg for the envelope and the second scenario), with the matching debt-register entry.
