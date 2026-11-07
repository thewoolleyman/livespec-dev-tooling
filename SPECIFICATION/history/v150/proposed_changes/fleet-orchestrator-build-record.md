---
topic: fleet-orchestrator-build-record
author: claude-opus-5-5
created_at: 2026-11-07T14:13:11Z
---

## Proposal: One committed fleet orchestrator build record governs every fleet clone's orchestrator adoption, and ensure-plugins is the only adopter

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Replaces v147's orchestrator roll hold with one committed fleet orchestrator build record, fleet/orchestrator-build.json, which names the orchestrator version every fleet clone may run (fleet_version) and the version the launch clone, livespec-orchestrator-beads-fabro, may run (launch_version). Every member's ensure-plugins adopts a newer orchestrator build only when the offered version equals that member's recorded version, so no SessionStart source (startup, resume, clear, compact, or a headless claude -p) moves any clone's orchestrator build. ensure-plugins becomes the only path that may adopt a plugin build in a fleet clone. A build found above its recorded version is reported as OUTSIDE RECORD and never downgraded, and ensure-plugins-fleet judges orchestrator convergence against the record. A roll (launch_version above fleet_version, with canaries and a proof matrix) is the special case that replaces the v147 hold. Rolls are value-only changes on the config-value fast path. The v147 scenario is replaced by two scenarios.

### Motivation

