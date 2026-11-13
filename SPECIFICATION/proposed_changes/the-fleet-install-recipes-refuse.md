---
topic: the-fleet-install-recipes-refuse
author: claude:gmktec-factory-placement
created_at: 2026-11-13T00:44:34Z
---

## Proposal: The fleet install recipes refuse an orchestrator build the release branch does not name, except a declared and recorded canary adoption

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

`just ensure-plugins-fleet <build>` and the full-commit adopt step MUST read the commit that the orchestrator `release` branch names on the marketplace's remote, and MUST refuse any other build, whatever ref `known_marketplaces.json` records. The tag adopt of `just adopt-orchestrator-build` installs a build `release` does not name ONLY with an explicit `--canary` declaration, which it prints and appends to a host canary-adoption record; without the declaration it refuses.

### Motivation

MAINTAINER DIRECTION, about 00:3xZ on 2026-11-13, recorded by legacy-coordinator-agent as a scope event on livespec-dev-tooling-6tgd2z: "Ensure this doesn't happen again, and get things back on track ASAP." The direction followed the fix_commit_settle RoutingBlocked loss of six factory runs, a build whose canary never exercised the changed path. Rule CANARY-COVERS-CHANGED-PATHS makes the orchestrator's release-branch roll refuse a tag whose canary coverage record does not cover every changed workflow path (orchestrator proposal the-roll-refuses-a-tag-without-canary-coverage-of-changed-workfl, carrier bd-ib-5psq3e). That gate guards only the `release` branch, and two routes install an orchestrator build without moving it. First, `ensure-plugins-fleet` and the full-commit adopt check `<build>` against the commit of whatever ref `known_marketplaces.json` records, so they are gated only while that ref is `release`. Second, the tag adopt accepts any published tag that descends from `release`; taken once per clone, it installs an un-rolled, un-canaried build fleet-wide, which is the same per-clone shape every roll already uses for its hand adopts. The coordinator ruled this bypass closed under rule K (P1). A flat refusal would break canaries, because a canary clone MUST adopt an un-rolled tag (Scenario: a canary clone adopts a release tag ahead of the release branch). So the un-rolled tag adopt survives behind a printed, recorded `--canary` declaration. A canary adoption becomes a visible, auditable act, and a sweep of plain adopts cannot carry an unjudged build. livespec-dev-tooling-tv7obt's rollback recipe installs only ancestors of the marketplace tip, so it is untouched. Implementation carrier: livespec-dev-tooling-faetyh, whose launch judgement holds it at spec-change tier on this topic.

### Proposed Changes

Amend `contracts.md` §"Cross-repo coordination automation surface" as follows.

1. **Named build.** (the `just ensure-plugins-fleet <build>` bullet). After "it MUST refresh the orchestrator plugin's marketplace and read the commit as the adopt step reads it for a full commit id.", insert:

"It MUST also read the commit that livespec-orchestrator-beads-fabro's `release` branch names on the marketplace's remote, never from the host's marketplace clone. When that commit is not `<build>`, or when the commit the recorded ref names is not that commit, it MUST exit non-zero having run no member, naming the commits that differ. A roll therefore reaches only the build that `release` names, whatever ref `known_marketplaces.json` records."

2. **Adopt step.** After "For a full commit id, when that commit is not `<build>`, it MUST exit non-zero having moved nothing, naming both commits.", insert:

"For a full commit id, it MUST also read the commit that the `release` branch names on the marketplace's remote, and when that commit is not `<build>` it MUST exit non-zero having moved nothing, naming both commits."

3. **Tag adopt.** Append this paragraph to the bullet:

"A tag adopt whose tag's commit is not the commit that the `release` branch names on the marketplace's remote installs a build that has not been rolled. The recipe MUST take such a tag adopt only when the invocation carries the `--canary` declaration, as `just adopt-orchestrator-build <clone> <tag> --canary`. Without it, the recipe MUST refuse, moving nothing and naming the tag, its commit and the commit `release` names. With it, the recipe MUST print one line naming the clone, the tag, the tag's commit and the canary declaration. It MUST then append one line to the host's canary-adoption record, `~/.local/state/livespec-dev-tooling/canary-adoptions.jsonl`, naming the clone, the tag, the tag's commit, the commit `release` names, the operator identity and the UTC time. A tag adopt whose tag's commit is the commit `release` names needs no declaration. The declaration does not waive any other refusal of this bullet."

4. **Canaries and rolls.** Replace "An operator starts an orchestrator canary by a tag adopt of the release's tag in each canary clone, while `release` still names the last rolled build." with:

"An operator starts an orchestrator canary by a tag adopt of the release's tag, with the `--canary` declaration, in each canary clone, while `release` still names the last rolled build. The canary-adoption record then names every clone that holds an un-rolled build."

Amend `scenarios.md` without adding or removing a `## ` heading, so `tests/heading-coverage.json` needs no co-edit:

5. In "## Scenario: a canary clone adopts a release tag ahead of the release branch and the release branch does not move", change "When the operator runs `just adopt-orchestrator-build <A> T`" to "When the operator runs `just adopt-orchestrator-build <A> T --canary`", and append:

And the recipe MUST print one line naming A, T, T's commit and the canary declaration, and the host's canary-adoption record MUST gain one line naming A, T, T's commit, R, the operator identity and the UTC time
And when the operator instead runs `just adopt-orchestrator-build <A> T` with no `--canary` declaration, the recipe MUST exit non-zero having moved nothing, naming T, T's commit and R

6. In "## Scenario: one fleet-wide command adopts the current plugin builds in every fleet member and refuses a split adoption", after "And when the operator instead names a commit that is not X, the recipe MUST exit non-zero naming both commits, having run no member", insert:

And when the orchestrator's `release` branch on the marketplace's remote names a commit other than X, the recipe MUST exit non-zero naming both commits, having run no member
