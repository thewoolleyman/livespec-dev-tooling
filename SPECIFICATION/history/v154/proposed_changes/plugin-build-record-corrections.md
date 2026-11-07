---
topic: plugin-build-record-corrections
author: claude-opus-5-5
created_at: 2026-11-07T16:26:54Z
---

## Proposal: Correct the fleet plugin build record so a release can reach members, evidence is bound to a graph blob, and its versions and scope are defined

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Corrects spec v150's fleet plugin build record, which cannot work as ratified. A release must name the build the marketplace offers when it merges, followed at once by ensure-plugins-fleet, and a member that misses the window prints STRANDED. Canary and matrix evidence attests an implement graph blob, and a member refuses to adopt an offered build whose graph blob differs from the entry's. Installed version is read from plugin.json at the install path. The rule's scope is stated: Claude Code project installs in every manifest repository that enables a covered plugin, adopters included, and not Codex's host-wide install. An absent or unreadable record adopts and installs nothing. The fast path's validation also evaluates record validity, and missing scenario lines are added.

### Motivation

The LLM doctor phases, run read-only on v150 at the coordinator's request on 2026-11-07 after being skipped as post-steps, returned 14 findings. This seat verified four against live state. (O1) known_marketplaces.json has the orchestrator marketplace on ref `release`, a moving branch; `git tag` shows 32 orchestrator tags since 2026-11-03, about 8 a day; and no install route takes a version (research note 002). v150 adopts only when the offered version equals the recorded version, so a record naming a proven build that is no longer newest moves nobody, members strand, and the armed check stays red. (O3) installed_plugins.json's `version` for this project is 1f2b50ec3080, with `gitCommitSha` the full commit; the semver 0.300.0 is in <installPath>/plugin.json. v150's rules compare semver and its scenarios say the record names 0.300.0, which is false on real records. (O4) scripts/just/ensure-codex-plugins.sh runs `codex plugin marketplace upgrade` for the orchestrator's marketplace, host-wide, contradicting 'nothing else moves it'. (O5) the fleet manifest has 10 fleet entries and 12 adopters, v150 does not say whether adopters are bound, and homelab's .claude/hooks/ensure_plugins.py runs `claude plugin update` directly. (O2) follows from v150's own text: canaries and matrix name no build and no clause reads implement_graph_blob, so verdicts left from an earlier roll would make a new build read as RELEASED after a version-only edit. The matrix here has attested the implement graph since this plan's 2026-11-06T13:12Z decision, so the blob is the right binding, and it carries the non-material rulings the coordinator already uses. The agent's further findings are taken on their text: O6 the lead paragraph, O7 schema validation alone cannot check a cross-field rule, O8 and earlier reviewer notes for the missing scenario lines, O9 'value-only' overclaiming, S3 lowercase normative words, S4 status text and a hard-coded plugin, S5 'released roll'. Rejected for O1: holding the `release` ref during a roll, because it stops every other tag in the release train; and adopting anything at or above the recorded version, because that is the unproven movement option D exists to stop. livespec-dev-tooling-7upzav carries an owner hold until this lands, because a worker's brief freezes at dispatch and that item was ticketed against v150. The coordinator rules this revise under R301.

### Proposed Changes

All changes are in `contracts.md` §"Fleet-wide plugin adoption" and `scenarios.md`. No `## ` heading is added, removed or renamed, so `tests/heading-coverage.json` needs no row change. The two scenarios named below keep their rows, owned by livespec-dev-tooling-7upzav.

**Lead paragraph of §"Fleet-wide plugin adoption".** Replace its second sentence with: "It adopts each member's recorded build of every plugin the fleet plugin build record covers, and the current build of every other enabled plugin, so that no plugin build is adopted by only some members outside a recorded roll."

**Opening paragraph of "#### Fleet plugin build record".** Replace its last two sentences ("Today the record covers only…" and "Bringing another plugin…") with:

> The keys of the record's `plugins` object are the plugins it covers. Bringing another plugin under it is a value edit that adds one entry, not a specification change. These rules govern Claude Code project-scope installs in the local clone of every repository in livespec core's fleet manifest, fleet or adopter, whose committed `.claude/settings.json` enables a covered plugin. An adopter whose SessionStart hook does not run the shared reconcile MUST be changed to apply these rules. Codex plugin installs are host-wide and operator-invoked through `just ensure-codex-plugins`. No per-member recorded version can apply to a host-wide install, so the record does not govern them.

**Add these bullets immediately before **The record.**:**

> - **Versions.** A member's installed version of a plugin MUST be read from the `version` in `plugin.json` at the `installPath` of its `installed_plugins.json` record whose project path is that clone, because that record's own `version` field holds a commit id. The offered version MUST be read from the `version` in `plugin.json` at the marketplace's current ref. Versions MUST compare by semver precedence.

**In **The record.**:**

- `fleet_version` becomes: "a semver string, the only version `ensure-plugins` adopts in a member other than that plugin's launch clone."
- `launch_version` becomes: "a semver string, the only version `ensure-plugins` adopts in that plugin's launch clone."
- Each canary object also carries `attests_blob`: the implement graph blob the verdict was earned on, or `null` for a plugin with no implement graph.
- `matrix` also carries `attests_blob`: the implement graph blob its legs ran on.
- The RELEASED sentence becomes: "A plugin entry's evidence is RELEASED when every one of its canary verdicts is `passed` with an `attests_blob` equal to the entry's `implement_graph_blob` (an empty `canaries` array has none outstanding), and either its `matrix` is `null` or every one of its `matrix` legs names a run and its `attests_blob` equals the entry's `implement_graph_blob`. The evidence is UNRELEASED otherwise. So a plugin with nothing under roll, such as a livespec core or Driver entry with an empty `canaries` array and a `null` `matrix`, is RELEASED."

