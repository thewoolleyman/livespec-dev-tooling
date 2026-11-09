---
topic: master-push-cancel-superseded
author: claude:ci-runtime-and-cost
created_at: 2026-11-09T09:04:04Z
---

## Proposal: A member with no master-health reconciler may cancel superseded master push runs

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Amends constraints.md §"CI matrix shape" so that a repository whose workflows call no master-health reconciler MAY cancel an in-progress master push CI run once a newer master push of the same workflow supersedes it. The newest master head's run still runs its unconditional full aggregate, and pull-request and merge_group runs are never cancelled by the setting. A check in `just check` MUST refuse the setting in any repository whose workflows call the master-health reconciler, because a cancelled run leaves a commit with no verdict and the reconciler cannot prove a culprit from it. The allowance is interim: it stands until the reconciler can resolve an unverdicted commit by re-running its cancelled run, which is a separate, later livespec core proposal. Three scenarios state the behaviour.

### Motivation

Maintainer ruling 2026-11-09, recorded on plan epic livespec-dev-tooling-ib3oe3. It chose option B now, with option A as the end state, from research note plan/ci-runtime-and-cost/research/007-superseded-master-runs-2026-11-09.md (livespec-dev-tooling#3847). Over 72 h, master push runs that a newer master push had already superseded spent about 4,110 runner-min/day, 48% of all master-lane CI. About 2,467/day was in livespec-dev-tooling and 1,640/day in livespec-orchestrator-beads-fabro, and neither repository calls the master-health reconciler. livespec, the one reconciler caller, had no superseded runs. During the 2026-11-09 merge gap the dev-tooling master lane stacked 7 runs, and each new head's jobs queued over 3 minutes until 11 superseded runs were cancelled by hand. Today §"CI matrix shape" requires an "unconditional full-aggregate on master", which a cancelled superseded run does not complete, so the setting needs this amendment before any workflow carries it. The guard exists because contracts.md §"Master-health reconciler" names a culprit only from proven verdicts and raises needs-attention when a culprit cannot be proven; a cancelled run would turn every automatic revert in a reconciler-calling repository into needs-attention.

### Proposed Changes

In constraints.md §"CI matrix shape", after the first paragraph (the per-event matrix shape and the incident repair-PR exception), add this paragraph:

> A repository whose workflows call no master-health reconciler (contracts.md §"Master-health reconciler") MAY cancel an in-progress `master` push run of a CI workflow when a newer `master` push run of the same workflow starts. It does so through a workflow `concurrency` group keyed on the workflow and the ref whose `cancel-in-progress` is true only for `push` events on the default branch. The setting MUST NOT cancel a `pull_request` or `merge_group` run. The newest `master` head's run MUST still run the unconditional full aggregate, and a cancelled superseded run MUST NOT be read as that commit's verdict, green or red. A check in `just check` MUST fail when a repository's workflows call the master-health reconciler's reusable workflow and any of its CI workflows sets `cancel-in-progress` for `master` push events, naming the workflow file and the reconciler caller, because a cancelled run leaves a `master` commit with no verdict and the reconciler cannot prove a culprit from it. This allowance is interim: it SHOULD be retired when the reconciler can resolve an unverdicted commit by re-running its cancelled run.

In scenarios.md, add these three scenarios:

```
## Scenario: a superseded master push run is cancelled in a repository that calls no master-health reconciler

Given a repository whose workflows call no master-health reconciler

And its CI workflow cancels in-progress master push runs of the same workflow

And a master push run of that workflow is in progress for commit C1

When a newer master push for commit C2 starts a run of the same workflow

Then the run for C1 MUST be cancelled

And the run for C2 MUST run the unconditional full aggregate

## Scenario: the master cancel setting never cancels a pull-request run

Given a repository whose CI workflow cancels in-progress master push runs

And a pull-request run of that workflow is in progress

When a newer master push starts a run of the same workflow

Then the pull-request run MUST NOT be cancelled

## Scenario: master run cancellation is refused in a repository that calls the master-health reconciler

Given a repository whose workflows call the master-health reconciler's reusable workflow

And one of its CI workflows sets cancel-in-progress for master push events

When `just check` runs

Then the check MUST fail naming that workflow file and the reconciler caller
```
