---
topic: one-fleet-wide-command-adopts
author: claude:gmktec-factory-placement
created_at: 2026-11-03T09:14:10Z
---

## Proposal: One fleet-wide command adopts the current plugin builds in every fleet member

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a `### Fleet-wide plugin adoption` subsection to contracts.md §"Cross-repo coordination automation surface" and a matching scenario to scenarios.md. Together they specify `just ensure-plugins-fleet` in livespec-dev-tooling. The recipe runs every fleet manifest member's own `ensure-plugins` recipe in that member's local clone. It prints each enabled plugin's installed build before and after for every member, keeps going past a failed member, and fails when the members end on different builds of one plugin. An orchestrator release can therefore no longer be adopted partially.

### Motivation

Work item livespec-dev-tooling-jzwgjw (plan gmktec-factory-placement, epic livespec-dev-tooling-me5aqz; ruled by legacy-coordinator-agent 2026-11-03 ~02:55Z). Its factory dispatch was refused as spec-change tier, held for this topic, because no clause states the behaviour and the spec-stated judgement named this section to generalize. On 2026-11-02/03 a released orchestrator build was adopted PARTIALLY twice in one night. Seats ran `just ensure-plugins` in one or a few projects, while the seat launcher resolves each target repository's build from installed_plugins.json at launch. Launches therefore went out on two builds at once: from 0.276.2 to 0.277.0, four projects stayed behind until ~00:56Z; from 0.277.0 to 0.278.0, only livespec-overseer had been moved at 02:54Z. Membership comes from livespec core's committed fleet manifest, which is already this section's source of truth for the member set (§"Sibling discovery"), not from a hand-kept list.

### Proposed Changes

In SPECIFICATION/contracts.md, under §"Cross-repo coordination automation surface", after the `### Fleet surface — central conformance and reconcile` subsection, add:

### Fleet-wide plugin adoption

This repository's justfile MUST ship an operator-invoked recipe, `just ensure-plugins-fleet`. It adopts the current plugin builds in every fleet member at once, so that no released plugin build is adopted by only some members. It is a local-vantage, operator-invoked surface, NOT a CI check, and it carries no run lever.

- **Membership.** The recipe MUST take the member set from livespec core's committed `.livespec-fleet-manifest.jsonc`, read as §"Sibling discovery" reads it. It MUST NOT carry or read a hand-kept member list.
- **Per-member adoption.** For each member, the recipe MUST run that member's OWN `ensure-plugins` recipe in that member's local clone, with the clone as the working directory. It MUST NOT reimplement a member's plugin reconcile.
- **Before and after builds.** For every member and every plugin that member's committed `.claude/settings.json` enables, the recipe MUST print the installed build before and after the member's `ensure-plugins` run. It MUST read both from `installed_plugins.json`, using the install record whose project path is that member's clone.
- **Failure isolation.** When a member's clone is missing, or its `ensure-plugins` recipe exits non-zero, the recipe MUST still run every remaining member. It MUST name each failed member with its cause, and it MUST exit non-zero.
- **Build convergence.** After every member has run, when one enabled plugin is installed at different builds across the members' project scopes, the recipe MUST exit non-zero. It MUST name that plugin, each build and the members holding it, even when every member's `ensure-plugins` succeeded.
- **Success.** The recipe MUST exit 0 only when every member's `ensure-plugins` succeeded and every enabled plugin is installed at a single build across the members that enable it.

In SPECIFICATION/scenarios.md, add:

## Scenario: one fleet-wide command adopts the current plugin builds in every fleet member and refuses a split adoption

Given livespec core's fleet manifest lists the members whose local clones are on this host, and each member's committed `.claude/settings.json` enables the orchestrator plugin

When the operator runs `just ensure-plugins-fleet` in livespec-dev-tooling

Then the recipe MUST run each member's own `ensure-plugins` recipe in that member's clone and MUST print, for every member and every enabled plugin, the installed build before and after, read from `installed_plugins.json` for that member's project path

And when one member's clone is missing, the recipe MUST still run every other member, MUST name the missing member and its cause, and MUST exit non-zero

And when every member's `ensure-plugins` succeeds but the orchestrator plugin is left installed at two different builds across the members, the recipe MUST exit non-zero, naming the plugin, both builds and the members holding each