**In **Record validity.**:** replace "The record must never tell every member…" with "The record MUST NOT tell every member to run a build that is still under test."

**In **Adoption.**:** append:

> Before adopting, `ensure-plugins` MUST compare the git blob of `implement-work-item/workflow.fabro` in the offered build with the plugin entry's `implement_graph_blob`, when that value is not `null`. When they differ, it MUST leave the installed build unchanged and print one line naming the plugin, the offered version and both blobs. Evidence therefore cannot follow a version edit onto a build whose implement graph it never ran. Carrying evidence across a graph change its canary's owner rules non-material is an explicit edit of `implement_graph_blob` and each `attests_blob` in one change, with the ruling recorded on `recorded_on`.

**Add these bullets immediately after **Adoption.**:**

> - **Releasing a roll.** The marketplace tracks a moving `release` ref, and no install route can install anything but its newest build. So a change that raises `fleet_version` or `launch_version` MUST name the version the marketplace offers when that change merges. A recorded version that is not the offered version moves no member. After merging a change that raises `fleet_version`, the seat making the roll MUST run `just ensure-plugins-fleet` at once, so that every member adopts before the next release moves `release` again.
> - **Stranded member.** When a member's installed version is below its recorded version and the offered version is above its recorded version, `ensure-plugins` MUST leave the installed build unchanged and print one `STRANDED` line naming the plugin, the installed version, the offered version and the recorded version. The remedy is a new value-only change naming the offered version, not an install by hand.

**Replace **Unreadable or absent record.** with:**

> - **Unreadable or absent record.** When the record is absent, cannot be fetched, or is unreadable under **Record validity.**, the set of covered plugins is unknown. So `ensure-plugins` MUST adopt and install no plugin build in that run, MUST print one line naming the cause, which distinguishes an absent record, a failed fetch and an unreadable one, and MUST exit 0.

**In **Adoption before arming.**:** replace "So no member's recorded version may equal…" with "So no member's recorded version MUST equal the version the marketplace offers at that moment, unless that member already runs it."

**In **Rolls are value-only changes.**:** add the `attests_blob` key paths to the covered list. Replace "Starting a roll, recording its evidence and releasing it to the fleet are then each a value-only change." with "Starting a roll, recording its evidence and releasing it to the fleet are then each a value-only change, when the entry already has the canary entries and the `matrix` shape that roll needs." Replace "A change that adds or removes a canary entry or a plugin entry takes the normal path." with "A change that adds or removes a canary entry or a plugin entry, or moves `matrix` between `null` and an object, takes the normal path." Replace "That fast path is still being built. Until it exists," with "Until that fast path exists,". Append: "For this file, the fast path's schema and parse validation MUST also evaluate **Record validity.**, so a value edit that would make the record unreadable refuses the commit and cannot freeze the fleet."

**`scenarios.md`, "a fleet clone's ensure-plugins keeps its orchestrator build while an orchestrator roll hold is unreleased":**

- Replace each "`installed_plugins.json` orchestrator record MUST name" and "orchestrator record MUST (still) name" with "installed orchestrator version MUST be", the installed version being read per **Versions.**.
- Give the canary and `matrix` in the Given line an `attests_blob` equal to the entry's `implement_graph_blob`.
- In the release line, also set `implement_graph_blob` and each `attests_blob` to the 0.301.0 build's blob, and say the marketplace offers 0.301.0 when that change merges.
- Add these lines before the `just ensure-plugins-fleet` line:

```gherkin
And when a value-only change raises `fleet_version` to 0.301.0 but leaves `implement_graph_blob` at the 0.300.0 build's blob, and the 0.301.0 build's graph blob differs, each recipe MUST leave its installed build unchanged and MUST print one line naming the plugin, the offered 0.301.0 and both blobs

And when a member's installed version is 0.299.0, its recorded version is 0.300.0 and the marketplace offers 0.301.0, its recipe MUST leave 0.299.0 installed and MUST print one `STRANDED` line naming the plugin and all three versions

And when the record cannot be fetched, each recipe MUST adopt and install no plugin build, MUST print one line naming the failed fetch, and MUST exit 0

And when the record is absent, a member with no orchestrator build installed MUST still have none after its recipe runs

And when a record's `launch_version` is below its `fleet_version`, or the record fails its schema, each recipe MUST treat it as unreadable

And when `just ensure-plugins-fleet` runs while the record is absent or unreadable, it MUST exit non-zero naming the cause
```

- Replace "the record is absent from livespec-dev-tooling master, every member's orchestrator build MUST stay unchanged" so that it says every plugin build, per the new unreadable-or-absent rule.

**`scenarios.md`, "an orchestrator build adopted outside ensure-plugins is reported and never downgraded":** in the Given line replace "and a released roll" with "and released evidence". Replace "orchestrator record MUST still name 0.300.0" with "installed orchestrator version MUST still be 0.300.0".

