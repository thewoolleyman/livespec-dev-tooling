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

`just adopt-orchestrator-build <clone> <build>` today refuses any build other than the commit the host's marketplace clone names at `release`, so a canary can adopt a build only after `release` has been fast-forwarded to it. This proposal adds a second accepted form, a published orchestrator release tag whose commit descends from the commit `release` names: the *tag adopt*. The tag adopt builds the tag in a throwaway builder home, copies that build into the host's plugin cache, and rewrites only the named clone's install record. It never runs a `claude plugin` command against the host's own home and never changes the host's marketplace declaration or registration, so no other clone's install can move while it runs. The Canaries and rolls bullet then starts a canary with a tag adopt, and releases a roll by fast-forwarding `release` only after the canary's samples pass.

### Motivation

On 2026-11-09 the orchestrator 0.308.0 canary failed only after `release` had already been fast-forwarded, and six fleet projects' session reconciles had adopted the broken build. A corrective v0.309.2 roll was needed. At about 17:0xZ the maintainer accepted livespec-orchestrator-beads-fabro#4749, which orchestrator spec v337 then ratified: `release` advances only at the roll step, after a release's canary samples pass, and canary clones are moved by a named-build adopt naming the tag. That adopt must leave the commit `release` names, the host's marketplace registration and every other clone's install record unchanged, and "another clone's install MUST NOT move while it runs". This repository's ratified Adopt step cannot take a tag at all, so the ruling has no executable route here.

On 2026-11-10 at about 00:2xZ legacy-coordinator-agent put this chain on expedited-incident-response-flag's critical path: its second rehearsal needs orchestrator v0.311.1 or later in livespec-dev-tooling, reached only through a canary. Linked work item: livespec-dev-tooling-zpqvnr (plan gmktec-factory-placement, epic livespec-dev-tooling-me5aqz), which blocks on livespec-dev-tooling-7upzav. livespec-dev-tooling-tv7obt (rollback to a named earlier release) reuses the same primitive.

THIS IS A SECOND RE-FILE. Two earlier designs re-pointed the host's single marketplace slot at the tag for a window: first by editing the registration, then by editing the user-scope `extraKnownMarketplaces` ref. Pre-commit doctor walks rejected both. homelab (`.claude/hooks/ensure_plugins.py`), resume (`.claude/hooks/ensure-plugins.ts`), openbrain, livespec-tdd-proof and about 12 old worktrees run `claude plugin update <plugin> -s project` at session start, outside any lock this library could hold. During such a window those runs would take the tag, which breaks v337. A pin-based refusal for them could not be computed either.

The mechanism below never opens a window. It was PROVEN on 2026-11-10, on Claude Code 2.1.321, with a scratch target home holding two clones A and B, both installed at project scope at `release` (456712f1af12):
- A builder home whose user settings declare the marketplace at `ref: v0.311.1` ran `claude plugin marketplace add <repo>#v0.311.1` and `claude plugin install ... -s project` in a throwaway clone. That gave a record with `gitCommitSha` fec4e26d9ab0d26945f856ff58a0ce13160ad887 and a cache directory named by the commit's 12-character prefix.
- Copying that directory into the target's plugin cache, and atomically rewriting only A's record (`installPath`, `version`, `gitCommitSha`, `lastUpdated`), left the target's user settings, `known_marketplaces.json` and marketplace clone byte-identical, and B's record byte-identical.
- `claude plugin list` showed A at the tag. A bare `install` in A was a no-op. `update` in B kept B on `release`. A target `marketplace update` did not delete the copied directory. livespec-dev-tooling's registry and artifact probes accepted A's build.
- The backward move worked too: a full-commit adopt's `claude plugin update -s project` in A moved A from the tag back to `release`'s commit.
- Claude Code validates no checksum for a marketplace plugin's cache directory. The plugin's own `cache-manifest.json` `required_paths` is the completeness check.

