---
topic: every-workflow-editing-pr-rewrites
author: claude-opus-5-5 (ci-runtime-and-cost)
created_at: 2026-11-13T09:00:11Z
---

## Proposal: The workflow-edit guard admits a workflow change from a per-change exemption file, so two in-flight workflow changes never conflict on their exemptions

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

ADDS one paragraph, "Workflow edits are admitted only by a per-change exemption.", under "## Hooks and CI". It states the workflow-edit guard this repository ships in its worktree-discipline pack (`check-no-workflow-edits.sh`), which the live specification does not yet state.

- A workflow change is admitted from an exemption file that the change itself authors, in a directory of per-change files. Two changes that each add their own file therefore do not textually conflict.
- "Authored" is defined by content against the base. A mode-only change, a rename or copy of a base exemption, and a deletion never author one.
- During a transition the guard also reads the legacy single root file, under the same authored-in-this-change rule. The ci-runtime-and-cost plan seat owns the revision that ends the transition, and a filed item checks each repository's pin.
- A workflow change with no exemption authored in it is still refused, naming each workflow path.
- The declaration's keys, its two label tiers, the false-additive and missing-label refusals, the fail-closed ledger read and the absence of any environment escape are stated as the guard implements them.

ADDS nine scenarios after "## Scenario: a workflow GitHub cannot parse is refused at every gate".

### Motivation

Work item livespec-dev-tooling-oim422 was filed by the expedited-incident-response-flag plan seat at legacy-coordinator-agent's direction on 2026-11-13. It is a child of ci-runtime-and-cost (livespec-dev-tooling-ib3oe3). The guard admits a change under `.github/workflows/` only when the repository's single root file `.livespec-workflow-edit-exemption` names it, and only when this change authored that file. Every pull request that edits a workflow therefore rewrites that one file, and any two such pull requests in flight conflict on it.

Measured 2026-11-13: livespec-dev-tooling#4462 (bqnzcm.4 slice 2a) passed CI on head 85d16269a. pwabtl's merge 838a4e545 then rewrote the exemption file, and #4462's workflow commit, which replaces the same file, could no longer rebase-merge. The slice had to be re-cut and its workflow commit re-authored. That needed a fresh byte diff by legacy-coordinator-agent before it could merge.

