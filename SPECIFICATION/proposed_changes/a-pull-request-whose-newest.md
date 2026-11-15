---
topic: a-pull-request-whose-newest
author: claude-opus-5-5 (ci-runtime-and-cost)
created_at: 2026-11-13T04:02:00Z
---

## Proposal: A pull request whose newest CI run is a zero-job ghost is closed and reopened once for a fresh run on the same head

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a ghost-run pass to the CI infrastructure re-run reconciler. When an open pull request's newest gating CI run for its current head stays queued with zero jobs, unchanged since creation, for more than 15 minutes, the reconciler closes and reopens that pull request once, on a schedule of at most every 5 minutes, so that GitHub creates a fresh run on the unchanged head. It re-arms auto-merge afterwards except under merge-hold:on. Master heads, non-newest ghosts and ghosts with no open head are only reported. The reusable workflow contract gains the scheduled trigger and the App-token rule, and scenarios.md gains one scenario.

### Motivation

Work item livespec-dev-tooling-227glz (plan ci-runtime-and-cost, epic livespec-dev-tooling-ib3oe3) was filed at spec-change tier against ## Hooks and CI, because no current clause covers a queued run GitHub never started. ## Hooks and CI ratifies the CI infrastructure re-run reconciler's signatures for COMPLETED runs only: the Set up job 429, the Initialize containers registry error, and the job-creation Internal server error. On 2026-11-13 at 00:47:15Z the stale-base-merge-options seat measured 31 queued runs across the fleet (livespec, livespec-dev-tooling, livespec-driver-claude, livespec-driver-codex, livespec-orchestrator-beads-fabro, livespec-overseer). 30 had zero jobs: GitHub created the run record and never created its jobs. 28 cancel attempts were refused with HTTP 409, and such a run cannot be re-run either, so a fresh run is the only lever. A ghost run on an open pull request's newest head leaves that pull request with no verdict, so it never merges. The ci-runtime-and-cost seat, the CI owner, decided the remedy on livespec-dev-tooling-xowhol (DECISION ~01:0xZ and AMENDMENT ~01:1xZ, 2026-11-13), and legacy-coordinator-agent accepted this route (option (a)): close then reopen the pull request once, which fires a pull_request reopened run on the unchanged head. The head is never moved, because a moved head makes a factory run's resume refuse. Closing a pull request drops its auto-merge, so the reconciler re-arms it, except under merge-hold:on, the coordinator's label, whose removal IS the merge. Master heads are out of scope (the next push supersedes them), and so are non-newest historical ghosts and runs with no open head: they are reported only, never deleted. The live case that prompted the ruling was livespec-overseer#2948. The pass is placed in the existing reconciler, but it needs a scheduled trigger, because the reconciler starts on a workflow_run completed event, which a ghost run never raises. The App-token rule is in the contract because a reopen made with GITHUB_TOKEN starts no workflow and so would not produce the fresh run this clause requires.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, §"Hooks and CI", insert the following paragraph immediately after the paragraph that begins "A gating CI run of a fleet repository that adopts the CI infrastructure re-run reconciler and that GitHub fails at job creation":

A pull request of a fleet repository that adopts the CI infrastructure re-run reconciler, whose newest gating CI run for its current head is a ghost run, MUST be closed and reopened once by the reconciler, so that GitHub creates a fresh gating CI run on the unchanged head. A ghost run is a gating CI run whose status is `queued`, that has zero jobs, whose `updated_at` equals its `created_at`, and that is more than 15 minutes old. The reconciler MUST look for ghost runs on a schedule of at most every 5 minutes, because a ghost run never completes and so never raises the event that starts the reconciler for a completed run. It MUST NOT move the pull request's head, MUST NOT delete a ghost run, and MUST NOT close and reopen a pull request more than once for the same ghost run id; a later sighting of that run MUST be recorded in its run summary as left for its owner. A pull request that had auto-merge enabled before the close MUST have auto-merge enabled again after the reopen, unless it carries the `merge-hold:on` label, in which case auto-merge MUST stay disabled. A ghost run on a master head, a ghost run that is not the newest gating CI run of its open pull request's head, and a ghost run whose head has no open pull request MUST NOT be acted on and MUST only be reported. Each close and reopen MUST write the repository, the pull request number, the ghost run id and the new run id to the reconciler's own run summary, and each ghost run the reconciler only reports MUST be named in that summary.

In SPECIFICATION/contracts.md, §"Reusable workflows wire contract", in the `reusable-ci-infra-rerun.yml` paragraph, replace "Inputs: `run_id` (the completed run to reconcile)." with "Inputs: `run_id` (the completed run to reconcile; omitted on the scheduled trigger below)." Then, in the same paragraph, append the following two sentences immediately after the sentence "It also classifies a run that created zero jobs or only some of its jobs against the run's own annotations, and re-runs the whole run, after the wait non-functional-requirements.md §"Hooks and CI" names, when they match a run-level re-run signature that section names.":

A second caller trigger, a `schedule` of at most every 5 minutes, calls it with no `run_id`; on that trigger it runs the ghost-run pass non-functional-requirements.md §"Hooks and CI" names, which closes and reopens a pull request whose newest gating CI run is a ghost run. The close, the reopen and any auto-merge re-arm MUST be made with the fleet's GitHub App token, not `GITHUB_TOKEN`, because an event raised with `GITHUB_TOKEN` starts no further workflow run, so a reopen made with it would create no fresh CI run.

In SPECIFICATION/scenarios.md, insert the following scenario immediately after "## Scenario: a CI run GitHub fails at job creation with an Internal server error is re-run with backoff":

## Scenario: a pull request whose newest CI run is a zero-job ghost is closed and reopened once

Given an open pull request of a fleet repository whose caller workflow calls `reusable-ci-infra-rerun.yml`

And the newest gating CI run for the pull request's current head is `queued`, has zero jobs, has `updated_at` equal to `created_at`, and is more than 15 minutes old

And the pull request had auto-merge enabled and carries no `merge-hold:on` label

When the reconciler's scheduled ghost-run pass runs

Then it MUST close and reopen the pull request once, leaving its head unchanged

And a new gating CI run MUST be created on the same head

And auto-merge MUST be enabled on the pull request again

And it MUST write the repository, the pull request number, the ghost run id and the new run id to its own run summary

And a later pass that sees the same ghost run MUST NOT close and reopen the pull request again, and MUST record that run as left for its owner

And a ghost run on a master head, a ghost run that is not the newest gating CI run of its head, and a ghost run whose head has no open pull request MUST only be named in the summary, never acted on

And a pull request labelled `merge-hold:on` that is closed and reopened MUST be left with auto-merge disabled

The revise that accepts this adds a `tests/heading-coverage.json` row for the new scenario heading; its owed test belongs to livespec-dev-tooling-227glz, which implements the pass.
