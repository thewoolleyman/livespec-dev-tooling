---
topic: fabro-factory-registry
author: claude-opus-5-5
created_at: 2026-10-18T15:50:00Z
---

## Proposal: Render the Fabro factory registry on the dispatching hosts from the inventory

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Adds `## Fabro factory registry` to `non-functional-requirements.md`, immediately after §"Fabro factory host provisioning", plus one scenario. The inventory carries one mapping, `fabro_factory_registry` in `ansible/inventory/group_vars/dev_hosts.yml`, from each logical factory name to the inventory host and `fabro_server_instances` unit that serve it, and optionally a container-daemon address. `ansible/fabro-hosts.yml` resolves each name to that instance's HTTPS address and renders `/etc/livespec/fabro-factories.json` on every `dev_hosts` host, refusing an unresolvable mapping before it writes the file. Binding a factory to a machine becomes an inventory change plus a converge, with no committed factory entry, play or role naming the machine.

### Motivation

Plan `petri-factory-on-gmktec` (epic `bd-ib-fyozyd` in the livespec-orchestrator-beads-fabro ledger) carries the maintainer's 2026-10-15 ruling that no playbook, role or committed factory entry may name a machine hostname, and that a factory is bound to a machine only in the gitops inventory. The play-and-role half landed under `livespec-dev-tooling-prdxxe`. The committed-entry half is livespec-orchestrator-beads-fabro's proposal `factory-addresses-from-a-gitops-registry`, ratified in that repository's contracts as §"Factory addresses resolved from a host registry" (its revise lands before this one, so the Scope paragraph below cites a section that exists): a `dispatcher.factories` entry may declare `"registry": true`, and the Dispatcher then resolves its server address, and optionally its `docker_host`, by name from a registry file at `/etc/livespec/fabro-factories.json` that "the fleet's provisioning renders from its inventory". This repository is that provisioning, and nothing in its specification states the rendering, so the role that renders the file has no clause to be graded against. Measured 2026-10-18: every host whose host_vars declare `fabro_server_instances` (hp-xubuntu, gmktec-xubuntu and the retired vps) already gives each instance a `unit_name` and a `canonical_host`, so a name-to-instance mapping is all the inventory lacks.

Revision 2 adopts the independent reviewer's simpler mechanism (Fable, round 1, BLOCKERS): one inventory-level mapping keyed by factory name, which makes names unique by construction and covers an instance on any host, instead of a per-instance `factory_name` scanned across one host group, which excluded the vps instances. It also scopes the refusal to "before writing the registry", qualifies the converge rule for `--limit` and `--tags` runs, adds `docker_host`, and names the work item that owns the scenario's test binding (`livespec-dev-tooling-txadim`).

### Proposed Changes

Insert the following section into `non-functional-requirements.md` immediately before the line `## Docker engine install guard`, so that it follows §"Fabro factory host provisioning":

```markdown
## Fabro factory registry

**Scope.** This section states how this repository publishes, on each host
where the Dispatcher runs natively, which Fabro server instance answers to each
logical factory name. The Dispatcher reads that publication to resolve a
factory entry that declares `"registry": true` (livespec-orchestrator-beads-fabro
`contracts.md` §"Factory addresses resolved from a host registry"). A
Dispatcher running inside a factory sandbox or a cluster gate Job reads no such
file, and the file is not rendered there.

**Declared once, in the inventory.** The inventory MAY declare
`fabro_factory_registry`, and when it does it MUST declare it only in
`ansible/inventory/group_vars/dev_hosts.yml`: a
mapping from each logical factory name to an object carrying `host`, the
inventory name of the host that serves it, `unit_name`, the `unit_name` of one
mapping in that host's `fabro_server_instances`, and optionally `docker_host`, a
string spelled as the Docker CLI's `DOCKER_HOST`. A factory name SHOULD name the
Fabro server instance it addresses and SHOULD stay the same for that instance's
whole life.

**Rendered on the dispatching hosts.** On every host in the `dev_hosts` group,
`ansible/fabro-hosts.yml` MUST render `/etc/livespec/fabro-factories.json` as a
JSON object holding exactly one entry per `fabro_factory_registry` name: an
object whose `server` is `https://` followed by the named instance's
`canonical_host`, and which carries `docker_host` exactly when the mapping
declares it. When the inventory declares no `fabro_factory_registry`, the file
MUST hold the empty object. The file MUST be owned by root and MUST be
world-readable. A converge that runs the rendering on a host MUST leave that
host's file holding exactly the derived content, removing any entry the
inventory no longer declares. A run narrowed by `--limit` or `--tags` so that
it does not run the rendering on a host MUST leave that host's file
unchanged.