The coordinator held oim422 at spec-change tier (linked topic every-workflow-editing-pr-rewrites, generalization target "## Expedited incident execution"). The live SPECIFICATION/*.md states no workflow-edit guard and no exemption layout. The guard's rules appear only under history/ and in the shipped script's header comment. The nearest live text, "Workflow reductions require explicit maintainer authority, not a logically additive exemption" in contracts.md "## Expedited incident execution", says nothing about how an exemption is stored. This proposal places the rule under "## Hooks and CI", the section that already governs the worktree-discipline pack's installation and the "Workflow files must parse." gate.

The paragraph's tier, exit-code and malformed-declaration rules restate what `livespec_dev_tooling/worktree_pack/check-no-workflow-edits.sh` already does:

- A change= value other than `additive` is refused as malformed, and so is a work_item that is not one ledger id token.
- The additive tier requires `ci_runtime=no-significant-increase`.
- A false additive claim exits 1, naming the offending lines.
- A valid exemption whose work item lacks the tier's label exits 1.

The new behaviour is limited to the per-change directory, the content-based definition of "authored" (which also closes the mode-only, rename, copy and deletion paths for the root file), the one-exemption-per-change rule, and the transition.

Fleet scope, read on each repository's origin/master on 2026-11-13:

- Nine consumers track the root file `.livespec-workflow-edit-exemption`: livespec, livespec-orchestrator-beads-fabro, livespec-orchestrator-git-jsonl, livespec-overseer, livespec-driver-claude, livespec-driver-codex, livespec-driver-pi, livespec-runtime and livespec-console-beads-fabro.
- livespec-dev-tooling, which ships the guard, also tracks the root file.
- dolt-server, hetzner-xubuntu-info and livespec-tdd-proof carry the installed guard and a `check-no-workflow-edits` recipe but no root file.
- No consumer tracks the guard itself. Each receives it only through the released worktree pack, installed into its gitignored `dev-tooling/`. Adoption is therefore one livespec-dev-tooling release plus each consumer's ordinary pin bump, with no per-repository code.

The route ruled by legacy-coordinator-agent is factory implementation of oim422 once this ratifies, with the transition rule below as its rider.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Hooks and CI", INSERT the following paragraph immediately after the paragraph that begins "**Workflow files must parse.**" and before the paragraph that begins "**The coverage handoff is tested, and workflow commits run the tests that read ci.yml.**":

**Workflow edits are admitted only by a per-change exemption.** The worktree-discipline pack this repository ships carries one workflow-edit guard, `check-no-workflow-edits.sh`. It is an authorship control at the agent boundary: it runs in a consumer's local check aggregate and in the Dispatcher's janitor gate, and it judges nothing when `GITHUB_ACTIONS` is set. A change touches workflows when any path under `.github/workflows/` differs between the change and its base, counting committed, staged, unstaged and untracked paths.

The guard MUST admit such a change only under an exemption that this change authored, and one exemption covers every workflow path the change touches. Exemptions live one file per change in the directory `.livespec-workflow-edit-exemptions/`, under any file name, so two changes that add differently named files never conflict on them. Merged exemption files accumulate in the directory and are not pruned: each stays the record of the change it admitted and never admits a later one. During the transition the guard MUST also accept the legacy single root file `.livespec-workflow-edit-exemption` under the same rule.

A change authors an exemption file when that file is tracked and present in the change's tree, and EITHER the base has no file at that path OR the file's content differs from the base's content at that path, counting committed, staged and unstaged content. None of the following authors an exemption:

- a change to the file's mode alone;
- a rename or a copy whose resulting content matches an exemption file present in the base;
- a deletion.

An exemption present in the base that this change did not author MUST NOT admit, in either form. That includes a file an in-progress merge brings in from the base.

An exemption MUST carry exactly one `work_item=` line whose value is one ledger id token, and exactly one non-empty `reason=` line. It MAY carry at most one `change=` line, whose only valid value is `additive`, and at most one `ci_runtime=` line. A change is in the ADDITIVE tier only when its exemption carries both `change=additive` and `ci_runtime=no-significant-increase`. An exemption carrying `change=additive` with any other `ci_runtime=` value, or none, is in the MAINTAINER tier, as is every other change.

A `change=additive` claim is checked against the change's committed, staged and unstaged workflow diff. Any deleted line (a modification is a deletion plus an addition), any deleted file or any mode change makes the claim false, whatever label the work item carries. When the repository has a ledger, the named work item MUST carry a label that admits the tier:

- The additive tier accepts `approval:workflow-edit-additive` or `approval:workflow-edit`.
- The maintainer tier accepts `approval:workflow-edit` only.

A repository with no ledger accepts a valid exemption alone.

The guard MUST exit `1`, naming each workflow path the change touches, in three cases:

- no admitting exemption was authored in the change;
- the exemption's `change=additive` claim is false, in which case it also names each offending line;
- a valid exemption names a work item that carries no label admitting its tier, in which case it also names the work item and the label it needs.

The guard MUST exit `2`, naming the cause, when the change cannot be evaluated:

- more than one exemption is authored in the change, across both forms;
- a `work_item=` or `reason=` line is missing or repeated;
- the `work_item=` value is not one ledger id token;
- the `reason=` value is empty;
- a `change=` or `ci_runtime=` line is repeated;
- the `change=` value is anything other than `additive`;
- the ledger cannot be read.

The guard MUST exit `0` otherwise. No environment variable changes the verdict.

The transition ends only by a later revision that retires the legacy root file. The ci-runtime-and-cost plan seat, which owns livespec-dev-tooling-oim422, owns that revision. That revision MUST name a filed work item that lists each fleet repository that tracks the root file together with the livespec-dev-tooling release it pins, and checks that each pins a release whose guard reads the directory. The revision MUST NOT land before that check passes for every listed repository.

In SPECIFICATION/scenarios.md, insert the following nine scenarios immediately after "## Scenario: a workflow GitHub cannot parse is refused at every gate" and before "## Scenario: a new runner release opens one bump across every scale set":

## Scenario: two workflow changes that each add their own exemption file merge in either order

Given two changes from the same base that each edit a file under `.github/workflows/`
And each adds its own differently named exemption file under `.livespec-workflow-edit-exemptions/`, naming a work item that carries the label its tier requires

When either change is merged onto the base first and the other is then merged onto the result

Then neither merge MUST conflict on an exemption file
And the workflow-edit guard MUST exit 0 on each change's own branch

## Scenario: a workflow change with no exemption authored in it is refused by name

Given a change that edits `.github/workflows/ci.yml`
And the change authors no exemption file in either form

When the workflow-edit guard runs

Then it MUST exit 1
And its output MUST name `.github/workflows/ci.yml`

## Scenario: an exemption inherited from the base does not admit a workflow change

Given a base whose `.livespec-workflow-edit-exemptions/` directory and root `.livespec-workflow-edit-exemption` file each hold a well-formed exemption naming a labelled work item
And a change from that base that edits a file under `.github/workflows/` and adds, modifies and stages no exemption file

When the workflow-edit guard runs

Then it MUST exit 1
And its output MUST name each workflow path the change touches

## Scenario: the legacy root exemption file authored in the change still admits during the transition

Given a change that edits a file under `.github/workflows/`
And the change modifies the root `.livespec-workflow-edit-exemption` file to a well-formed exemption naming a work item that carries the label its tier requires
And the change authors no file under `.livespec-workflow-edit-exemptions/`

When the workflow-edit guard runs

Then it MUST exit 0

## Scenario: changing only an exemption file's mode does not author it

Given a base whose root `.livespec-workflow-edit-exemption` file holds a well-formed exemption naming a labelled work item
And a change from that base that edits a file under `.github/workflows/` and changes only that exemption file's mode

When the workflow-edit guard runs

Then it MUST exit 1
And its output MUST name each workflow path the change touches

## Scenario: renaming a base exemption file does not author it

Given a base whose `.livespec-workflow-edit-exemptions/` directory holds a well-formed exemption file naming a labelled work item
And a change from that base that edits a file under `.github/workflows/` and renames that exemption file to a new name, leaving its content unchanged

When the workflow-edit guard runs

Then it MUST exit 1
And its output MUST name each workflow path the change touches

## Scenario: copying a base exemption file does not author it

Given a base whose `.livespec-workflow-edit-exemptions/` directory holds a well-formed exemption file naming a labelled work item
And a change from that base that edits a file under `.github/workflows/` and adds a copy of that exemption file under a new name with identical content

When the workflow-edit guard runs

Then it MUST exit 1
And its output MUST name each workflow path the change touches

## Scenario: deleting a base exemption file does not author it

Given a base whose `.livespec-workflow-edit-exemptions/` directory holds a well-formed exemption file naming a labelled work item
And a change from that base that edits a file under `.github/workflows/`, deletes that exemption file and authors no other exemption

When the workflow-edit guard runs

Then it MUST exit 1
And its output MUST name each workflow path the change touches

## Scenario: a change that authors two exemptions cannot be evaluated

Given a change that edits a file under `.github/workflows/`
And the change authors two well-formed exemption files, in either form or both

When the workflow-edit guard runs

Then it MUST exit 2
And its output MUST name each authored exemption file

The revise that accepts this MUST add a tests/heading-coverage.json row for each of the nine new scenario headings at the CONSUMER tier, the tier `scenario_tiers = ["tests.consumer"]` in pyproject.toml declares, so each row's test resolves under `tests.consumer`. Each row MUST carry the literal key `"work_item": "livespec-dev-tooling-oim422"` and a reason naming the consumer tier and that item. The revise MUST regenerate tests/heading-coverage-debt.json with `just generate-heading-coverage-debt-register` and stage it in the same commit. "## Hooks and CI" keeps its existing row.
