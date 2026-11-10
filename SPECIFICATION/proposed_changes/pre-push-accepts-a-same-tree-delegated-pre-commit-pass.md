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

Add a **Same-tree delegated pre-commit verdict** bullet to §"Delegated pre-push gate", an **Evidence for the pre-push gate** bullet to §"Delegated pre-commit aggregate", and one sentence to the ratified **Explicit local route** bullet. The rule applies in a repository that sets both `delegated_gate` and `delegated_pre_commit`. A passing DELEGATED (cluster gate Job) full pre-commit aggregate on tree T qualifies when four things hold: the Job reports the members it ran and passed; its verdict arrived on a clean working tree; `git write-tree` was unchanged across the run; and the pushed HEAD tree is T. The pre-push gate then accepts that run as the full-suite verdict for T and submits no gate Job for the members it covered. It still runs, on the pushing host, every member of its own check set that the Job did not report as run and passed (such as `check-red-green-replay`, which a Green-amend pre-commit skips), every world-reading member, and every authorization-reading member. A LOCAL pre-commit pass never qualifies, and the pre-commit hook's local `just check` no longer writes the green token. This removes a second full-suite run per hand-landed Green amend in every consumer that delegates both gates.

### Motivation

Coordinator ruling, 2026-11-10 about 23:30Z. livespec-orchestrator-beads-fabro runs its whole suite twice per hand-landed Green amend. It runs once as the pre-commit full aggregate (`dev-tooling/just-check-pre-commit.sh:87-98` in that repository) and again at pre-push, because its `dev-tooling/green-token-scope.sh:83` rejects any token carrying `pre_commit_aggregate`. The comment at :19-20 calling such evidence 'never a gate pass' is a code comment, not a ruling. On a gmktec orchestrator gate, `check-per-file-coverage` takes 2,222 s, of which pytest is 2,174 s (14,969 tests at 4 workers). The second run therefore costs about 37 minutes per Green commit and proves nothing the delegated pre-commit Job did not already prove for the same tree. The ruled conditions match the ratified local-aggregate reuse conditions (aggregate exit 0, no unstaged change, no untracked non-ignored file, write-tree unchanged across the run), plus the pushed-HEAD-tree match the green token already uses. The local exclusion is part of the ruling: a host-local pre-commit pass never qualifies. That also narrows this repository's own shipped `green_token check`, which today honours a token written by a LOCAL pre-commit aggregate. Members outside the pre-commit run's scope keep running, so the saving never drops a member from the push. The post-step doctor LLM phase (2026-11-10) confirmed two points in the live code. First, `scripts/just/check.sh:231` writes the green token after the pre-commit hook's local `just hook_gate=1 check`. Second, only the Job knows which members it skipped, because the consumer's own recipe decides that inside the Job. So the evidence names the members the Job itself reports as run and passed, and the pre-commit hook's local aggregate stops writing the token.

### Proposed Changes

In `SPECIFICATION/contracts.md`, section "## Delegated pre-commit aggregate", add this bullet after the "**Verdict.**" bullet:

- **Evidence for the pre-push gate.** The gate Job MUST report, in one structured line of its output, the name of every aggregate member it ran for the staged tree and the verdict of each. When a delegated pre-commit run returns the gate Job's own green verdict for the FULL aggregate of the staged tree, the hook MUST record pre-push evidence for that tree. A FULL aggregate is not the doc-only subset and not the Red-leg subset. The hook MUST do so only when every one of these holds at the moment the verdict arrives:
  - the Job's reported tree hash equals the staged tree hash;
  - the Job reported its member list;
  - the working tree has no unstaged change;
  - no untracked, non-ignored file exists;
  - `git write-tree` names the same tree it named when the hook submitted the Job.

  The pre-push evidence MUST carry the gate Job's name in a field of its own, the tree hash, and the names of the members the Job reported as run and passed. In every other case the hook MUST record no pre-push evidence. That includes a Job that reported no member list, and the doc-only and Red-leg subsets. Evidence recorded after a LOCAL aggregate MUST NOT carry a gate Job name. That includes the local run that follows an absent verdict under the **Absent verdict** bullet. This bullet does not narrow the evidence that §"Suite-green replay leg" **Same-tree reuse** consumes: a delegated green verdict MAY still record same-tree evidence for the suite-green leg when the host's working tree was not clean, because the Job judged a clean checkout of the staged tree. §"Delegated pre-push gate" **Same-tree delegated pre-commit verdict** is the only reader of pre-push evidence.

