---
topic: pre-push-accepts-a-same-tree-delegated-pre-commit-pass
author: claude:implement-test-performance
created_at: 2026-11-10T23:25:25Z
---

## Proposal: The pre-push gate accepts a same-tree delegated pre-commit pass as the full-suite verdict

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a **Same-tree delegated pre-commit verdict** bullet to §"Delegated pre-push gate" and an **Evidence for the pre-push gate** bullet to §"Delegated pre-commit aggregate". In a repository that sets both `delegated_gate` and `delegated_pre_commit`, a passing DELEGATED (cluster gate Job) full pre-commit aggregate on tree T qualifies when its verdict arrived on a clean working tree with `git write-tree` unchanged, and the pushed HEAD tree is T. The pre-push gate then accepts that run as the full-suite verdict for T and submits no gate Job for the members it covered. It still runs, on the pushing host, every member the pre-commit Job did not run (such as `check-red-green-replay`, which a Green-amend pre-commit skips), every world-reading member, and every authorization-reading member. A LOCAL pre-commit pass never qualifies. This removes a second full-suite run per hand-landed Green amend in every consumer that delegates both gates.

### Motivation

Coordinator ruling, 2026-11-10 about 23:30Z. livespec-orchestrator-beads-fabro runs its whole suite twice per hand-landed Green amend. It runs once as the pre-commit full aggregate (`dev-tooling/just-check-pre-commit.sh:87-98` in that repository) and again at pre-push, because its `dev-tooling/green-token-scope.sh:83` rejects any token carrying `pre_commit_aggregate`. The comment at :19-20 calling such evidence 'never a gate pass' is a code comment, not a ruling. On a gmktec orchestrator gate, `check-per-file-coverage` takes 2,222 s, of which pytest is 2,174 s (14,969 tests at 4 workers). The second run therefore costs about 37 minutes per Green commit and proves nothing the delegated pre-commit Job did not already prove for the same tree. The ruled conditions match the ratified local-aggregate reuse conditions (aggregate exit 0, no unstaged change, no untracked non-ignored file, write-tree unchanged across the run), plus the pushed-HEAD-tree match the green token already uses. The local exclusion is part of the ruling: a host-local pre-commit pass never qualifies. That also narrows this repository's own shipped `green_token check`, which today honours a token written by a LOCAL pre-commit aggregate. Members outside the pre-commit run's scope keep running, so the saving never drops a member from the push.

### Proposed Changes

In `SPECIFICATION/contracts.md`, section "## Delegated pre-commit aggregate", add this bullet after the "**Verdict.**" bullet:

- **Evidence for the pre-push gate.** When a delegated pre-commit run returns the gate Job's own green verdict for the FULL aggregate of the staged tree (not the doc-only subset and not the Red-leg subset), the hook MUST record pre-commit evidence for that tree only when every one of these holds at the moment the verdict arrives: the Job's reported tree hash equals the staged tree hash; the working tree has no unstaged change; no untracked, non-ignored file exists; and `git write-tree` names the same tree it named when the hook submitted the Job. The evidence MUST name the gate Job, the tree hash, and every member of the aggregate that the Job did NOT run for that staged tree (for example `check-red-green-replay`, which the pre-commit aggregate of a Green amend skips). In every other case the hook MUST record no such evidence. Evidence recorded after a LOCAL aggregate, including the local run that follows an absent verdict under the **Absent verdict** bullet, names no gate Job and MUST NOT be written in this form. §"Delegated pre-push gate" **Same-tree delegated pre-commit verdict** is the only reader of this evidence at push time.

In `SPECIFICATION/contracts.md`, section "## Delegated pre-push gate", add this bullet after the "**Token memoization.**" bullet:

