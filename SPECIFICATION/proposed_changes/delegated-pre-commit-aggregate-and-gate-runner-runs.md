---
topic: delegated-pre-commit-aggregate-and-gate-runner-runs
author: claude-opus-5-5:dev-host-test-gate-load
created_at: 2026-11-01T16:29:06Z
---

## Proposal: Delegate the hand-commit pre-commit aggregate to a gate Job keyed to the staged tree

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add an opt-in `delegated_pre_commit` delegation under which `just check-pre-commit` runs as a gates Job against the staged tree. The Job's verdict is the commit's verdict, world-reading members stay on the committing host, and a missing verdict falls back to a local run that says so. This retires v105's 'the pre-commit aggregate is not delegated' bullet.

### Motivation

Plan dev-host-test-gate-load (epic livespec-dev-tooling-6vuiwe), DoD assertion 2, ordered by the maintainer on 2026-11-01. On the dev host vmi3006760 the pre-commit aggregate of hand commits measured 1.1 of 15.2 attributed cores in the first slice of the v3 window (plan research note 002). It was the second-largest test/gate class after the janitor. v105 delegated only the commit-hook replay runs and left this aggregate deliberately local.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Delegated commit-time replay test runs", the bullet **The pre-commit aggregate is not delegated.** MUST be replaced by: "**The pre-commit aggregate.** Whether `just check-pre-commit` runs on the committing host or as a gate Job is governed by §"Delegated pre-commit aggregate", not by this key."

A new H2 section MUST be added to `contracts.md`, immediately after §"Delegated commit-time replay test runs":

## Delegated pre-commit aggregate

A consuming repository MAY run its pre-commit check aggregate (`just check-pre-commit`) as a Kubernetes Job in the `gates` namespace that §"Delegated pre-push gate" uses, instead of on the committing host. Delegation changes WHERE the aggregate runs. It MUST NOT change which members the pre-commit hook selects for a staged change, or how it judges them.

- **Opt-in.** Pre-commit delegation is switched on by `delegated_pre_commit = true` in the consumer's `[tool.livespec_dev_tooling]` table. The key is independent of `delegated_gate` and `delegated_commit_tests`. It is read by its own loader and is not a role key. Only the literal boolean `true` enables it. An absent key, `false`, a value of another type, or an unreadable `pyproject.toml` all leave the aggregate on the committing host.
- **Host eligibility.** With the key switched on, a commit delegates only when the committing user can read the gates kubeconfig on that host, as §"Delegated pre-push gate" decides for a push. A host without that credential MUST run the aggregate locally and MUST say in the hook output that it gated locally.
- **The staged tree.** The gate Job MUST run against the tree that `git write-tree` names for the index when the hook runs. The gate client MUST publish that tree to the cluster's gate mirror the same way it publishes a pushed tree. The committing host MUST verify that the Job's reported tree hash equals the staged tree hash before it honours the outcome. An outcome reported for any other tree is an absent verdict.
- **What the Job runs.** The Job MUST run exactly the members that the local aggregate would run for that staged tree, and nothing else. A member that declares it reads an authorization held outside the tree MUST instead run on the committing host against the same tree, as §"Delegated pre-push gate" places such members.
- **Verdict.** The Job's verdict is the aggregate's verdict. A green verdict lets the commit proceed. A red verdict MUST refuse the commit, and the hook output MUST carry the Job's complete output and name each failed member. Every hook run that delegated MUST print the gate Job's name and the staged tree hash.
- **Absent verdict.** A verdict is absent when the API server is unreachable, the credential cannot be refreshed, the Job cannot be submitted, the Job is lost or times out, or the reported tree does not match. In each case the committing host MUST run the aggregate itself and MUST say that it gated locally. A commit MUST NOT be refused because the cluster returned no verdict. This is the same departure from the pre-push rule that §"Delegated commit-time replay test runs" makes.
- **Telemetry.** Every delegated pre-commit run MUST emit exactly one outcome span, with the outcome words §"Delegated pre-push gate" defines: `passed`, `failed-tree` and `no-verdict`.
- **Credential use.** Cluster commands go through `with-gates-kubeconfig`, as §"Delegated pre-push gate" states. This delegation adds no credential.