In `SPECIFICATION/contracts.md`, section "## Delegated pre-push gate", append this sentence to the "**Explicit local route.**" bullet:

A `just check` that the pre-commit hook runs as its LOCAL aggregate is not this route. It MUST NOT write the green token, because a local pre-commit pass never stands in for the pre-push gate (**Same-tree delegated pre-commit verdict**).

In `SPECIFICATION/contracts.md`, section "## Delegated pre-push gate", add this bullet after the "**Token memoization.**" bullet:

- **Same-tree delegated pre-commit verdict.** This bullet applies in a consuming repository whose `[tool.livespec_dev_tooling]` table sets both `delegated_gate = true` and `delegated_pre_commit = true`. There the pre-push gate MUST accept a qualifying delegated pre-commit run as the full-suite verdict for the tree it judged. A run qualifies only when two things hold. First, §"Delegated pre-commit aggregate" **Evidence for the pre-push gate** recorded pre-push evidence for it, which names its gate Job in a field of its own. Second, at push time the pushing worktree is clean and its `HEAD` tree is the tree that evidence names. A pre-commit record that carries no gate Job name MUST NOT qualify. When a run qualifies, the pre-push gate MUST NOT submit a gate Job and MUST NOT run the local fall-through. It MUST still run, on the pushing host against the same tree, three kinds of member:
  - every member of its own check set that the evidence does not name as run and passed;
  - every world-reading member of its check set, as **Token memoization** requires, whether or not the pre-commit Job ran it;
  - every member that declares it reads an authorization held outside the tree, as **What the delegated gate runs** places such members.

  It MUST refuse the push, naming the member, when any member it runs fails. It MUST print the gate Job's name and the tree hash whose pre-commit verdict it accepted, the name of each member it ran, and the number of members it skipped because that verdict covered them. A push gated this way therefore never reads as fully gated by a pre-push Job.

  A pre-commit aggregate that ran on the committing host MUST NOT qualify, even when it passed on the same tree. That covers a host that cannot read the gates kubeconfig, a repository whose pre-commit delegation is off, and the local run that follows an absent delegated verdict. The same-tree evidence that the **Local-aggregate evidence entry point** of §"Suite-green replay leg" writes therefore MUST NOT stand in for the pre-push gate. It still serves that section's **Same-tree reuse** bullet. When no qualifying run exists for the `HEAD` tree, the pre-push gate MUST gate exactly as the other bullets of this section require. A push that accepts a qualifying run makes no delegated gate run, so it emits no outcome event under **Telemetry**. For a push that the **Seed and preserve refs** bullet covers, that bullet takes precedence over this one.

  Fleet scope: this bullet binds the pre-push gate of every consuming repository that sets both keys, including a repository whose pre-push gate reads the green token through a script of its own. Such a gate MUST NOT refuse a qualifying run's evidence because it carries pre-commit provenance.

  This bullet and the sentence added to **Explicit local route** are spec-first. As of filing, this repository's `green_token check` honours any token whose tree matches. That includes the token `scripts/just/check.sh` writes after the pre-commit hook's local `just hook_gate=1 check`, and evidence whose gate Job name exists only inside its `run_id`. livespec-orchestrator-beads-fabro's `dev-tooling/green-token-scope.sh` refuses every token that carries `pre_commit_aggregate`. No gate Job reports its member list. The revise that ratifies this bullet MUST name the work item that owns the change.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario: a push of a tree whose delegated pre-commit aggregate passed submits no gate Job and runs only the members that run did not cover

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and `delegated_pre_commit = true`

