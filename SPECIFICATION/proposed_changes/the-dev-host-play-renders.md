---
topic: the-dev-host-play-renders
author: claude-opus-5-5
created_at: 2026-11-05T03:22:07Z
---

## Proposal: The dev-host play renders each registered factory's run cap into a one-line fleet-limit file from the instance's own max_concurrent_runs

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Generalize §"Fabro factory registry" so the dev-host play publishes, beside the address registry, each registered factory's run cap. For each `fabro_factory_registry` factory it renders a world-readable one-line file `<factory>.max_concurrent_runs` in a role-variable directory whose default is `/home/ubuntu/.local/state/livespec/fleet-limits`. The value is read through `hostvars` from the same `fabro_server_instances` entry that renders that instance's `settings.toml`, so one committed value drives both renders. A factory whose resolved instance declares no `max_concurrent_runs` is refused before any host writes. The registry JSON keeps exactly `server` and an optional `docker_host`.

### Motivation

The petri fleet's run count is bounded by three duplicate values: the petri Fabro server's `max_concurrent_runs` (the only one that enforces), the fleet launchers' uncommitted `fleet-cap` file, and `FLEET_LAUNCH_GMK_CAP` in livespec-orchestrator-beads-fabro `fleet-launch/config.sh`. On 2026-11-04 they disagreed, 16 against 20. The maintainer directed the fix on epic livespec-dev-tooling-6tgd2z: "why we have three different levers for the same fucking queue ... IF any of this is the case, fix it." legacy-dispatcher-agent owns the launchers. It confirmed it will point both launcher values at this file once the file exists, and chose a file over a server query so that a launcher poll spawns no process and lists nothing from the server. The launchers run on the dev host and the Fabro server runs on gmktec-xubuntu, so the file is rendered on the dev host from the same inventory value, not beside `settings.toml`. It is a separate file, not a new key in `/etc/livespec/fabro-factories.json`, because this section says that file holds exactly `server` and an optional `docker_host`, and the Dispatcher reads it under that rule. Work item livespec-dev-tooling-o5xpdy (execution mirror of bd-ib-rtzhfc under plan bd-ib-nmuyjc) implements this; its dispatch was held on this proposal topic.

### Proposed Changes

1. In `non-functional-requirements.md` §"Fabro factory registry", replace the first sentence of paragraph **Scope.**

"This section states how this repository publishes, on each host where the Dispatcher runs natively, which Fabro server instance answers to each logical factory name."

with

"This section states how this repository publishes, on each host where the Dispatcher runs natively, which Fabro server instance answers to each logical factory name, and, on the same hosts, how many runs that instance admits at once."

The rest of **Scope.** is unchanged.

2. In the same section, insert this new paragraph immediately after paragraph **Rendered on the dispatching hosts.** and before paragraph **Refused before writing.**:

"**Run caps rendered beside the registry.** On every host in the `dev_hosts` group, `ansible/fabro-hosts.yml` MUST render, for each `fabro_factory_registry` name, a file named `<factory>.max_concurrent_runs` that holds exactly one line: the decimal `max_concurrent_runs` of the `fabro_server_instances` mapping that the factory's `host` and `unit_name` resolve to. The files MUST be written to the directory a role variable names, whose default is `/home/ubuntu/.local/state/livespec/fleet-limits`, and each file MUST be world-readable. The play MUST read the value through `hostvars` from the same `fabro_server_instances` entry from which the `fabro_server` role renders that instance's `settings.toml`, so that changing that one committed value changes both renders, and MUST NOT take the number from any other committed file or variable. The run cap is a separate file, not a key of `/etc/livespec/fabro-factories.json`, because that file holds only `server` and an optional `docker_host`. The `--limit` and `--tags` rule for the registry applies to these files in the same way."

3. In paragraph **Refused before writing.**, replace

"whose matched instance has no `canonical_host` non-empty after surrounding whitespace is removed, or whose `docker_host` is present but is not a string non-empty after surrounding whitespace is removed, naming the factory and the reason."

with

"whose matched instance has no `canonical_host` non-empty after surrounding whitespace is removed, whose matched instance declares no `max_concurrent_runs`, or whose `docker_host` is present but is not a string non-empty after surrounding whitespace is removed, naming the factory and the reason. The same validation MUST pass before any run-cap file is written on any host."

The paragraph's last sentence ("These are the same emptiness rules the Dispatcher applies when it reads the file.") is unchanged; it refers to the registry's own fields.

4. In `scenarios.md`, add this scenario immediately after `## Scenario: the fabro-hosts play renders the factory registry from the inventory's factory names`:

```
## Scenario: the fabro-hosts play renders each registered factory's run cap from its instance's max_concurrent_runs

Given `fabro_factory_registry` maps `petri` to an instance on another host whose `fabro_server_instances` entry declares `max_concurrent_runs: 20`

When `ansible/fabro-hosts.yml` converges and runs the rendering on a `dev_hosts` host

Then that host's fleet-limit directory, `/home/ubuntu/.local/state/livespec/fleet-limits` by default, MUST hold a world-readable file `petri.max_concurrent_runs` whose single line is `20`

And that host's `/etc/livespec/fabro-factories.json` entry for `petri` MUST carry no capacity key

Given that instance's `max_concurrent_runs` is changed to `16` and nothing else is changed

When `ansible/fabro-hosts.yml` converges and runs the rendering on that `dev_hosts` host

Then `petri.max_concurrent_runs` MUST hold the single line `16`

And that instance's rendered `settings.toml` MUST carry `max_concurrent_runs = 16`

Given a `fabro_factory_registry` entry whose resolved instance declares no `max_concurrent_runs`

When `ansible/fabro-hosts.yml` converges and runs the rendering on any host

Then the play MUST refuse before writing the registry or any run-cap file on any host, naming that factory
```
