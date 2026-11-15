---
topic: an-orchestrator-roll-moves-only-the-orchestrator
author: claude:gmktec-factory-placement
created_at: 2026-11-13T04:06:12Z
spec_commitments:
  impl_followups:
    - id_hint: split-orchestrator-roll-from-fleet-refresh
      description: |
        Change livespec_dev_tooling.fleet.ensure_plugins_fleet so `just ensure-plugins-fleet <build>` takes only the orchestrator adopt step in each member that enables the orchestrator plugin, and runs no member `ensure-plugins` recipe; print and converge the orchestrator plugin only. Add the `just refresh-plugins-fleet` recipe, which runs each member's own `ensure-plugins` under the host-wide adoption lock, prints before and after builds for every enabled plugin, isolates failures, and converges every enabled plugin other than the orchestrator. Add both recipes to the single-adoption-path scan.
---

## Proposal: An orchestrator roll moves only the orchestrator plugin, and a separate fleet refresh moves every other plugin

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

`just ensure-plugins-fleet <build>` is the orchestrator roll, and today it also runs every member's own `ensure-plugins`, so a roll moves every other enabled plugin to whatever its release names. This proposal makes the roll move only the orchestrator plugin, and moves the all-plugin refresh to a separate operator recipe, `just refresh-plugins-fleet`, which runs each member's `ensure-plugins` and leaves the orchestrator build where the session reconcile holds it.

### Motivation

On 2026-11-13 the v0.325.0 orchestrator roll (the fix for the fix_commit_settle RoutingBlocked regression, rolled by gmktec-factory-placement under plan livespec-dev-tooling-me5aqz) ran `just ensure-plugins-fleet f8a1626e74b3c944f1f6b429f0c98588c9b54a08`. That moved the orchestrator plugin in 10 clones as intended. It also moved livespec-overseer@livespec-overseer in every clone it touched, from 696d1e9c332919329157f1781c2656a1169c4946 (65dce2d876744df3b17f508e9e7c60db5dec31b0 in two clones) to e055ce87d7647aba09bbac2f80c5f4ffc2195d12. The move was the ratified behaviour: §"Fleet-wide plugin adoption" says the recipe "adopts the current plugin builds in every fleet member at once" and runs each member's own `ensure-plugins` before the adopt step, and §"Orchestrator build adoption" → **Canaries and rolls.** releases every roll through it. The result was harmless, because overseer moved to the build its own release names. But an orchestrator roll is a judged, canaried change to one plugin, and today it carries unjudged moves of every other plugin with it. That makes a roll's blast radius depend on what other releases happened to land. A roll-time incident would then have more than one suspect, and the rollback, which names only the orchestrator build, would not reverse the other moves. legacy-coordinator-agent ruled on 2026-11-13 that this is a design point, not a defect, and directed this propose-change under me5aqz, at low urgency, at the end of the dev-tooling revise queue. Splitting the two keeps the fleet-wide no-split guarantee for every plugin, because the refresh converges the other plugins and the roll converges the orchestrator, and it leaves the roll touching exactly what its canary judged. In-flight survey: the-fleet-install-recipes-refuse (carrier livespec-dev-tooling-faetyh) amends **Named build.** of the same recipe to refuse a build `release` does not name. It is compatible with this proposal (align): it changes which build the roll accepts, and this proposal changes which plugins the roll moves. ensure-plugins-fleet-adopts-factory-dispatching-projects widens which clones the recipe adopts in. It is also compatible (align), and its widening applies to the orchestrator adopt step this proposal keeps. a-new-orchestrator-release-s and every-sessionstart-plugin-reconcile-on govern the canary and the session reconcile, and this proposal does not change either.

### Proposed Changes

Amend `contracts.md` §"Cross-repo coordination automation surface" → "### Fleet-wide plugin adoption" as follows.

1. Replace the opening paragraph's second sentence, "It adopts the current plugin builds in every fleet member at once, so that no released plugin build is adopted by only some members.", with:

"It is the *orchestrator roll*: it adopts one orchestrator build in every fleet member that enables the orchestrator plugin, at once, so that no orchestrator build is adopted by only some members, and it moves no other plugin. A second operator-invoked recipe, `just refresh-plugins-fleet`, adopts the current builds of every other enabled plugin in every fleet member at once, so that no other released plugin build is adopted by only some members; **Fleet plugin refresh.** below governs it."

2. Replace the **Per-member adoption.** bullet with:

"- **Per-member adoption.** For each member whose committed `.claude/settings.json` enables the orchestrator plugin, the recipe MUST take the adopt step below for that member, with the recipe's own `<build>` argument. It MUST NOT run the member's `ensure-plugins` recipe, and it MUST NOT run any install or update command for any plugin other than the orchestrator plugin."

3. In **Before and after builds.**, replace "For every member and every plugin that member's committed `.claude/settings.json` enables, the recipe MUST print the installed build before the member's `ensure-plugins` run and after the member's last adoption command." with "For every member whose committed `.claude/settings.json` enables the orchestrator plugin, the recipe MUST print that plugin's installed build before and after the member's adopt step."

4. In **Failure isolation.**, replace "or its `ensure-plugins` recipe or adopt step exits non-zero" with "or its adopt step exits non-zero".

