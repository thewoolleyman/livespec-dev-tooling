---
topic: a-canary-clone-adopts-a
author: claude-opus-5-5
created_at: 2026-11-09T19:24:53Z
---

## Proposal: The adopt step installs a published orchestrator release tag ahead of the release branch in one named clone, and leaves the release branch where it was

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

`just adopt-orchestrator-build <clone> <build>` today refuses any build that is not the commit the host's marketplace clone names at the `release` ref, so a canary can only adopt a build after `release` has been fast-forwarded to it. This proposal adds a second accepted form: a published orchestrator release tag whose commit descends from the commit `release` names. The recipe installs that tag's build at project scope in the one named clone. It points the host's single marketplace slot at the tag only for that install, under a lock it shares with `just ensure-plugins-fleet`, and restores the slot to `release` at its prior commit on every exit. The Canaries and rolls bullet then starts a canary by this tag adopt and releases a roll by fast-forwarding `release` only after the canary's samples pass.

### Motivation

On 2026-11-09 the orchestrator 0.308.0 canary failed only after `release` had already been fast-forwarded, and six fleet projects' session reconciles had adopted the broken build. A corrective v0.309.2 roll was needed to recover. The maintainer then ruled, at about 17:0xZ that day, accepting livespec-orchestrator-beads-fabro#4749: the orchestrator `release` branch advances only at the roll step, after a release's canary samples pass, and canary clones adopt the release by a named-build adopt naming its tag. This repository's ratified Adopt step cannot do that. It refuses any build that is not the marketplace tip, and the section states that no install route takes a version. The maintainer's ruling therefore has no executable route here, and the orchestrator v0.310.x canary is held on it (legacy-coordinator-agent agreed 2026-11-09 ~19:2xZ that no old-order roll runs). Linked work item: livespec-dev-tooling-zpqvnr (plan gmktec-factory-placement, epic livespec-dev-tooling-me5aqz), which blocks on livespec-dev-tooling-7upzav. Once 7upzav lands, a session reconcile no longer moves the orchestrator build, so a brief, locked change of the shared marketplace slot cannot leak into another clone through a SessionStart. livespec-dev-tooling-tv7obt (rollback to a named earlier release) reuses the same install-a-named-tag primitive.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Cross-repo coordination automation surface", subsection "Orchestrator build adoption", in the bullet that begins "- **Adopt step.**", insert after the sentence "`<build>` is the full commit id the operator means to adopt.":

"`<build>` MAY instead be a published release tag of the orchestrator plugin, the tag adopt. For a tag adopt, the recipe MUST resolve the tag to its commit and read the commit the host's marketplace clone names at `origin/<ref>`, for the ref `known_marketplaces.json` records, after refreshing that marketplace. It MUST refuse, moving nothing and naming both commits, when that `release` commit is not an ancestor of, or equal to, the tag's commit. It MUST refuse, moving nothing and naming the ref, when `<build>` is neither a full commit id nor a published release tag. Otherwise, holding the one lock that `just ensure-plugins-fleet` also takes, the recipe MUST point the host's orchestrator marketplace slot at the tag, refresh it, run `claude plugin update` for that plugin at project scope with the clone as the working directory, and then restore the slot to the ref and the commit it named before, refreshing it again. It MUST restore the slot on every exit, a failed or interrupted run included, and it MUST NOT run `claude plugin update` or `claude plugin install` in any other clone. It MUST exit non-zero, naming the cause, when the install record's `gitCommitSha` afterwards is not the tag's commit, or when the slot does not afterwards name the ref and commit it named before."

In the same bullet, the existing sentence "When that commit is not `<build>`, it MUST exit non-zero having moved nothing, naming both commits." applies to the full-commit-id form only. Prefix it with "For a full commit id,".

In the bullet that begins "- **Canaries and rolls.**", replace the sentence "An operator releases a roll by running `just ensure-plugins-fleet <build>`." with:

"An operator starts an orchestrator canary by a tag adopt of the release's tag in each canary clone, while `release` still names the last rolled build. An operator MUST NOT advance `release` to a build until that build's canary samples have passed. After they pass, the operator advances `release` to the build and releases the roll by running `just ensure-plugins-fleet <build>`."

In SPECIFICATION/scenarios.md, append:

"## Scenario: a canary clone adopts a release tag ahead of the release branch and the release branch does not move

Given the orchestrator marketplace's `release` ref names commit R, and a published release tag T whose commit descends from R
When the operator runs `just adopt-orchestrator-build <scratch clone> T`
Then that clone's install record MUST name T's commit
And the host's orchestrator marketplace slot MUST afterwards name `release` at R
And no other clone's install record MUST change
And when the operator runs the recipe with a tag whose commit does not descend from R, it MUST exit non-zero having moved nothing, naming both commits"

The revise pass that accepts or modifies this proposal MUST co-edit tests/heading-coverage.json with one entry for the new scenario heading. The entry MAY be a spec-first "test": "TODO" row whose reason names the host-captured tier, plus a "work_item" key naming livespec-dev-tooling-zpqvnr, and the debt register MUST be regenerated in the same commit.