- **Same-tree delegated pre-commit verdict.** In a consuming repository whose `[tool.livespec_dev_tooling]` table sets both `delegated_gate = true` and `delegated_pre_commit = true`, the pre-push gate MUST accept a qualifying delegated pre-commit run as the full-suite verdict for the tree it judged. A run qualifies only when §"Delegated pre-commit aggregate" **Evidence for the pre-push gate** recorded evidence for it, which means it ran as a gate Job, ran the full aggregate, returned the Job's own green verdict for the staged tree, and left a clean working tree whose `git write-tree` was unchanged across the run, AND, at push time, the pushing worktree is clean and its `HEAD` tree is the tree that evidence names. When a run qualifies, the pre-push gate MUST NOT submit a gate Job and MUST NOT run the local fall-through for the members that run covered. It MUST still run, on the pushing host against the same tree: every member of its own check set that the evidence names as not run by the pre-commit Job; every world-reading member of its check set, as **Token memoization** requires, whether or not the pre-commit Job ran it; and every member that declares it reads an authorization held outside the tree, as **What the delegated gate runs** places such members. It MUST refuse the push, naming the member, when any member it runs fails. It MUST print the gate Job's name and the tree hash whose pre-commit verdict it accepted, the name of each member it ran, and the number of members it skipped because that verdict covered them, so that a push gated this way never reads as fully gated by a pre-push Job. A pre-commit aggregate that ran on the committing host MUST NOT qualify, even when it passed on the same tree. That covers a host that cannot read the gates kubeconfig, a repository whose pre-commit delegation is off, and the local run that follows an absent delegated verdict. The same-tree evidence the **Local-aggregate evidence entry point** of §"Suite-green replay leg" writes therefore MUST NOT stand in for the pre-push gate, while it still serves that section's **Same-tree reuse** bullet. When no qualifying run exists for the `HEAD` tree, the pre-push gate MUST gate exactly as the other bullets of this section require. A push that accepts a qualifying run makes no delegated gate run, so it emits no outcome event under **Telemetry**. For a push that the **Seed and preserve refs** bullet covers, that bullet takes precedence over this one. Fleet scope: this bullet binds the pre-push gate of every consuming repository that sets both keys, including a repository whose pre-push gate reads the green token through a script of its own. Such a gate MUST NOT refuse a qualifying run's evidence because it carries pre-commit provenance. This bullet is spec-first. As of filing, this repository's `green_token check` honours any token whose tree matches, including evidence that a LOCAL pre-commit aggregate wrote, and it records no member set. livespec-orchestrator-beads-fabro's `dev-tooling/green-token-scope.sh` refuses every token that carries `pre_commit_aggregate`. Neither gate tells a delegated run from a local one, and neither runs the members a pre-commit run skipped. The revise that ratifies this bullet MUST name the work item that owns the change.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario: a push of a tree whose delegated pre-commit aggregate passed submits no gate Job and runs only the members that run did not cover

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and `delegated_pre_commit = true`

And a Green-amend commit whose pre-commit hook ran the full aggregate as gate Job `J` on staged tree `T`, and `J` skipped `check-red-green-replay` and reported a green verdict for `T`

And when that verdict arrived the working tree had no unstaged change and no untracked, non-ignored file, and `git write-tree` still named `T`

And the pushing worktree is clean and its `HEAD` tree is `T`

When the pre-push gate runs for a push of that commit to an ordinary branch

Then it MUST NOT submit a gate Job and MUST NOT run the local `just check` fall-through

And it MUST run `check-red-green-replay` and every world-reading member of its check set on the pushing host against `T`

And it MUST NOT run any tree-pure member that `J` ran

And it MUST print `J`, `T`, the name of each member it ran, and the number of members it skipped

And the push MUST complete when every member it ran passes

## Scenario: a pre-commit aggregate that ran on the committing host does not stand in for the pre-push gate

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and `delegated_pre_commit = true`

And a commit whose pre-commit aggregate ran on the committing host and passed on tree `T`, because the delegated run reached no verdict and the hook gated locally

And the pushing worktree is clean, its `HEAD` tree is `T`, and no green `just check` has recorded a green token for `T`

When the pre-push gate runs on a host eligible under **Host eligibility** for a push of that commit to an ordinary branch

Then it MUST submit a gate Job for `T` exactly as it does for a tree with no pre-commit evidence

And it MUST NOT print that it accepted a pre-commit verdict

## Scenario: a delegated pre-commit pass on a dirty or changed tree does not stand in for the pre-push gate

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and `delegated_pre_commit = true`

And a commit whose pre-commit hook ran the full aggregate as gate Job `J` on staged tree `T`, and `J` reported a green verdict for `T`

And when that verdict arrived the working tree had an unstaged change or an untracked, non-ignored file, or `git write-tree` named a tree other than `T`

When the pre-commit hook finishes

Then it MUST record no pre-commit evidence for `J`

And a later pre-push gate for a clean worktree whose `HEAD` tree is `T` MUST submit a gate Job for `T` on a host eligible under **Host eligibility**

## Scenario: a member outside the delegated pre-commit run's scope still runs at pre-push and refuses the push when it fails

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and `delegated_pre_commit = true`

And recorded evidence that gate Job `J` passed the full pre-commit aggregate on tree `T` and did not run `check-red-green-replay`

And the pushing worktree is clean and its `HEAD` tree is `T`

And `check-red-green-replay` fails for the pushed range

When the pre-push gate runs for a push of that commit to an ordinary branch

Then it MUST run `check-red-green-replay` on the pushing host

And it MUST refuse the push, naming `check-red-green-replay`

