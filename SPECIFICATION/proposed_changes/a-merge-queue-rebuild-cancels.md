---
topic: a-merge-queue-rebuild-cancels
author: claude-opus-5-5
created_at: 2026-11-15T17:54:18Z
---

## Proposal: A merge-queue rebuild cancels the superseded merge-group run of the same pull request

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Add a merge-queue supersession rule to constraints.md section "CI matrix shape": every merge_group run of each heavy job joins a job-level concurrency group keyed on the pull request number of its own queue entry (resolved and output by the merge-group guard), the workflow name, the job id and the matrix index, with cancel-in-progress true, so a queue rebuild cancels only the superseded run for the same pull request. A run for a different pull request, a pull_request run and a master push run are never cancelled by it. Add one scenario beside the master-concurrency scenarios.

### Motivation

Work item livespec-dev-tooling-uo2cy4 (plan stale-base-merge-options, epic livespec-dev-tooling-xowhol), decided as FIX 1 by throughput-plans-coordinator on 2026-11-15. Measured at 17:40Z on 2026-11-15: the dev-tooling merge queue (max_entries_to_build 4, ALLGREEN) rebuilt three times (17:02, 17:04 and 17:38Z), each rebuild starting four fresh full merge_group CI runs, and the runs on superseded gh-readonly-queue refs were not cancelled. Nine merge_group runs were in progress and five were on refs that no longer existed (cancelled by hand: 43739071141, 43739069389, 43739067835, 43739066269, 43738809554). Each orphan runs the full suite, including check-fleet-conformance at about 521 App-installation requests per sweep, which is the burst multiplier behind both exhaustions of installation 182016479 (~16:28Z and ~17:37Z). Today ci.yml's workflow-level concurrency groups every run except ordinary master pushes by its own run_id with cancel-in-progress false (v182, livespec-dev-tooling-qzw2gf), so a superseded merge_group run is never cancelled. A workflow-level expression cannot strip the base sha from the merge-queue head_ref (gh-readonly-queue/master/pr-<N>-<base sha>) and cannot read job outputs, so the number comes from the existing first job, merge-group-guard, which already resolves the group's pull requests through the forge API, and the grouping is job-level, where `needs` is an allowed context (docs.github.com, workflow syntax, jobs.<job_id>.concurrency: "Allowed expression contexts: github, inputs, vars, needs, strategy, and matrix"). The key carries the matrix index because at most one job runs in a group at a time, so matrix legs sharing a key would cancel each other. This removes no coverage: a superseded ref no longer exists, so its verdict gates nothing, and the replacing run runs everything.

### Proposed Changes

In constraints.md section "CI matrix shape", insert this paragraph directly after the paragraph that defines the master push concurrency group (the one ending "it SHOULD be retired when the reconciler can resolve an unverdicted commit by re-running its dropped run."). That paragraph, and its statement that the master push group never holds, cancels or drops a `merge_group` run, are unchanged:

> A CI workflow that runs on `merge_group` events MUST put every `merge_group` run of each heavy job (every job that can route to self-hosted capacity, and every job that spends the forge's App-installation request budget, such as fleet conformance) in a job-level `concurrency` group keyed on the pull request number of that run's OWN merge-queue entry, with `cancel-in-progress` true. The workflow's first job, the merge-group guard (contracts.md §"The guarded merge_group exception"), MUST resolve that number through the forge API from the queue entry whose head commit is the merge group's head commit, and MUST output it; it MUST output it empty on every other event and whenever it cannot resolve exactly one such entry. The group key MUST include the workflow's name, the job's id and the job's matrix index, because a repository's concurrency groups are shared across all its workflows and at most one job runs in a group at a time, so a key without them would let one job or matrix leg cancel another. When the merge queue rebuilds and starts a new `merge_group` run for a pull request, each heavy job of the superseded `merge_group` run for that same pull request MUST be cancelled, whether it is pending or in progress, and the new run MUST run the unconditional full aggregate. A `merge_group` run whose guard output an empty number MUST instead run in a group of its own and MUST NOT cancel or be cancelled. This supersession group MUST NOT hold, cancel or drop a `merge_group` run for a different pull request, a `pull_request` run or a `push` run, and the workflow-level concurrency of every other event is unchanged. A superseded run's merge-queue ref no longer exists, so its verdict gates nothing; a job this group cancelled, and the `ci-green` of its run, MUST NOT be read as a verdict, green or red, of any pull request or merge group. The fleet member this rule is ratified for is livespec-dev-tooling; every repository that later moves onto the merge queue MUST adopt the same guard-output-keyed concurrency through its own workflow change when it adopts the queue.

In scenarios.md, add this scenario directly after "## Scenario: the master concurrency group never holds or cancels a pull-request run", which is unchanged:

## Scenario: a merge-queue rebuild cancels the superseded merge-group run of the same pull request

Given a CI workflow that runs on `merge_group` events and whose merge-group guard outputs the pull request number of each run's own queue entry

And a `merge_group` run R1 for pull request P on merge-queue ref Q1 is pending or in progress

And a `merge_group` run S for a different pull request P2 is pending or in progress

When the merge queue rebuilds, removes Q1, and starts a `merge_group` run R2 for P on a new ref Q2

Then every heavy job of R1 MUST be cancelled, and R1 MUST NOT be read as a verdict of P, green or red

And R2 MUST run the unconditional full aggregate

And S MUST NOT be cancelled

And a `pull_request` run and a `master` push run of the same workflow MUST NOT be held, cancelled or dropped

And a `merge_group` run whose guard could not resolve its queue entry MUST NOT be cancelled and MUST NOT cancel another run

The revise that ratifies this MUST add a row for the new scenario heading to tests/heading-coverage.json, naming its owning work item livespec-dev-tooling-uo2cy4, and regenerate the debt register in the revise commit.