And its check set holds a tree-pure member `check-alpha` and the world-reading member `check-red-green-replay`, beside its other members

And a Green-amend commit whose pre-commit hook ran the full aggregate as gate Job `J` on staged tree `T`, and `J` reported a green verdict for `T` with a member list naming every member except `check-alpha` and `check-red-green-replay` as run and passed

And when that verdict arrived the working tree had no unstaged change and no untracked, non-ignored file, and `git write-tree` still named `T`

And the pushing worktree is clean and its `HEAD` tree is `T`

When the pre-push gate runs for a push of that commit to an ordinary branch

Then it MUST NOT submit a gate Job and MUST NOT run the local `just check` fall-through

And it MUST run `check-alpha`, `check-red-green-replay`, every other world-reading member and every authorization-reading member of its check set on the pushing host against `T`

And it MUST NOT run any tree-pure member that `J` reported as run and passed

And it MUST print `J`, `T`, the name of each member it ran, and the number of members it skipped

And the push MUST complete when every member it ran passes

## Scenario: a pre-commit aggregate that ran on the committing host does not stand in for the pre-push gate

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and `delegated_pre_commit = true`

And a commit whose pre-commit aggregate ran `just check` on the committing host and passed on tree `T`, because the delegated run reached no verdict and the hook gated locally

And the pushing worktree is clean and its `HEAD` tree is `T`

When the pre-push gate runs on a host eligible under **Host eligibility** for a push of that commit to an ordinary branch

Then the local aggregate MUST NOT have written a green token or pre-push evidence for `T`

And the pre-push gate MUST submit a gate Job for `T` exactly as it does for a tree with no pre-commit evidence

And it MUST NOT print that it accepted a pre-commit verdict

## Scenario: a delegated pre-commit pass on a dirty or changed tree does not stand in for the pre-push gate

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and `delegated_pre_commit = true`

And a commit whose pre-commit hook ran the full aggregate as gate Job `J` on staged tree `T`, and `J` reported a green verdict and its member list for `T`

And when that verdict arrived the working tree had an unstaged change or an untracked, non-ignored file, or `git write-tree` named a tree other than `T`

When the pre-commit hook finishes

Then it MUST record no pre-push evidence for `J`

And a later pre-push gate for a clean worktree whose `HEAD` tree is `T` MUST submit a gate Job for `T` on a host eligible under **Host eligibility**

## Scenario: a delegated pre-commit pass does not stand in for a push whose tree or worktree differs

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and `delegated_pre_commit = true`

And recorded pre-push evidence that gate Job `J` passed the full pre-commit aggregate on tree `T`

And the pushing worktree's `HEAD` tree is not `T`, or the pushing worktree has an uncommitted change

When the pre-push gate runs on a host eligible under **Host eligibility** for a push to an ordinary branch

Then it MUST gate exactly as it does with no pre-commit evidence, and MUST NOT print that it accepted `J`'s verdict

## Scenario: a doc-only or Red-leg delegated pre-commit run records no pre-push evidence

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and `delegated_pre_commit = true`

And a commit whose delegated pre-commit gate Job ran the doc-only subset or the Red-leg subset for staged tree `T` and reported a green verdict

When the pre-commit hook finishes

Then it MUST record no pre-push evidence for `T`

## Scenario: a member outside the delegated pre-commit run's scope still runs at pre-push and refuses the push when it fails

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and `delegated_pre_commit = true`

And recorded pre-push evidence that gate Job `J` passed the full pre-commit aggregate on tree `T` with a member list that does not name `check-red-green-replay`

And the pushing worktree is clean and its `HEAD` tree is `T`

And `check-red-green-replay` fails for the pushed range

When the pre-push gate runs for a push of that commit to an ordinary branch

Then it MUST run `check-red-green-replay` on the pushing host

And it MUST refuse the push, naming `check-red-green-replay`
