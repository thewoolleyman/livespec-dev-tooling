---
topic: a-release-please-pull-request
author: claude-opus-5-5
created_at: 2026-11-13T04:03:48Z
---

## Proposal: A release-please pull request lands only release-owned changes, enforced before merge by a release-PR scope check

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md §"Versioning" with a rule that a release-please pull request may land only release-owned changes, enforced before merge by a release-PR scope check that this library ships and every fleet repository running release-please wires into its required ci-green aggregate. The check identifies a release pull request by its release-please head branch name, never by HEAD's commit subject. It judges the patch a merge would land: the diff from the merge base of the base tip and the head to the head, over the whole tree. In that patch, a changed line passes only when it pairs with an opposite-side line that is identical after substituting the repository's own release version, the changelog may only gain lines, and the manifest may change only its version value. Anything else fails the check, naming each offending file and line, and the remedy is to close the release pull request and delete its branch so release-please regenerates it from current master; the release pull request's bytes are never edited. A diff against the CURRENT base tip does not fail the check, because a base that moved on shows up there as reversed hunks the merge does not land. Add six scenarios to scenarios.md. Work item livespec-dev-tooling-apluqn carries the implementation.

### Motivation

Measured 2026-11-13 on livespec-overseer (work item livespec-dev-tooling-apluqn, priority 1, stop-the-line). livespec-overseer#2971 bumped the livespec-dev-tooling pin to v1.202.0 and merged as 0c4ff835 at 01:45:12Z. release-please run 43347190067 had read pyproject.toml at 01:45:13Z from an earlier snapshot, and at 01:45:28Z it committed release head be920557 onto parent 0c4ff835. release-please writes WHOLE files through the GitHub API, so be920557's pyproject.toml and uv.lock equal the pre-#2971 copies apart from the version lines, and the release pull request's own diff reverted the pin to v1.200.0. The next run logged that livespec-overseer#2972 "remained the same", because release-please compares only a release pull request's title and body. The factory App armed rebase auto-merge, which replays the head commit's own diff, and the revert landed on master as 65dce2d8 and turned it red. The same shape landed once before, as 356b68bd on 2026-08-21. No pre-merge check saw it. livespec-overseer's only guard keys on HEAD's subject (`chore(master): release X.Y.Z`), and on a pull_request checkout HEAD is the merge commit GitHub synthesizes, so the guard is a no-op on every release pull request and fires only after the merge. The fleet sweep (rule G, recorded on apluqn) found the race possible in all nine repositories that run release-please, with no pre-merge release-scope check in any of them. legacy-coordinator-agent ruled option (a) on 2026-11-13: file this proposal. Its interim ruling disarms auto-merge on every release-please pull request until this check is on that repository's master, and a seat-run guard applies exactly the rule proposed here. That rule was corrected at 03:28Z: the merge-base diff alone decides, and the base-tip diff is only a warning, after a base-tip-diff block falsely closed livespec-console-beads-fabro#1319, whose base had four newer commits that a rebase merge preserves. Measured basis for the line rule: across all 2,343 merged release commits in the nine fleet repositories it flags exactly the two overseer clobbers, and it passes livespec-dev-tooling cca3bc008e, a benign version-only change that a manifest-substitution form would have refused. Placement: no ratified clause covers a pre-merge release-pull-request scope rule. The spec-change tier record on apluqn names `## Versioning` as the generalization target, and that section already says release-please is the only writer of the version fields, so the rule extends it there and adds no H2 beside it. The rule is a wire contract that every consumer repository's CI inherits through a pinned Action, so it belongs in contracts.md under the §Boundary litmus. apluqn's Definition of Done carries two bullets this proposal deliberately does not ratify: a failure on the net change against the current base tip (the rule the 03:28Z correction retracted), and a file-set rule read from release-please-config.json, which the whole-tree line rule already covers. apluqn's Definition of Done owes a rewrite to the ratified text once the revise lands. The revise MUST co-edit tests/heading-coverage.json for the six new scenario headings: spec-first TODO rows naming the integration tier and owned by livespec-dev-tooling-apluqn, registered in the heading-coverage debt register.

### Proposed Changes

### SPECIFICATION/contracts.md §"Versioning"

Append these paragraphs and this list at the end of the section, after the paragraph that ends "`release-please` is the only tool that writes to these.":