In `SPECIFICATION/scenarios.md`, two scenarios MUST be added:

## Scenario: a delegated pre-commit aggregate gates the staged tree on the cluster

Given a repository with `delegated_pre_commit = true` and a committing host that can read the gates kubeconfig

When a hand commit runs the pre-commit hook

Then the pre-commit aggregate MUST run as a gate Job against the staged tree's hash, the hook output MUST name that Job and tree hash, and a red Job verdict MUST refuse the commit

## Scenario: a delegated pre-commit aggregate with no cluster verdict gates locally

Given a repository with `delegated_pre_commit = true` whose gate Job cannot be submitted

When a hand commit runs the pre-commit hook

Then the committing host MUST run the pre-commit aggregate itself and the hook output MUST say that it gated locally


## Proposal: Run gate-runner full suites as gate Jobs by default, with a recorded explicit local choice

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

In a delegated repository on an eligible host, `gate-start` runs `just check`, `just check-*` and pytest as a gates Job against the worktree's current content by default. `--local` is the explicit dev-host choice. Every run records its venue and, when local, the reason.

### Motivation

Plan dev-host-test-gate-load, DoD assertion 4. Seats' ad-hoc and diagnostic full suites run on the dev host. On 2026-11-01 25-minute diagnostic suites ran there, and ad-hoc pytest/check runs measured 0.45 cores in the first v3 slice. Nothing routes them to the cluster today, so the default puts them on the shared 18-vCPU host where agent sessions contend.

### Proposed Changes

A new H2 section MUST be added to `SPECIFICATION/contracts.md`, immediately after §"Detached gate runner":

## Delegated gate-runner runs

In a repository with `delegated_gate = true`, on a host that is eligible under §"Delegated pre-push gate", `gate-start` MUST by default run a full-suite gate command as a gate Job instead of on the dev host. A full-suite gate command is any of the following, invoked directly or through `mise exec --`: `just check`, `just check-<name>`, `pytest`, or `uv run pytest`.

- **Tree.** The Job MUST run against a tree naming the worktree's current content, including uncommitted changes. The runner MUST write that tree from a temporary index built from the working directory, honouring `.gitignore`. It MUST NOT touch the worktree's own index. It MUST publish the tree to the gate mirror. The run record MUST carry that tree hash.
- **Verdict and output.** The Job's verdict becomes the run's verdict under §"Detached gate runner"'s existing rules, and the Job's complete output MUST be streamed into the run's `output.log`. A cluster that returns no verdict MUST end the run as `DIED_WITHOUT_VERDICT`. It MUST NOT be read as a pass, and the runner MUST NOT silently re-run the command on the dev host.
- **Explicit local choice.** `gate-start --local -- <command>` MUST run the command on the dev host. Every run MUST record a `venue` in its run record and print it: `cluster_job` with the gate Job's name, or `host_local` with the reason. The reasons are an explicit `--local` choice, an ineligible host, an undelegated repository, or a command outside the full-suite set.
- **Not converted.** A `git commit` or `git push` dispatched through `gate-start` MUST keep running its own hooks on the dev host. Those hooks carry their own delegation under §"Delegated pre-push gate", §"Delegated commit-time replay test runs" and §"Delegated pre-commit aggregate".

In `SPECIFICATION/scenarios.md`, two scenarios MUST be added:

## Scenario: a seat's gate-runner full suite runs as a gate Job by default

Given a repository with `delegated_gate = true` and a host that can read the gates kubeconfig

When a seat runs `gate-start -- just check` in a worktree with uncommitted changes

Then the suite MUST run as a gate Job against a tree that includes those changes, and the run record MUST carry `venue: cluster_job`, the Job name and the tree hash

## Scenario: an explicit local gate-runner run is recorded as local

Given the same repository and host

When a seat runs `gate-start --local -- just check`

Then the suite MUST run on the dev host, and the run record MUST carry `venue: host_local` and the reason `--local`

