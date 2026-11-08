---
topic: ci-lane-priority-from-plan-rank
author: claude-opus-5-5
created_at: 2026-11-08T15:03:51Z
---

## Proposal: CI lane priority follows plan rank through a pre-joined priorities record chosen at runs-on

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a section stating how a fleet repository's CI runs take lane priority from the coordinator's plan ranking without naming any plan in code. A CI_PRIORITY_RECORD repository variable carries a pre-joined map from open work item to priority band. A route step chooses each pull-request or master-push run's runs-on target from the work item ids that run names, sending high-band runs to a priority runner set that shares its lane's LocalQueue and ClusterQueue and carries a higher Kueue WorkloadPriorityClass. A missing record or an unmapped run falls back to the normal set and never blocks. The dispatcher's ticket order reads the same record. Two scenarios state the routing and the fail-safe.

### Motivation

On 2026-11-08 between 14:51Z and 14:56Z, three jobs of livespec-dev-tooling#3796 sat queued for 220 s behind first-in-first-out admission in livespec-dev-tooling-cq. That PR was the incident hook fix on the expedited incident track's critical path. Priority was enforced only by hand-cancelling factory draft runs from a 60-second watcher. The maintainer directed that the fix be generic and driven by priority, not hard-coded plan names. legacy-coordinator-agent ruled the mechanism (2026-11-08, about 15:2xZ) and split preemption of running workloads into a separate phase held for a maintainer ruling. A pod-level priority alone cannot work: ARC creates a runner pod before GitHub assigns it a job, so nothing at admission says which run the pod will serve (ci-runner/k3s/phase2/kueue/DERIVATION.md, "Why a WorkloadPriorityClass cannot fix it"). Priority is therefore chosen at runs-on. Work item: livespec-dev-tooling-5wewi2 (phase 1). Phase 2 (preemption and automatic re-run) is livespec-dev-tooling-samgg2 and is out of scope here.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, add a new section immediately after "## Runner-pool node rebuild recipe":

## CI lane priority from plan rank

A fleet repository's CI runs MUST take lane priority from the coordinator's ranking of plans, and no plan slug or plan epic id MAY appear in CI workflow code, route code or runner configuration.

**Record.** Every fleet repository MUST carry a repository variable `CI_PRIORITY_RECORD` whose value is one JSON object with `schema`, `generated_at`, `source` (the priorities-record comment it was derived from), `plan_rank` (plan epic id to rank), `items` (open work item id to band: `high`, `medium` or `low`) and `default` (the band of anything unmapped). The `items` map MUST be pre-joined by its producer: open work item, then its owning plan epic through the parent edge, then that epic's rank, then the band under the thresholds committed in livespec-dev-tooling's configuration. CI therefore needs no ledger credential to read it. The producer MUST write the same value to every fleet repository, MUST be idempotent, and MUST offer a dry-run that prints each repository's value and writes nothing. The coordinator owns the record's content and runs the producer on each priorities-record append.

**Route.** Each pull-request and master-push CI run MUST choose its gating jobs' `runs-on` target in a route step that reads `CI_PRIORITY_RECORD` and the work item ids the run names: in its head branch and pull-request title, or, on a master push, in its merged commit's subject. A run whose best band is `high` MUST go to the repository's priority runner set for its lane, and every other run MUST go to the lane's normal runner set. The route step is a pure function of the record and the run's event: it MUST NOT probe runner capacity or runner labels.

**Runner sets.** A lane's priority runner set MUST use the same LocalQueue and ClusterQueue as the lane's normal set, so it adds no churn-slot capacity. Its runner pods MUST carry a Kueue WorkloadPriorityClass higher than the normal set's, so that while the lane's ClusterQueue has pending workloads, a pending high-band workload is admitted before every earlier-created pending normal workload. This section states admission ORDER only: a high-band workload MUST NOT evict a running workload under this section.

**Fail-safe.** A missing, unreadable or schema-invalid `CI_PRIORITY_RECORD`, a route-step error, or a run that names no work item in the record MUST send the run to the normal runner set, MUST write the reason to the run's job summary, and MUST NOT block or fail the run.

**One source.** The orchestrator dispatcher's ticket order SHOULD read the same `CI_PRIORITY_RECORD`, so that queue order and CI priority cannot disagree.

**Rollout.** The priority runner set MUST be rolled out canary-first: livespec-dev-tooling's pull-request lane first, measured, then every fleet repository's pull-request lane and the livespec-dev-tooling master lane.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario: a run of a high-band work item is admitted ahead of earlier pending normal runs

Given `CI_PRIORITY_RECORD` bands work item W `high` because W's plan epic holds a top rank

And the repository's pull-request lane is at its churn-slot quota with normal workloads pending

When a pull request whose head branch names W starts its CI run

Then the route step MUST send the run's gating jobs to the lane's priority runner set

And each of those jobs' pending workloads MUST be admitted before every earlier-created pending normal workload in that ClusterQueue

And admitting them MUST NOT evict any running workload

## Scenario: a run with no usable priority record runs on the normal runner set

Given `CI_PRIORITY_RECORD` is missing from the repository, or does not parse as the record schema

When a pull request starts its CI run

Then the route step MUST send the run's gating jobs to the lane's normal runner set

And the run's job summary MUST state why no priority was applied

And the run's gating jobs MUST proceed as they would with no route step