v147 (livespec-dev-tooling#3623) bound members only while a hold was unreleased, and exempted the launch clone outright. Combined with the SessionStart hook (matcher "", so every source), that let the launch clone's orchestrator build, the build the factory dispatches orchestrator work on, change as a side effect of session lifecycle events. On 2026-11-07 it moved three times with no roll step: (1) 01:29:32Z, source compact, kubernetes-sandbox-backend session 79f576b0, c681f61e16f9 -> 812c6bb59d02 (v0.297.0 -> v0.298.0), while v0.298.0's dev-tooling canary was still running; (2) ~03:20Z, source startup on a legacy-dispatcher-agent seat restart, 812c6bb59d02 -> 68e0a4999647 (v0.299.0); (3) 14:01:45Z, a HEADLESS `claude -p --model claude-sonnet-5-5` started by the DoD-preflight leg of the dispatcher's screen for bd-ib-zedjgq (screen-ticket-tw.sh -> dod-preflight-codexfirst.sh, transcript ecd231cf, entrypoint sdk-cli) with its cwd in the orchestrator primary checkout. Its SessionStart hook ran `just ensure-plugins`, which moved 68e0a4999647 -> 1f2b50ec3080 (v0.300.0) (measured by legacy-dispatcher-agent, session 2be3fdf7). Members moved the same way outside any hold on 2026-11-06 (livespec-dev-tooling, hetzner-xubuntu-info, homelab, livespec-overseer; scope events 11:27:53Z and 19:34:05Z on livespec-dev-tooling-me5aqz). Every move was caught only by a hand check of the LAUNCH-line version. All three 11-07 moves ran through ensure-plugins itself, so a rule enforced inside ensure-plugins binds every session kind, headless included. Every install route installs only the marketplace's newest build (claude plugin update has no version argument, and claude plugin install takes no ref), and a host-wide ref pin is forbidden by stop-the-line. So the record can only HOLD a build or ADOPT the newest one, never install an older one. Research note plan/gmktec-factory-placement/research/002-draft-launch-clone-roll-step.md (livespec-dev-tooling#3675) set out options A-D and recommended C (launch clone only). The maintainer asked 'Why C? Why not D, applied to every repository? If there's a good reason not to go with D, just explain it, then go with C'. legacy-coordinator-agent (session a37283d5) DECIDED option D fleet-wide under that delegation; the ruling is a priorities-record scope event on livespec-dev-tooling-6tgd2z at 2026-11-07T14:04:11Z. One record, not one per repository, keeps a roll to one PR, and the config-value fast path keeps that PR cheap, which is D's accepted cost. The v147 record was never implemented: livespec-dev-tooling-7upzav, which carries it, has not launched, and fleet/orchestrator-roll-hold.json does not exist on master. So the record can be redefined with no migration. 7upzav's Definition of Done is amended to this text after the revise and before it launches.

### Proposed Changes

In `contracts.md` §"Fleet-wide plugin adoption", rename the H4 "#### Orchestrator roll hold" to "#### Fleet orchestrator build record" and replace that subsection's whole body (its opening paragraph and every bullet, **Hold record.** through **Released hold.**) with the text below. The H2 set does not change.

> A member's `ensure-plugins` recipe is the reconcile that every fleet clone's SessionStart hook runs, on every SessionStart source (startup, resume, clear and compact). It is also the path through which `just bootstrap`'s local reconcile and `just ensure-plugins-fleet` adopt plugin builds. The orchestrator plugin, `livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro`, is adopted in every fleet member only through one committed fleet record, so one reviewed change moves the whole fleet's orchestrator build and nothing else moves it.
>
> - **Single adoption path.** In a fleet member's clone, only that member's `ensure-plugins` recipe MAY adopt a plugin build. No recipe, hook, verb or skill of this library, and no committed configuration of a fleet member, MAY run `claude plugin update` or `claude plugin install` for a plugin outside `ensure-plugins`, or enable any automatic plugin update that a Claude Code session, interactive or headless, would apply on its own.
> - **The record.** livespec-dev-tooling's master branch MUST carry exactly one committed fleet orchestrator build record at `fleet/orchestrator-build.json`, validated by a JSON schema this repository ships beside it. Each member's `ensure-plugins` MUST fetch the record from livespec-dev-tooling master at run time, the way §"Sibling discovery" fetches the fleet manifest. The record is a JSON object with exactly these keys:
>   - `plugin`: the orchestrator plugin's install key, `livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro`.
>   - `fleet_version`: a semver string, the orchestrator version every member except the launch clone may run.
>   - `launch_version`: a semver string, the orchestrator version the launch clone may run.
>   - `implement_graph_blob`: the git blob id of `implement-work-item/workflow.fabro` in the `launch_version` build.
>   - `canaries`: an array of objects, each carrying `item`, `criteria` and `verdict`, where `verdict` is one of `pending`, `passed` or `failed`.
>   - `matrix`: an object with the keys `fresh`, `seeded` and `non_orchestrator`, each a passing factory run id or `null`.
>   - `recorded_on`: the ledger id of the plan epic where the roll's evidence is recorded.
>
>   The roll to `launch_version` is RELEASED when every canary verdict is `passed` and every `matrix` value names a run, and UNRELEASED otherwise.
> - **Record validity.** A record MUST be treated as unreadable when it does not parse against the schema, when `launch_version` is below `fleet_version`, or when `fleet_version` equals `launch_version` while the roll is unreleased.
> - **Recorded version.** A member's recorded version is `launch_version` for the launch clone and `fleet_version` for every other member. The launch clone is the member whose repository is the orchestrator plugin's own source repository, livespec-orchestrator-beads-fabro. A roll is the special case `launch_version` above `fleet_version`: the launch clone runs the build under canary and proof-matrix test, and every other member keeps `fleet_version`.
> - **Adoption.** When the marketplace offers the orchestrator plugin at a version newer than the member's installed build, `ensure-plugins` MUST adopt it ONLY when the offered version equals the member's recorded version. Otherwise it MUST leave the installed build unchanged and print one line naming the plugin, the installed version, the offered version and the recorded version. For a member other than the launch clone, while the roll is unreleased, that line MUST also name each unmet release condition. The orchestrator plugin MUST NOT make the recipe exit non-zero, and `ensure-plugins` MUST still reconcile every other enabled plugin exactly as it does today.
> - **Absent install.** When a member enables the orchestrator plugin and has no build of it installed, `ensure-plugins` MUST install the offered build. When the offered version is not the member's recorded version, it MUST also print one `NOT RECORDED` line naming the installed and recorded versions.
> - **Adopted outside the record.** When a member's installed orchestrator build is above its recorded version, `ensure-plugins` MUST leave it installed, MUST NOT downgrade it, and MUST print one `OUTSIDE RECORD` line naming the installed version, the recorded version and the install record's `lastUpdated` value.
> - **Unreadable or absent record.** When the record is absent, cannot be fetched, or is unreadable under **Record validity.**, `ensure-plugins` MUST leave the installed orchestrator build unchanged, MUST print one line naming the cause, which distinguishes an absent record from an unreadable one, and MUST reconcile every other plugin.
> - **Rolls are value-only changes.** livespec-dev-tooling's config-value fast-path list (§"Config-value fast path at pre-commit") MUST cover these key paths of `fleet/orchestrator-build.json`: `fleet_version`, `launch_version`, `implement_graph_blob`, `recorded_on`, `matrix.fresh`, `matrix.seeded`, `matrix.non_orchestrator`, and each canary's `item`, `criteria` and `verdict`. Starting a roll, recording its evidence and releasing it to the fleet are then each a value-only change. A change that adds or removes a canary entry takes the normal path.

In the same section, replace the **Build convergence.** and **Success.** bullets with:

> - **Build convergence.** After every member has run, when one enabled plugin other than the orchestrator plugin is installed at different builds across the members' project scopes, the recipe MUST exit non-zero. It MUST name that plugin, each build and the members holding it, even when every member's `ensure-plugins` succeeded. The orchestrator plugin is judged against the fleet orchestrator build record (below) instead. The recipe MUST print one `RECORDED` line naming `fleet_version`, `launch_version` and the members on each installed version. It MUST exit non-zero, naming each member and its cause, when any member's installed orchestrator version differs from that member's recorded version, or when the record is absent or unreadable.
> - **Success.** The recipe MUST exit 0 only when every member's `ensure-plugins` succeeded, every enabled plugin other than the orchestrator plugin is installed at a single build across the members that enable it, and every member's installed orchestrator version equals its recorded version.

In `scenarios.md`, REMOVE "## Scenario: a fleet clone's ensure-plugins keeps its orchestrator build while an orchestrator roll hold is unreleased", and add the two scenarios below in its place:

```gherkin
## Scenario: a fleet clone adopts an orchestrator build only when the committed fleet orchestrator build record names it

Given livespec-dev-tooling master carries `fleet/orchestrator-build.json` with `fleet_version` 0.299.0 and `launch_version` 0.300.0, one canary whose verdict is `pending`, and a `matrix` whose `seeded` value is `null`

And livespec-orchestrator-beads-fabro's clone has orchestrator build 0.299.0 installed, and another fleet member has 0.299.0 installed

When the marketplace offers 0.300.0 and a Claude Code session starts in each clone, so each SessionStart hook runs `just ensure-plugins`

Then the livespec-orchestrator-beads-fabro clone's `installed_plugins.json` orchestrator record MUST name 0.300.0

And the other member's orchestrator record MUST still name 0.299.0, and its recipe MUST print one line naming the plugin, the installed 0.299.0, the offered 0.300.0, the recorded 0.299.0, the pending canary and the missing seeded run, and MUST exit 0

And when the marketplace then offers 0.301.0 and a session in the livespec-orchestrator-beads-fabro clone compacts, that clone's orchestrator record MUST still name 0.300.0, and its recipe MUST print one line naming the installed 0.300.0, the offered 0.301.0 and the recorded 0.300.0

And when a value-only change sets the canary verdict to `passed`, names a seeded run, and sets `fleet_version` and `launch_version` to 0.301.0, the next SessionStart run in each clone MUST install 0.301.0

And when the record sets `fleet_version` equal to `launch_version` while a canary verdict is `pending`, every member's orchestrator build MUST stay unchanged and each recipe MUST print one line naming the record as unreadable

And when `just ensure-plugins-fleet` runs while the launch clone is on `launch_version` and every other member is on `fleet_version`, it MUST print one `RECORDED` line naming both versions and the members on each, and MUST NOT exit non-zero for the orchestrator plugin
```

```gherkin
## Scenario: an orchestrator build adopted outside ensure-plugins is reported and never downgraded

Given livespec-dev-tooling master carries `fleet/orchestrator-build.json` with `fleet_version` and `launch_version` both 0.299.0 and a released roll

And a fleet member's orchestrator build was moved to 0.300.0 by a path other than its `ensure-plugins` recipe

When that member's SessionStart hook runs `just ensure-plugins`

Then the member's orchestrator record MUST still name 0.300.0

And the recipe MUST print one `OUTSIDE RECORD` line naming the installed 0.300.0, the recorded 0.299.0 and the install record's `lastUpdated` value

And when `just ensure-plugins-fleet` then runs, it MUST exit non-zero, naming that member, its installed 0.300.0 and its recorded 0.299.0

And a scan of this library's recipes, hooks, verbs and skills, and of every fleet member's committed `.claude/settings.json`, MUST find no `claude plugin update` or `claude plugin install` call outside `ensure-plugins` and no enabled automatic plugin update
```

Co-edits the revise commit MUST carry:

- `tests/heading-coverage.json`: drop the removed scenario's entry, and add one entry per new `## Scenario` heading. Each is a `"test": "TODO"` row whose `reason` names the integration tier and livespec-dev-tooling-7upzav as the owner of the owed test.
- `tests/heading-coverage-debt.json`: regenerated with `just generate-heading-coverage-debt-register`.

