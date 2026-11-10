---
topic: ensure-plugins-fleet-adopts-factory-dispatching-projects
author: claude-opus-5-5
created_at: 2026-11-10T13:19:18Z
---

## Proposal: ensure-plugins-fleet takes the adopt step in every host clone whose committed .livespec.jsonc configures a dispatcher factory

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend contracts.md §"Fleet-wide plugin adoption" so that `just ensure-plugins-fleet <build>` also takes the adopt step, with its own `<build>`, in every clone under the clones root whose committed `.livespec.jsonc` configures an orchestrator dispatcher factory (the orchestrator plugin's `dispatcher.default_factory`). This includes manifest adopters and clones that are not in the manifest at all. The set is derived from that committed config, never from a hand-kept list. Such a project keeps the recipe's before/after build lines, its failure isolation and its exit-code rules, but it is not a member for the member-only rules (its own `ensure-plugins` run and Build convergence). The report-only rule for adopters narrows to adopters that configure no dispatcher factory. The scenario 'one fleet-wide command adopts the current plugin builds in every fleet member and refuses a split adoption' changes to match. The per-clone `just adopt-orchestrator-build <clone> <build>` is unchanged: it already accepts a manifest adopter or an absolute checkout path.

### Motivation

A project's installed orchestrator build IS its factory dispatch build: the host dispatcher resolves its launch build from that project's project-scope install (contracts.md §"Orchestrator build adoption"; livespec-dev-tooling .ai/factory-span-receiver.md). The fleet command adopts only manifest members, and the bullet 'Adopters enabling the orchestrator plugin' forbids it to adopt a manifest adopter. So every orchestrator roll strands every project that dispatches to the factory without being a member. That clause governs only the fleet command. The per-clone adopt step is the route that reaches these projects, and today it has to be taken by hand, one project at a time.

Measured on the 2026-11-10 orchestrator v0.312.3 roll (f0b6f8909cc4de6e6fd2aeeb8827c47291ec8c11; `just ensure-plugins-fleet` ran 13:03:50Z-13:08:59Z). All 11 manifest members read f0b6f8909cc4 afterwards. The adopters homelab and hetzner-xubuntu-info, both of which dispatch to the petri factory, stayed on 10d604e3, so their runs kept losing to defects the roll had fixed. legacy-coordinator-agent ruled them in, and they were hand-adopted with `just adopt-orchestrator-build` at 13:11:36Z and 13:11:46Z. dolt-server (9ff450ec), resume (376981a9), openbrain (4bc8237f) and livespec-tdd-proof (9ff450ec) were then hand-adopted to f0b6f8909cc4 by the gmktec-factory-placement seat between 13:13:59Z and 13:14:30Z. All six hand adoptions are an INTERIM measure, taken while this proposal ratifies.

Which projects the derivation picks up today: on this host, livespec, dolt-server, resume, openbrain, livespec-tdd-proof, homelab and hetzner-xubuntu-info all configure `dispatcher.default_factory: "petri"` in their committed `.livespec.jsonc` (livespec is already a member). Dispatch evidence from each project's `tmp/fabro-dispatch-journal.jsonl` `dispatch-run-stamp` rows, over the 7 days 2026-11-03T13Z-2026-11-10T13Z:
- openbrain: 2 runs (ob-td6fup, 01M6WF7GHVJX at 2026-11-08T02:19:57Z and 01M6WHD1XQ1F at 02:58:04Z).
- homelab: 6 runs (last 2026-11-06T23:29:59Z).
- hetzner-xubuntu-info: 2 runs (last 2026-11-08T01:48:51Z).
- resume: 0 runs, though its launcher made 38 pre-launch CPU reads between 2026-11-08T02:21:52Z and 02:24:30Z, so it attempted to dispatch; its last run stamp is 2026-10-31T22:34:37Z.
- dolt-server: 0 runs (last 2026-11-02T18:04:54Z).
- livespec-tdd-proof: 0 runs (last 2026-10-24T10:26:40Z).
The config-derived rule decides these consistently: a configured factory means the next dispatch will run on the installed build, whether or not one happened in the last week. A hand list or an activity window would rot again at the next roll.

### Proposed Changes

In SPECIFICATION/contracts.md §"Fleet-wide plugin adoption":

1. In the opening paragraph, after "so that no released plugin build is adopted by only some members", add: "or left behind in a project that dispatches to the factory".

2. Add a new bullet after **Membership.**:

- **Factory-dispatching projects.** Besides the members, the recipe MUST take the adopt step below, with its own `<build>` argument, in every *factory-dispatching project*. That is a git checkout directly under `<root>`, not itself a member, whose `.livespec.jsonc` at its committed `HEAD` sets the orchestrator plugin's `dispatcher.default_factory` to a non-empty value and whose committed `.claude/settings.json` enables the orchestrator plugin. The recipe MUST derive this set by reading each candidate's committed config on every run, and MUST NOT carry or read a hand-kept list of such projects. It covers manifest adopters and checkouts the manifest does not name. The recipe MUST NOT run a factory-dispatching project's own `ensure-plugins` recipe. **Before and after builds.**, **Failure isolation.** and **Success.** apply to it as to a member, for the orchestrator plugin only. **Build convergence.** compares members only. A candidate whose committed `.livespec.jsonc` cannot be read or parsed MUST be named, with its cause, in a line that does not affect the exit code, and MUST NOT be adopted.

3. Replace the bullet **Adopters enabling the orchestrator plugin.** with:

- **Adopters enabling the orchestrator plugin.** The recipe MUST NOT adopt a build in a manifest adopter that is not a factory-dispatching project. For each such adopter whose local clone exists and whose committed `.claude/settings.json` enables the orchestrator plugin, it MUST print one line naming the adopter, its installed build and the adopt step's command. These lines MUST NOT affect the exit code. This rule and **Factory-dispatching projects.** govern this recipe only. The per-clone adopt step (`just adopt-orchestrator-build <clone> <build>`) keeps its own `<clone>` rule, which already accepts a manifest adopter or an absolute checkout path.

In SPECIFICATION/scenarios.md, "## Scenario: one fleet-wide command adopts the current plugin builds in every fleet member and refuses a split adoption" (the heading is unchanged):

4. Replace the clause beginning "And for a manifest adopter whose clone exists and whose committed settings enable the orchestrator plugin" with:

And for a manifest adopter whose clone exists, whose committed settings enable the orchestrator plugin and whose committed `.livespec.jsonc` configures no dispatcher factory, the recipe MUST NOT adopt a build there, MUST print one line naming the adopter, its installed build and the adopt step's command, and that line MUST NOT affect the exit code

And for a checkout under the clones root that is not a member, whose committed settings enable the orchestrator plugin and whose committed `.livespec.jsonc` sets the orchestrator plugin's `dispatcher.default_factory`, whether or not it is a manifest adopter, the recipe MUST take the adopt step there with commit X without running that checkout's `ensure-plugins`, MUST print its orchestrator build before and after, and an adopt step that exits non-zero there MUST make the recipe exit non-zero after every other member and project has run

And when such a checkout's committed `.livespec.jsonc` cannot be parsed, the recipe MUST name it and the cause in a line that does not affect the exit code, and MUST NOT adopt a build there
