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

ADDS one paragraph, "Workflow edits are admitted only by a per-change exemption.", under "## Hooks and CI". It states the workflow-edit guard this repository ships in its worktree-discipline pack (`check-no-workflow-edits.sh`), which the live specification does not yet state. A workflow change is admitted from an exemption file that the change itself authors, in a directory of per-change files, so two changes that each add their own file do not textually conflict. During a transition the guard also reads the legacy single root file. Either form counts only when this change authored it, and an exemption inherited from the base never admits. A workflow change with no exemption authored in this change is still refused, naming each workflow path. The declaration's keys, its two label tiers, the fail-closed ledger read and the absence of any environment escape are stated unchanged. ADDS four scenarios after "## Scenario: a workflow GitHub cannot parse is refused at every gate".

### Motivation

Work item livespec-dev-tooling-oim422 was filed by the expedited-incident-response-flag plan seat at legacy-coordinator-agent's direction on 2026-11-13. It is a child of ci-runtime-and-cost (livespec-dev-tooling-ib3oe3). The guard admits a change under `.github/workflows/` only when the repository's single root file `.livespec-workflow-edit-exemption` names it, and only when this change authored that file. Every pull request that edits a workflow therefore rewrites that one file, and any two such pull requests in flight conflict on it.

Measured 2026-11-13: livespec-dev-tooling#4462 (bqnzcm.4 slice 2a) passed CI on head 85d16269a. pwabtl's merge 838a4e545 then rewrote the exemption file, and #4462's workflow commit, which replaces the same file, could no longer rebase-merge. The slice had to be re-cut and its workflow commit re-authored. That needed a fresh byte diff by legacy-coordinator-agent before it could merge.

The coordinator held oim422 at spec-change tier (linked topic every-workflow-editing-pr-rewrites, generalization target "## Expedited incident execution"). The live SPECIFICATION/*.md states no workflow-edit guard and no exemption layout. The guard's rules appear only under history/ and in the shipped script's header comment. The nearest live text, "Workflow reductions require explicit maintainer authority, not a logically additive exemption" in contracts.md "## Expedited incident execution", says nothing about how an exemption is stored. This proposal places the rule under "## Hooks and CI", the section that already governs the worktree-discipline pack's installation and the "Workflow files must parse." gate.

Fleet scope:

- Seven fleet repositories track `.livespec-workflow-edit-exemption`: livespec, livespec-orchestrator-beads-fabro, livespec-overseer, livespec-driver-claude, livespec-driver-codex, livespec-runtime and livespec-console-beads-fabro. livespec-dev-tooling, which ships the guard, tracks it too.
- None of the seven tracks the guard. Each receives it only through the released worktree pack, which is installed into its gitignored `dev-tooling/`.
- Adoption is therefore one livespec-dev-tooling release plus each consumer's ordinary pin bump, with no per-repository code. dolt-server carries neither file.

The route ruled by legacy-coordinator-agent is factory implementation of oim422 once this ratifies, with the transition rule below as its rider.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Hooks and CI", INSERT the following paragraph immediately after the paragraph that begins "**Workflow files must parse.**" and before the paragraph that begins "**The coverage handoff is tested, and workflow commits run the tests that read ci.yml.**":

**Workflow edits are admitted only by a per-change exemption.** The worktree-discipline pack this repository ships carries one workflow-edit guard, `check-no-workflow-edits.sh`. It is an authorship control at the agent boundary: it runs in a consumer's local check aggregate and in the Dispatcher's janitor gate, and it judges nothing when `GITHUB_ACTIONS` is set. A change touches workflows when any path under `.github/workflows/` differs between the change and its base, counting committed, staged, unstaged and untracked paths.

The guard MUST admit such a change only under an exemption that this change authored. An exemption is a tracked file that this change adds or modifies and that is present in its tree. One file per change goes in the directory `.livespec-workflow-edit-exemptions/`, under any file name, so two changes that add differently named files never conflict on them. During the transition the guard MUST also accept the legacy single root file `.livespec-workflow-edit-exemption` under the same authored-in-this-change rule. An exemption file that exists in the base and that this change did not modify MUST NOT admit, in either form. That includes a file an in-progress merge brings in from the base.

An exemption MUST carry exactly one `work_item=<ledger-id>` line and exactly one non-empty `reason=` line. It MAY carry at most one `change=additive` line and at most one `ci_runtime=` line, which claim the additive tier. A change that authors more than one exemption, across both forms, cannot be evaluated.

An additive claim is checked against the change's workflow diff; any deleted line, deleted file or mode change refuses it. When the repository has a ledger, the named work item MUST carry a label that admits the tier:

- The additive tier accepts `approval:workflow-edit-additive` or `approval:workflow-edit`.
- Every other workflow change accepts `approval:workflow-edit` only.

A repository with no ledger accepts a valid exemption alone.

The guard MUST exit:

- `1` when a change touches workflows and no admitting exemption was authored in it, naming each workflow path the change touches;
- `2` when the exemption is malformed, when more than one is authored, or when the ledger cannot be read, naming the cause;
- `0` otherwise.

No environment variable changes the verdict.

The transition ends only by a later revision that retires the legacy root file. That revision MUST NOT land before every fleet repository that tracks the root file pins a livespec-dev-tooling release whose guard reads the directory.

In SPECIFICATION/scenarios.md, insert the following four scenarios immediately after "## Scenario: a workflow GitHub cannot parse is refused at every gate" and before "## Scenario: a new runner release opens one bump across every scale set":

## Scenario: two workflow changes that each add their own exemption file merge in either order

Given two changes from the same base that each edit a file under `.github/workflows/`
And each adds its own differently named exemption file under `.livespec-workflow-edit-exemptions/`, naming a work item that carries the label its tier requires

When either change is merged onto the base first and the other is then merged onto the result

Then neither merge MUST conflict on an exemption file
And the workflow-edit guard MUST admit each change on its own branch

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

The revise that accepts this MUST add a tests/heading-coverage.json row for each of the four new scenario headings, owned by livespec-dev-tooling-oim422, at the unit tier (the guard's fixture-repository harness in tests/livespec_dev_tooling/worktree_pack/test_check_no_workflow_edits.py), and register those rows in the debt register. "## Hooks and CI" keeps its existing row.
