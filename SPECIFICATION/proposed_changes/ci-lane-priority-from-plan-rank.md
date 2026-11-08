---
topic: ci-lane-priority-from-plan-rank
author: claude-opus-5-5
created_at: 2026-11-08T15:19:18Z
---

## Proposal: CI lane priority follows the maintainer radar through an opt-in priority runner set chosen at runs-on

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/constraints.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Let a fleet repository's CI runs take lane priority from the maintainer radar's order without naming any plan in code. A producer derives a CI_PRIORITY_RECORD repository variable from the radar load entry point; its wire format is a contract. A hosted, non-required route job bands each run from the work item ids it names. A lane opts in through a CI_RUNNER_LABELS_PRIORITY variable that sends high-band runs to a priority runner set sharing the lane's LocalQueue and ClusterQueue at a higher Kueue WorkloadPriorityClass. Admission order changes; nothing is evicted. Every missing, stale, unreadable or unmapped case, and every lane that has not opted in, keeps today's routing. This library ships the route as a composite Action that other fleet repositories adopt under their own specifications. Five scenarios state pull-request and master-push routing, fallback, and the producer.

### Motivation

Measured on 2026-11-08 between 14:51Z and 14:56Z: three jobs of livespec-dev-tooling#3796, the incident hook fix on the expedited incident track's critical path, sat queued for 220 s behind first-in-first-out admission in livespec-dev-tooling-cq. Priority was enforced only by hand-cancelling factory draft runs from a 60-second watcher. The maintainer directed a generic, priority-driven fix with no hard-coded plan names. legacy-coordinator-agent ruled the mechanism and held preemption of running workloads for a separate maintainer ruling (livespec-dev-tooling-samgg2). ARC creates a runner pod before GitHub assigns it a job (ci-runner/k3s/phase2/kueue/DERIVATION.md, "Why a WorkloadPriorityClass cannot fix it"), so priority must be chosen at runs-on. The priority order already lives in the maintainer radar (§"Maintainer radar"), so the record is derived from it and is not a second ordering. This revision of the proposal applies the post-step LLM doctor findings: the routing contract in constraints.md is amended rather than contradicted; the priority set is an explicit opt-in, so an unprovisioned lane never strands a run; the record derives from the radar; the route job is hosted and non-blocking; and the record schema is placed in contracts.md. Work item: livespec-dev-tooling-5wewi2 (phase 1). A second doctor pass narrowed the identifier ban to routing inputs (existing comments legitimately name item ids), amended the manual-revert sentence, and scoped fleet adoption through a shipped composite Action.

### Proposed Changes

### 1. `SPECIFICATION/non-functional-requirements.md`: add a section immediately after "## Runner-pool node rebuild recipe"

## CI lane priority from the maintainer radar

A fleet repository's CI runs MUST take lane priority from the maintainer radar's order (§"Maintainer radar"), and a plan slug, plan epic id or work item id MUST NOT be used as a routing, band or priority input in CI workflow code, route code or runner configuration. Plan identity MUST enter routing only through `CI_PRIORITY_RECORD` (contracts.md §"CI priority record"), which the route reads as data.

**Producer.** The record MUST be produced by one committed producer in this repository. The producer MUST derive the record from the radar that the radar load entry point returns, never from any other ordering. Band assignment works as follows:
- A `plan` entry bands every open child of its plan. The children are computed as §"Maintainer radar" computes them: the union of dotted-id descendants and `parent-child` edges.
- An `item` entry bands that item directly.
- An entry's band comes from its radar index under the thresholds committed in `.livespec.jsonc` at `ci.priority_bands`, an object mapping `high` and `medium` to the largest radar index each covers.
- When one item falls under several entries, its best band holds, in the order `high` > `medium` > `low`.

The producer MUST write the same value to every fleet repository's `CI_PRIORITY_RECORD`, and a second run on an unchanged radar and ledger MUST leave every value byte-identical. It MUST offer a dry-run that prints each repository's value and writes nothing. It MUST refuse to write a value larger than the platform's repository-variable limit, naming the size. The coordinator runs the producer, and SHOULD run it after every change to the radar.

**Runner sets.** A lane that opts in carries a priority runner set beside its normal set.
- The priority set MUST use the same LocalQueue and ClusterQueue as the normal set, so it adds no churn-slot capacity.
- Its runner pods MUST be identical to the normal set's pods except for the scale-set name and a Kueue WorkloadPriorityClass higher than the normal set's.
- In particular, its pods MUST use the same scheduler profile that §"Runner placement follows admission capacity" relies on.
- The sum of a lane's normal and priority `maxRunners` MUST stay within the bound that DERIVATION.md "Bounding maxRunners to the quota" derives for that lane.

While a lane's ClusterQueue has pending workloads, a pending high-band workload MUST be admitted before every earlier-created pending normal workload. This section changes admission ORDER only: admitting a high-band workload MUST NOT evict a running workload.

### 2. `SPECIFICATION/constraints.md`, §"CI matrix shape": insert after the paragraph introducing `CI_RUNNER_LABELS_MASTER`