5. In **Build convergence.**, replace "when one enabled plugin is installed at different builds across the members' project scopes, the recipe MUST exit non-zero. It MUST name that plugin, each build and the members holding it, even when every member's `ensure-plugins` succeeded." with "when the orchestrator plugin is installed at different builds across the project scopes of the members that enable it, the recipe MUST exit non-zero. It MUST name each build and the members holding it, even when every member's adopt step succeeded."

6. Replace the **Success.** bullet with "- **Success.** The recipe MUST exit 0 only when every member's adopt step succeeded and the orchestrator plugin is installed at a single build across the members that enable it."

7. Append this bullet after **Adopters enabling the orchestrator plugin.**:

"- **Fleet plugin refresh.** This repository's justfile MUST ship an operator-invoked recipe, `just refresh-plugins-fleet`, taking no argument. It MUST take its member set as **Membership.** states. For each member, it MUST run that member's OWN `ensure-plugins` recipe in that member's local clone, with the clone as the working directory, and it MUST NOT reimplement a member's plugin reconcile. It MUST NOT take the adopt step, so a member's orchestrator build moves only as **Session reconcile.** allows. For every member and every plugin that member's committed `.claude/settings.json` enables, it MUST print the installed build before and after the member's `ensure-plugins` run, read as **Before and after builds.** reads it. When a member's clone is missing or its `ensure-plugins` recipe exits non-zero, it MUST still run every remaining member, MUST name each failed member with its cause, and MUST exit non-zero. After every member has run, when one enabled plugin other than the orchestrator plugin is installed at different builds across the members' project scopes, it MUST exit non-zero, naming that plugin, each build and the members holding it. It MUST exit 0 only when every member's `ensure-plugins` succeeded and every enabled plugin other than the orchestrator plugin is installed at a single build across the members that enable it."

Amend "#### Orchestrator build adoption" as follows.

8. In **Adoption lock.**, replace "A tag adopt, a full-commit adopt step run on its own, and `just ensure-plugins-fleet` MUST each hold one host-wide adoption lock" with "A tag adopt, a full-commit adopt step run on its own, `just ensure-plugins-fleet` and `just refresh-plugins-fleet` MUST each hold one host-wide adoption lock".

9. In **Canaries and rolls.**, after "releases the roll by running `just ensure-plugins-fleet <build>`.", insert "The roll moves only the orchestrator plugin; an operator who means to bring the fleet's other plugins to their current builds runs `just refresh-plugins-fleet` as its own step, and records it where the roll is tracked when it is taken during a roll."

10. In **Single adoption path.**, replace "only that member's `ensure-plugins` recipe, this adopt step and `just ensure-plugins-fleet` MAY adopt a plugin build at project scope" with "only that member's `ensure-plugins` recipe, this adopt step, `just ensure-plugins-fleet` and `just refresh-plugins-fleet` MAY adopt a plugin build at project scope".

Amend `scenarios.md` as follows.

11. In "## Scenario: one fleet-wide command adopts the current plugin builds in every fleet member and refuses a split adoption", keep the heading and replace the scenario body's first Then and its livespec-core convergence And with:

"Then the recipe MUST take the adopt step with commit X in each member whose settings enable the orchestrator plugin, MUST NOT run any member's own `ensure-plugins` recipe, and MUST print, for every such member, the orchestrator plugin's installed build before and after, read from `installed_plugins.json` for that member's project path

And every member's livespec core plugin install record MUST name the same build after the run as before it

And when every member's adopt step succeeds but the orchestrator plugin is left installed at two different builds across the members, the recipe MUST exit non-zero, naming both builds and the members holding each"

keeping every other And line of that scenario unchanged.

12. Add this scenario directly after it:

"## Scenario: the fleet plugin refresh brings every plugin but the orchestrator to its current build in every fleet member

Given livespec core's fleet manifest lists the members whose local clones are on this host, and each member's committed `.claude/settings.json` enables the orchestrator plugin and the livespec core plugin

And each member has orchestrator build 0.299.0 installed while the marketplace offers 0.300.0, and the livespec core plugin's release names a build newer than every member's installed one

When the operator runs `just refresh-plugins-fleet` in livespec-dev-tooling

Then the recipe MUST run each member's own `ensure-plugins` recipe in that member's clone, MUST NOT take the adopt step, and MUST print, for every member and every enabled plugin, the installed build before and after

And every member's livespec core plugin install record MUST name the build its release names

And every member's orchestrator plugin install record MUST still name 0.299.0

And when one member's clone is missing or its `ensure-plugins` exits non-zero, the recipe MUST still run every other member, MUST name that member and its cause, and MUST exit non-zero

And when every member's `ensure-plugins` succeeds but the livespec core plugin is left installed at two different builds across the members, the recipe MUST exit non-zero, naming the plugin, both builds and the members holding each"

13. In "## Scenario: a fleet clone's ensure-plugins keeps its orchestrator build while an orchestrator roll hold is unreleased", in the scan line, replace "outside `ensure-plugins`, `just adopt-orchestrator-build` and `just ensure-plugins-fleet`" with "outside `ensure-plugins`, `just adopt-orchestrator-build`, `just ensure-plugins-fleet` and `just refresh-plugins-fleet`".

Item 12 adds one `## ` heading, so the revise that accepts this proposal MUST add its row to `tests/heading-coverage.json` and regenerate the debt register in the same commit.