A release-please pull request MUST land only release-owned changes. release-please writes each file it updates WHOLE, from a read of the default branch that can predate the base it commits onto, and its later runs do not regenerate a release pull request whose title and body are unchanged. So a pull request that merges in that window can have its change to a release-written file silently reverted by the release pull request's own diff, which a rebase merge replays. This library MUST ship a release-PR scope check as a check module with a console entry point and a composite Action that installs the pinned build and runs it. Every fleet repository that runs release-please MUST run that check on every pull request, as a job its required `ci-green` aggregate needs. The check MUST meet all of the following:
- It MUST identify a release pull request by its head branch name beginning `release-please--`, and MUST NOT identify one by the subject of `HEAD`. A pull_request checkout's `HEAD` is the merge commit the forge synthesizes, so the check MUST reach the same verdict on that merge commit as on the release head itself.
- On a pull request whose head branch is not a release-please branch, it MUST exit 0 and report that it does not apply.
- It MUST judge the release patch, which is the diff from the merge base of the current base tip and the head, to the head, over the whole tree with rename detection off. For a single-commit release pull request that merge base is the head's own parent, so the patch is exactly what a rebase merge replays.
- In the release patch, a removed or added line MUST pass only when it pairs with an opposite-side line that is identical after substituting the repository's own release version, the old version read from `.release-please-manifest.json` at the merge base and the new one from it at the head. The changelog (`CHANGELOG.md`) MAY only gain lines. The manifest MAY change only its version value.
- Any other change in the release patch MUST fail the check: any other changed line, a binary change, or a rename. The failure MUST name each offending file and line.
- The net diff of the current base tip against the head MUST NOT fail the check. A base that moved on after release-please cut the head shows up there as reversed hunks that the merge does not land. The check SHOULD report the base-tip hunks on pin-bearing files (`pyproject.toml`, `uv.lock`, `package.json`, `Cargo.toml`, `plugin.json`) as a warning.
- When the check fails, its message MUST tell the operator to close the release pull request and delete its branch, so that the next release-please run opens a fresh one from the current default branch. Nothing MAY edit a release pull request's bytes to make it pass.

When the check fails on a release-please pull request, the repository's release automation MUST close that pull request and delete its branch, and the next release-please run MUST open the replacement release pull request from the current default branch. A consumer that pins this check MUST pin it at a released tag of this library, by the same pin ref the pin-bump automation rewrites.

### SPECIFICATION/scenarios.md

Add these six scenarios, in this order, directly after "## Scenario: a stale pin whose bump PR never opened escalates once the release ages past the settle window":

## Scenario: a release pull request whose patch reverts a pin fails the release-PR scope check

Given a replay of livespec-overseer release commit 65dce2d8 on a release-please head branch, whose own patch moves the livespec-dev-tooling pin in `pyproject.toml` and `uv.lock` from v1.202.0 to v1.200.0 beside the 5.55.1 to 5.55.2 version lines

When the release-PR scope check runs on that pull request

Then it MUST fail

And it MUST name each `pyproject.toml` and `uv.lock` line that moves the pin

And its message MUST tell the operator to close the release pull request and delete its branch

## Scenario: a release pull request that changes only release-owned lines passes the release-PR scope check

Given a release-please pull request whose patch changes only lines that differ by the repository's own release version, the manifest's version value, and lines added to `CHANGELOG.md`

When the release-PR scope check runs on that pull request

Then it MUST exit 0

## Scenario: the release-PR scope check reaches the same verdict on the synthesized merge commit

Given a release-please pull request whose patch reverts a pin

And a pull_request checkout whose `HEAD` is the merge commit the forge synthesized, with a subject that is not a release subject

When the release-PR scope check runs on that checkout

Then it MUST identify the pull request as a release pull request by its `release-please--` head branch name

And it MUST fail as it fails on the release head itself

## Scenario: the release-PR scope check does not apply to a pull request that is not a release pull request

Given a pull request whose head branch does not begin `release-please--`

When the release-PR scope check runs on that pull request

Then it MUST exit 0

And it MUST report that it does not apply

## Scenario: a release pull request whose base moved on after it was cut is warned and not failed

Given a release-please pull request whose own patch changes only release-owned lines

And a newer commit on the base branch that changed the livespec-dev-tooling pin in `pyproject.toml` after release-please cut the head

When the release-PR scope check runs on that pull request

Then it MUST exit 0

And it SHOULD report the base-tip `pyproject.toml` hunk as a warning

## Scenario: a failed release pull request is closed and replaced from the current default branch

Given a release-please pull request on which the release-PR scope check failed

When the repository's release automation acts on that failure

Then it MUST close the pull request and delete its branch

And the next release-please run MUST open a replacement release pull request built from the current default branch

