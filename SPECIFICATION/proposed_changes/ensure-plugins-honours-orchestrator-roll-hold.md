---
topic: ensure-plugins-honours-orchestrator-roll-hold
author: claude-opus-5-5
created_at: 2026-11-06T15:54:02Z
---

## Proposal: ensure-plugins honours an orchestrator roll hold, so a session start cannot adopt an unproven orchestrator build

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a committed orchestrator roll-hold record that livespec-dev-tooling's master serves at fleet/orchestrator-roll-hold.json. While a hold is unreleased, every fleet member's ensure-plugins (the recipe each clone's SessionStart hook runs) keeps that member's installed orchestrator build instead of adopting the held build or any later one, and prints the unmet release conditions. A member is never downgraded, the orchestrator repository's own clone is exempt so canary and proof-matrix runs can launch, and an unreadable record fails closed. ensure-plugins-fleet reports a divergence that the hold explains as HELD instead of failing build convergence. A governing scenario is added.

### Motivation

The fleet's orchestrator roll gate (proof matrix plus named canaries, adopted by the maintainer on 2026-11-05 and recorded on livespec-dev-tooling-sv6m5p) was enforced only by an operator choosing when to run the install routes. Every fleet clone's committed SessionStart hook runs `just ensure-plugins`, and livespec_dev_tooling/fleet/ensure_plugins.py installs the newest marketplace build with no hold. On 2026-11-06, orchestrator v0.293.1 reached livespec-orchestrator-beads-fabro (06:07Z), livespec-dev-tooling (06:13Z), hetzner-xubuntu-info (06:17Z) and homelab (06:23Z) with no operator roll, and v0.294.1 reached livespec-dev-tooling at 11:53Z, while those builds were described as held. A gate that binds only launch-time dispatch, while every clone adopts the newest tag at session start, is incoherent. The maintainer ruled on 2026-11-06 at about 16:0xZ, relayed by legacy-coordinator-agent: "7. Yes, I assume so? Seems to make sense, do it if you agree", and the coordinator agreed. livespec-dev-tooling-7upzav (plan gmktec-factory-placement, epic livespec-dev-tooling-me5aqz) carries the implementation. The build-convergence rule in this section today makes ensure-plugins-fleet fail on exactly the split a hold creates, so the contract must change before that item is built.

### Proposed Changes

In `contracts.md` §"Fleet-wide plugin adoption", the following MUST be added. A member's `ensure-plugins` recipe is the reconcile that every fleet clone's SessionStart hook runs, so these rules bind session-start installs as well as `just ensure-plugins-fleet`.

Add a new bullet list item after **Success.**:

- **Orchestrator roll hold.** livespec-dev-tooling's master branch MAY carry one committed roll-hold record at `fleet/orchestrator-roll-hold.json`. Each member's `ensure-plugins` MUST fetch it from livespec-dev-tooling master at run time, the way §"Sibling discovery" fetches the fleet manifest. The record is a JSON object with exactly these keys:
  - `plugin`: the held plugin's install key, `livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro`.
  - `held_from_version`: a semver string.
  - `implement_graph_blob`: the git blob id of `implement-work-item/workflow.fabro` in the held build.
  - `canaries`: an array of objects, each carrying `item`, `criteria` and `verdict`. `verdict` is one of `pending`, `passed` or `failed`.
  - `matrix`: an object with the keys `fresh`, `seeded` and `non_orchestrator`. Each value is a passing factory run id, or `null`.
  - `recorded_on`: the ledger id of the plan epic where each condition's evidence is recorded.

  A hold is UNRELEASED while any canary verdict is not `passed` or any `matrix` value is `null`.
- **Held install.** While an unreleased hold names a plugin that a member enables, and the marketplace offers that plugin at a version at or above `held_from_version`, the member's `ensure-plugins` MUST leave that member's installed build of that plugin unchanged. It MUST print one line naming the plugin, the offered build, `held_from_version`, and each unmet release condition. It MUST still reconcile every other enabled plugin, and it MUST exit 0 for the held plugin.
- **No downgrade.** When a member already has a build at or above `held_from_version` installed, `ensure-plugins` MUST leave it installed. It MUST NOT downgrade it.
- **Launch-clone exemption.** The member whose repository is the held plugin's own source repository, livespec-orchestrator-beads-fabro, MUST be exempt from the held-install rule, so canary and matrix runs can launch on the held build.
- **Unreadable hold.** When the roll-hold record exists but cannot be fetched or does not parse against the shape above, `ensure-plugins` MUST leave the held plugin's installed build unchanged, MUST print one line naming the read failure, and MUST reconcile every other plugin. An ABSENT record, which the fetch distinguishes from an unreadable one, MUST leave behaviour exactly as it is without a hold.
- **Released hold.** When every canary verdict is `passed` and every `matrix` value names a run, `ensure-plugins` MUST install the offered build exactly as it does when no hold exists.

Amend **Build convergence.** and **Success.** as follows:

- `just ensure-plugins-fleet` MUST NOT exit non-zero on a build divergence that an unreleased hold fully explains. A divergence is fully explained when the only members on a build at or above `held_from_version` are the launch-clone exemption and members that already had that build before the run, and every other member enabling the plugin is on one build below it.
- For a divergence explained that way, the recipe MUST print one `HELD` line naming the plugin, `held_from_version`, and the members on each side.
- Any other divergence MUST still exit non-zero as today.

In `scenarios.md`, a new scenario MUST be added directly after "## Scenario: one fleet-wide command adopts the current plugin builds in every fleet member and refuses a split adoption":

```gherkin
## Scenario: a fleet clone's ensure-plugins keeps its orchestrator build while an orchestrator roll hold is unreleased

Given livespec-dev-tooling master carries `fleet/orchestrator-roll-hold.json` naming the orchestrator plugin with `held_from_version` 0.295.2, one canary whose verdict is `pending`, and a `matrix` whose `seeded` value is `null`
And a fleet member other than livespec-orchestrator-beads-fabro has orchestrator build 0.295.1 installed while the marketplace offers 0.295.2

When that member's `just ensure-plugins` runs, as its SessionStart hook runs it

Then the member's `installed_plugins.json` orchestrator record MUST still name the 0.295.1 build
And the recipe MUST print one line naming the plugin, the offered 0.295.2 build, `held_from_version` 0.295.2, the pending canary and the missing seeded run
And the recipe MUST still reconcile every other enabled plugin and MUST exit 0

And when the same recipe runs in livespec-orchestrator-beads-fabro's clone, it MUST install the offered 0.295.2 build

And when the record's canary verdict is `passed` and every `matrix` value names a run, the member's recipe MUST install the offered 0.295.2 build

And when the record cannot be fetched, the member's orchestrator build MUST stay unchanged and the recipe MUST print one line naming the read failure

And when `just ensure-plugins-fleet` then runs while the hold is unreleased, it MUST print one `HELD` line naming the plugin, `held_from_version` and the members on each side, and MUST NOT exit non-zero for that divergence
```

A `tests/heading-coverage.json` entry for the new `## Scenario` heading MUST be co-edited in the revise commit. It is a `"test": "TODO"` row naming the integration tier and livespec-dev-tooling-7upzav as the owner of the owed test, registered in `tests/heading-coverage-debt.json`.

