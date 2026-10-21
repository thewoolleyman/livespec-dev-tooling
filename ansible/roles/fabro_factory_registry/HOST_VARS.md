# `fabro_factory_registry` — the inventory values this role reads

| Variable | Default | Meaning |
| --- | --- | --- |
| `fabro_factory_registry` | `{}` | Which Fabro server instance answers to each logical factory name. A mapping from the factory name to an object carrying `host`, `unit_name` and optionally `docker_host`. |
| `fabro_factory_registry_dest` | `/etc/livespec/fabro-factories.json` | The absolute path this role renders the registry to. The directory it names is created too. |

`fabro_factory_registry` is declared ONCE, and only in
`ansible/inventory/group_vars/dev_hosts.yml` — not in
host_vars. The registry is not a per-host value: one factory name resolves to one
instance on one machine, and every dispatching host must publish the same answer.
Each entry's keys are:

| Key | Required | Meaning |
| --- | --- | --- |
| `host` | yes | The inventory name of the host that serves this factory. |
| `unit_name` | yes | The `unit_name` of one mapping in that host's `fabro_server_instances`. That instance's `canonical_host` becomes the published address. |
| `docker_host` | no | The container daemon's address, spelled exactly as the Docker CLI spells `DOCKER_HOST`. Rendered only when declared. |

The role renders `fabro_factory_registry_dest` on every host of the group the play
runs it on, as a JSON object holding one entry per factory name whose `server` is
`https://` followed by the named instance's `canonical_host`, and which carries
`docker_host` exactly when the mapping declares it. The default `{}` renders the
empty object rather than skipping the file, so a Dispatcher never reads a registry
an earlier converge left behind.

`fabro_factory_registry_dest` defaults to `/etc/livespec/fabro-factories.json`,
the path the Dispatcher reads
(`SPECIFICATION/non-functional-requirements.md` §"Fabro factory registry"), and
no inventory declares it: a converge publishes the default. It is a variable so
that the role's own tests can run the committed tasks without converging the
machine pytest runs on. `--check` is not enough on its own — a `--check --diff`
run still READS the destination, so an install diff taken against the real path
reports against whatever that host holds, and the suite's verdict depended on
whether the file was there. It silently was: the control node acquired it in
v1.118.0's apply on 2026-10-18 and every pre-push from it failed from 19:43Z,
while master CI and every factory sandbox stayed green
(work-item `livespec-dev-tooling-7qfnh6`).

## Why it exists

A repository's `dispatcher.factories` entry may declare `"registry": true` and
carry no address (livespec-orchestrator-beads-fabro `contracts.md` §"Factory
addresses resolved from a host registry"); the Dispatcher then resolves that
factory's address by name from this file. The maintainer ruled on 2026-10-15
(plan `petri-factory-on-gmktec`, epic `bd-ib-fyozyd`) that a factory is bound to
a machine only in the gitops inventory, because the factory moves between
machines now and onto Kubernetes later. Fifteen fleet repositories commit factory
tables whose `server` values name a machine today; this file is what lets them
stop.

## Refused before writing

A run that reaches the rendering validates every entry FIRST, and refuses the
play — on every host, before any host's file is touched — naming the factory and
the reason, when an entry

- has a name that is not a string non-empty once surrounding whitespace is removed,
- names a `host` the inventory does not declare,
- names a `unit_name` that matches no mapping in that host's `fabro_server_instances`,
- matches an instance whose `canonical_host` is not non-empty once surrounding
  whitespace is removed, or
- declares a `docker_host` that is not a string non-empty once surrounding
  whitespace is removed.

Those are the same emptiness rules the Dispatcher applies when it reads the file,
so a registry this role writes is one the Dispatcher accepts.

## Moving a factory

Re-point the entry's `host` and `unit_name` and converge. Nothing else changes:
no play, no role and no committed factory entry names the machine. A factory name
SHOULD name the instance it addresses and SHOULD stay the same for that
instance's whole life — which repository dispatches there by default is carried
by `dispatcher.default_factory` alone, so a cutover renames nothing.

## Declared today

```yaml
fabro_factory_registry:
  legacy:
    host: <the inventory host of the 0.254 instance>
    unit_name: fabro-server
  petri:
    host: <the inventory host of the current Fabro server>
    unit_name: fabro-server
  mi-homelab:
    host: <the inventory host of the mi-homelab organisation's instance>
    unit_name: fabro-server-mi-homelab
```

`mi-homelab` is the one entry whose `unit_name` is not `fabro-server`, and that
is the whole of it: its instance shares a machine with the instance `legacy`
names, so the unit is the only key that tells the two apart. An entry naming
`fabro-server` there would resolve to a valid address — the fleet instance's —
and route that organisation's dispatches onto the fleet factory with nothing
failing. Whether the instance is running is not the registry's business: it
publishes where a factory IS.

No entry declares a `docker_host`: no repository's committed factory table
declares one today (measured 2026-10-18 across the fleet's `.livespec.jsonc`
files), and publishing one would newly turn on the Dispatcher's remote container
sweep. Add one deliberately, with the reason beside it, not by transcription.