**Refused before writing.** Every run that runs the rendering on any host MUST
first validate every `fabro_factory_registry` entry, and MUST refuse, before it
writes the registry on any host, an entry whose name is not a string non-empty
after surrounding whitespace is removed, whose `host` is not an inventory host,
whose `unit_name` matches no mapping in that host's `fabro_server_instances`,
whose matched instance has no `canonical_host` non-empty after surrounding
whitespace is removed, or whose `docker_host` is present but is not a string
non-empty after surrounding whitespace is removed, naming the factory and the
reason. These are the same emptiness rules the Dispatcher applies when it reads
the file.

**Machines are bound only in the inventory.** Moving a factory name from one
instance to another MUST be a change to `fabro_factory_registry` or to host_vars
followed by this converge; no play, role or committed factory entry names the
machine.
```

## Proposal: Scenario: the fabro-hosts play renders the factory registry from the inventory's factory names

### Target specification files

- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

States the observable rendering, re-binding, narrowed-run and refusal behaviour of §"Fabro factory registry" as one scenario. The revise that accepts it MUST add `tests/heading-coverage.json` entries for both new headings with `test` "TODO" owned by work-item `livespec-dev-tooling-txadim`, which is filed before this revise lands, and regenerate the `tests/heading-coverage-debt.json` register.

### Motivation

Load-bearing behaviour carries a scenario beside its clause, and the role that renders the registry references this scenario in its Definition of Done.

### Proposed Changes

Append the following scenario to `scenarios.md` after the last scenario:

```markdown
## Scenario: the fabro-hosts play renders the factory registry from the inventory's factory names

Given `fabro_factory_registry` maps `legacy` to one host's instance with a `docker_host`, and maps `petri` to another host's instance with no `docker_host`

And a `dev_hosts` host whose `/etc/livespec/fabro-factories.json` holds a stale entry named `retired`

When `ansible/fabro-hosts.yml` converges and runs the rendering on that host

Then that host's `/etc/livespec/fabro-factories.json` MUST map `legacy` and `petri` each to an object whose `server` is `https://` followed by the named instance's `canonical_host`

And `legacy`'s object MUST carry that `docker_host` and `petri`'s object MUST carry none

And the file MUST hold no other entry, so `retired` is gone, and MUST be owned by root and world-readable

Given `fabro_factory_registry` is changed so that `petri` names an instance on a third host

When `ansible/fabro-hosts.yml` converges and runs the rendering on that host

Then `petri`'s `server` MUST be `https://` followed by the third host's instance's `canonical_host`, and the previous address MUST be gone

Given the inventory declares no `fabro_factory_registry`

When `ansible/fabro-hosts.yml` converges and runs the rendering on a `dev_hosts` host

Then that host's `/etc/livespec/fabro-factories.json` MUST hold the empty object

Given a `dev_hosts` host whose `/etc/livespec/fabro-factories.json` holds an entry the inventory no longer declares

When `ansible/fabro-hosts.yml` runs with `--tags` selecting no rendering task

Then that host's file MUST be unchanged

Given a `fabro_factory_registry` entry that is <invalid>

When `ansible/fabro-hosts.yml` converges and runs the rendering on any host

Then the play MUST refuse before writing the registry on any host, naming that factory and the reason

Examples of <invalid>: a name that is whitespace only; a `host` that is not an inventory host; a `unit_name` that matches no instance on its `host`; a matched instance whose `canonical_host` is whitespace only; a `docker_host` that is whitespace only
```