A pre-commit doctor walk of this mechanism found no HIGH finding. Its MEDIUM findings are folded in: staging outside the plugin cache, orphan markers, the pre-rename re-check, a write-time-only check of other records, and a probe-based canary-clone refusal. The tag adopt depends on livespec-dev-tooling-7upzav (livespec-dev-tooling#3900), because no released package carries the **Session reconcile.** hold before it merges.

The residual risk is a concurrent writer of `installed_plugins.json`. Any `claude plugin install`, `update` or `uninstall` in any project rewrites the whole file, under no lock this library shares, so a write that read before the transplant's rename can revert A's record silently. The tag adopt therefore re-reads A's record after a settle period and fails when it has reverted.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Cross-repo coordination automation surface", subsection "Orchestrator build adoption":

1. In the bullet that begins "- **Broken install.**", replace "No install route takes a version, so the repair installs the build the marketplace offers, which can move the build." with "The repair takes no version, so it installs the build the marketplace offers, which can move the build."

2. In the bullet that begins "- **Adopt step.**", replace the sentence "When that commit is not `<build>`, it MUST exit non-zero having moved nothing, naming both commits." with "For a full commit id, when that commit is not `<build>`, it MUST exit non-zero having moved nothing, naming both commits."

3. In the same bullet, replace "It MUST exit non-zero, naming the cause, when the clone is missing, when the clone's committed settings do not enable the plugin, when any command it runs exits non-zero, or when the install record's `gitCommitSha` afterwards is not `<build>`." with "For either form, it MUST exit non-zero, naming the cause, when the clone is missing, when the clone's committed settings do not enable the plugin, or when any command it runs exits non-zero, and for a full commit id also when the install record's `gitCommitSha` afterwards is not `<build>`."

4. Insert this bullet immediately AFTER the "- **Adopt step.**" bullet:

"- **Tag adopt.** `<build>` MAY instead be a published release tag of the orchestrator plugin: a tag of livespec-orchestrator-beads-fabro that names a published GitHub release. This is the *tag adopt*. When `<build>` is neither a full commit id nor a published release tag, the recipe MUST refuse it, moving nothing and naming the argument. A tag adopt MUST resolve the tag's commit (the peeled tag) and the commit that the marketplace's recorded ref names, both from the marketplace's remote. When the recorded ref's commit is neither the tag's commit nor an ancestor of it, it MUST refuse, moving nothing and naming both commits.

  The tag adopt MUST refuse, moving nothing and naming the clone, unless the livespec-dev-tooling package that the clone's own `just ensure-plugins` runs provides the **Session reconcile.** hold. That package is the clone's own environment, or this checkout when the clone is livespec-dev-tooling itself. The recipe MUST establish this by probing that package for the hold, not by reading the clone's pin or a version string, because a clone's environment can differ from its pin. A clone that runs no `just ensure-plugins`, or whose package cannot be probed, MUST be refused. Otherwise the clone's next session start would move its build back.

  The tag adopt MUST NOT run any `claude plugin` command with the host's home as its home. It MUST NOT change the host's user-scope settings, the host's marketplace registration (`known_marketplaces.json`) or the host's marketplace clone. It moves the clone's build by these steps instead:

  - **Build.** In a throwaway builder home, created under a disk-backed scratch directory and deleted on every exit, the recipe MUST:
    - write a user-scope settings file that declares the orchestrator marketplace at the tag;
    - register the marketplace at the tag;
    - install the plugin at project scope in a throwaway clone whose committed settings enable it and declare the marketplace at the tag.

    When the builder's install record's `gitCommitSha` is not the tag's commit, it MUST refuse, moving nothing.
  - **Copy.** It MUST copy that build into the host's plugin cache, into the plugin's cache directory named by the commit's 12-character prefix, which is where a `claude plugin update` to that commit installs, unless that directory already exists there. It MUST NOT copy the cache's `.in_use` or `.orphaned_at` markers. The copy MUST be staged in a temporary directory outside the plugin's cache directory and land by a rename. Each run MUST first remove any stale staging directory an earlier interrupted run left. The build MUST carry a `cache-manifest.json`, and the directory the record will name, whether copied or already present, MUST carry every path that manifest lists as required. Otherwise the recipe MUST refuse, moving nothing.
  - **Record.** The clone MUST have exactly one project-scope orchestrator install record, or the recipe MUST refuse, moving nothing. It MUST rewrite only that record in the host's `installed_plugins.json`, setting:
    - `installPath` to the cache directory above;
    - `version` to the commit's 12-character prefix;
    - `gitCommitSha` to the tag's commit;
    - `lastUpdated` to the time of the write.

    It MUST leave `installedAt` and every other record unchanged. It MUST write the file through a temporary file and an atomic rename. Immediately before the rename it MUST re-read the file. When the file changed since it was read, the recipe MUST re-apply its one change to the newly read content, at most three times, and then refuse. A write by another process that lands between that last re-read and the rename can still be lost; this is a known residual of a file that every `claude plugin` command rewrites whole. After the rename, it MUST remove any `.orphaned_at` marker from the directory the record names.
  - **Verify.** At the write, the recipe MUST check that the file it wrote differs from the content it last read only in the clone's record. It MUST then re-read the clone's record immediately, and again after a settle period of at least 60 seconds, and exit non-zero, naming the cause, when its `gitCommitSha` is not the tag's commit. It MUST compare builds by `gitCommitSha`, never by the `version` string, which the CLI writes in more than one form. Changes to other records after the write are other writers' business, and the recipe MUST NOT judge them. Another writer's rewrite of the file can silently revert the clone's record, and running the tag adopt again is the recovery.

  The recipe MUST print the clone's build before and after. A Claude Code session already running in the clone keeps the build it loaded until it is reloaded."

5. Insert this bullet immediately AFTER the "- **Tag adopt.**" bullet:

"- **Adoption lock.** A tag adopt, a full-commit adopt step run on its own, and `just ensure-plugins-fleet` MUST each hold one host-wide adoption lock exclusively for their whole run, so that two of them never write the host's `installed_plugins.json` at once. The adopt step that `just ensure-plugins-fleet` runs for a member runs under the fleet recipe's own hold, and MUST NOT take the lock a second time. A process that ends MUST release the lock. The lock serializes this library's adoptions only; a `claude plugin` command run anywhere else on the host does not take it, which is why **Tag adopt.** verifies after a settle period."

6. In the bullet that begins "- **Named build.**", replace "it MUST refresh the orchestrator plugin's marketplace and read the commit as the adopt step reads it." with "it MUST refresh the orchestrator plugin's marketplace and read the commit as the adopt step reads it for a full commit id."

7. In the bullet that begins "- **Canaries and rolls.**", replace " An operator releases a roll by running `just ensure-plugins-fleet <build>`. No install route takes a version, so a roll can only reach the marketplace's newest build. When a newer build has been released since the canary, both recipes refuse the canaried commit. The operator then decides whether the canary's evidence carries to the newer build or the canary must be re-run, and names that newer commit." with:

" An operator starts an orchestrator canary by a tag adopt of the release's tag in each canary clone, while `release` still names the last rolled build. An operator MUST take a tag adopt only in a clone whose SessionStart reconcile is this library's `ensure-plugins` at a release that carries the **Session reconcile.** hold, so that no session start in that clone moves its build back during the canary. An operator MUST NOT advance `release` to a build until that build's canary samples have passed. After they pass, the operator advances `release` to the build through livespec-orchestrator-beads-fabro's fast-forward-only release-branch workflow, and releases the roll by running `just ensure-plugins-fleet <build>`. `just ensure-plugins-fleet` takes no tag, so a roll reaches only the commit `release` names, and when that commit is not `<build>` the recipe refuses it, as **Named build.** states. When the canary samples fail, `release` does not advance, and the operator returns each canary clone to the build `release` names with the full-commit adopt step naming that commit."

8. In the same bullet, replace "because a factory worker resolves its build at run prepare and that build can be newer than the launch build." with "because a factory worker resolves its build at run prepare and that build can differ from the launch build."

In SPECIFICATION/scenarios.md, append:

"## Scenario: a canary clone adopts a release tag ahead of the release branch and the release branch does not move

Given the orchestrator marketplace's `release` ref names commit R, and a published release tag T whose commit descends from R
And clones A and B whose project-scope orchestrator install records name R
When the operator runs `just adopt-orchestrator-build <A> T`
Then A's install record MUST name T's commit as its `gitCommitSha`
And B's install record MUST still name R
And the host's user-scope settings, marketplace registration and marketplace clone MUST be unchanged
And when the operator then runs `just adopt-orchestrator-build <A> R`, A's install record MUST name R again
And when the operator runs the recipe with a tag whose commit does not descend from R, it MUST exit non-zero having moved nothing, naming both commits"

The revise pass that accepts or modifies this proposal MUST co-edit tests/heading-coverage.json with one entry for the new scenario heading. The entry MAY be a spec-first "test": "TODO" row whose reason names the tier the owed test runs at (a real test at the integration tier or above, with the live leg host-captured), with a "work_item" key naming livespec-dev-tooling-zpqvnr, and the debt register MUST be regenerated in the same commit.