A gating job MAY additionally route through the lane's opt-in priority variable, `CI_RUNNER_LABELS_PRIORITY` for pull-request events and `CI_RUNNER_LABELS_MASTER_PRIORITY` for push events. The priority variable is read only when the run's band, taken from the route job's output (non-functional-requirements.md §"CI lane priority from the maintainer radar"), is `high`. It is read at the same `runs-on`, ahead of the existing terms, and the inline hosted literal stays the LAST term. An unset priority variable MUST leave the job on the lane's existing routing. A `merge_group` event MUST NOT read a priority variable.

The route job MUST meet all of the following:
- It MUST run on GitHub-hosted capacity and MUST NOT be a required check.
- It MUST be a pure function of `CI_PRIORITY_RECORD` and the run's event, and it MUST NOT probe runner capacity, runner labels or runner health.
- A gating job that reads its output MUST still run when the route job fails or is skipped.
- A gating job MUST read an empty or missing band as not `high`.

The band for a run is computed as follows:
- A pull-request run's band is the best band of the work item ids named in its head branch and title.
- A push run's band is the best band of the ids named in the subjects of the commits the push carries.
- An id the record does not name takes the record's `default`.

The priority variables, the band output and the existing variables together, with the inline fallback, are the entire routing contract.

### 2b. `SPECIFICATION/constraints.md`, §"CI matrix shape": amend the revert paragraph

In the paragraph that begins "Both reverts are MANUAL", replace "deleting both returns every gating job to the inline hosted literal" with "deleting both, and every priority variable, returns every gating job to the inline hosted literal". A set priority variable keeps high-band runs on self-hosted capacity, so the existing sentence would no longer hold.

### 3. `SPECIFICATION/contracts.md`: add a section at the end of the file

## CI priority record

`CI_PRIORITY_RECORD` is a repository variable whose value MUST be one JSON object with these keys:
- `schema`: the integer `1`.
- `generated_at`: an ISO-8601 UTC timestamp.
- `radar_commit`: the commit of `livespec_dev_tooling/radar/radar.py` the record was derived from.
- `items`: an object mapping a work item id to `high` or `medium`.
- `default`: `low`.

The producer MUST omit from `items` every item whose band equals `default`. A reader MUST treat as MISSING a value that does not parse, has another `schema`, lacks a key, or carries a `generated_at` more than 72 hours old. A missing record MUST band every run `default`.

This library MUST ship the route job as a reusable composite Action whose only inputs are `CI_PRIORITY_RECORD` and the run's event, and whose one output is the run's band, computed as constraints.md §"CI matrix shape" states. Another fleet repository takes lane priority only by adopting that Action, and its own priority variables, under its own specification. This repository's lanes adopt it under constraints.md §"CI matrix shape".

### 4. `SPECIFICATION/scenarios.md`: add at the end of the file

## Scenario: a run of a high-band work item on an opted-in lane is admitted ahead of earlier pending normal runs

Given `CI_PRIORITY_RECORD` bands work item W `high`

And the repository's pull-request lane sets `CI_RUNNER_LABELS_PRIORITY` and is at its churn-slot quota with normal workloads pending

When a pull request whose head branch names W starts its CI run

Then its gating jobs MUST run on the lane's priority runner set

And each of their pending workloads MUST be admitted before every earlier-created pending normal workload in that ClusterQueue

And admitting them MUST NOT evict any running workload

## Scenario: a run naming no high-band item keeps the lane's existing routing

Given `CI_PRIORITY_RECORD` names work item V `medium` and does not name work item U

When a pull request whose head branch names V, and another whose head branch names U, start their CI runs

Then both runs' gating jobs MUST run on the lane's existing routing

And a high-band run on a lane that does not set `CI_RUNNER_LABELS_PRIORITY` MUST also run on the lane's existing routing

## Scenario: a failed route job or an unusable record leaves gating jobs on their existing routing

Given `CI_PRIORITY_RECORD` is missing, does not parse, or carries a `generated_at` more than 72 hours old, or the route job fails

When a pull request starts its CI run

Then its gating jobs MUST run on the lane's existing routing and reach their own outcome

And the route job's summary MUST state why no priority was applied, when the route job ran

## Scenario: a master push carrying a high-band work item's commit runs on the master lane's priority set

Given `CI_PRIORITY_RECORD` bands work item W `high`

And the repository sets `CI_RUNNER_LABELS_MASTER_PRIORITY`

When a push to master carries a commit whose subject names W

Then the push run's gating jobs MUST run on the master lane's priority runner set

And a push whose commit subjects name no high-band item MUST run on the master lane's existing routing

## Scenario: the CI priority producer is idempotent and its dry-run writes nothing

Given the maintainer radar and the ledger are unchanged between two producer runs

When the producer runs twice, and then runs once with its dry-run flag

Then every fleet repository's `CI_PRIORITY_RECORD` after the second run MUST be byte-identical to its value after the first

And the dry-run MUST print each repository's value and MUST leave every `CI_PRIORITY_RECORD` unchanged
