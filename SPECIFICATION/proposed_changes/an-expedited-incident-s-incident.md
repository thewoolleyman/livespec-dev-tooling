---
topic: an-expedited-incident-s-incident
author: claude-opus-5-5
created_at: 2026-11-13T06:34:42Z
---

## Proposal: An expedited incident's and a stop-the-line pull request's required checks run on a dedicated expedited lane admitted ahead of pull-request traffic

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md §"Expedited incident execution" so that every gating job of a designated run runs on a dedicated self-hosted expedited lane, provided its `runs-on` reads a repository variable. A designated run is an expedited-incident pull request, or a stop-the-line pull request that legacy-coordinator-agent labels `stop-the-line`. Its routing variable is `CI_RUNNER_LABELS_STOP_THE_LINE`.

The lane's quota lends nothing and preempts nothing, and it MAY borrow idle cohort capacity. A designated job never waits on an ordinary pull-request job, and starts within 5 minutes of being queued while the quota has room. Exceeding the quota is degraded service, and a trigger raises it.

Ratify the existing `CI_INCIDENT_RUNNER_LABELS` tailnet carve-out, which no clause states today. State why the two variables exist, and forbid consolidating them.

The route job decides designation from the pull request's issue labels read through the forge. A failed read falls back to ordinary routing loudly: an annotation, a step-summary line, and a `failure` conclusion. Adding `stop-the-line` cancels and re-runs the pull request's newest run.

Amend §"CI priority record" for the route job's new input and output, and constraints.md §"CI matrix shape" for the routing contract. Add five scenarios.

### Motivation

On 2026-11-13 livespec-dev-tooling master was red (z5cjph's run 43372854805 failed). Incident 3hilpy's EXPEDITED_INCIDENT_RESPONSE fix-forward (PR #4466, run 43377282930) had every check green except `incident-ci`, which sat queued from 06:14:13Z while master merges were held on it. It was behind 12 queued jobs on the label `livespec-dev-tooling-k3s`: ordinary PR coverage, red-green-replay and incident-ci legs of eight other pull requests. The pool was saturated at 20/20 runners, and `livespec-dev-tooling-cq` is BestEffortFIFO with no runner priority class. The only WorkloadPriorityClass is `gate-priority`, which orders gate Jobs only. No committed route existed, so a seat cancelled three low-band runs by hand to move the job up.

The same morning showed the same starvation for stop-the-line carriers. legacy-coordinator-agent required, on 2026-11-13, that the lane also cover them:
- livespec-orchestrator-beads-fabro#5138, the revert that lifts the fleet-wide factory stop: three per-file-coverage shards queued from 06:30:07Z behind about 12 jobs on `livespec-orchestrator-k3s`.
- livespec-dev-tooling#4466 (3hilpy): its coverage legs pending behind ordinary pull-request traffic.

A stop-the-line pull request is designated the same way an expedited incident is, by a label, `stop-the-line`. That label is reserved to the coordinator by convention and recorded on the work item.

ARC runners are generic, so a pod-level Kueue priority cannot target one job: only a separate label routes a job to reserved capacity. The dev-tooling master lane (`livespec-dev-master-k3s`, `CI_RUNNER_LABELS_MASTER`, its own values file and its own LocalQueue/ClusterQueue in the Kueue derivation record) already proves that pattern. legacy-coordinator-agent decided this design on 2026-11-13: a dedicated runner set and label with its own LocalQueue/ClusterQueue and reserved nominal quota, mirroring the master lane. It MAY borrow idle cohort capacity, lends nothing, and preempts never. The variable takes the lane suffix form `CI_RUNNER_LABELS_STOP_THE_LINE`, as `CI_RUNNER_LABELS_MASTER` and `CI_RUNNER_LABELS_PRIORITY` do. Job-class variables take an infix (`CI_PYTHON_`, `CI_COVERAGE_`, `CI_INCIDENT_RUNNER_LABELS`).

The expedited lane cannot reuse `CI_INCIDENT_RUNNER_LABELS` as its selector. That variable already routes `incident-ci` and `check-metadata` for EVERY pull request: it is the tailnet carve-out, since both jobs read the incident observer. Pointing it at a reserved set would move all ordinary pull-request metadata traffic onto the lane. So the lane needs its own variable, read only for a designated run.

Whether a run is designated cannot be read from the event payload's labels. The incident label workflow re-runs the CI run when the label is added, and a re-run keeps the ORIGINAL event payload. The route job runs again on a re-run and reads the pull request's current issue labels through the forge, so its output reflects the label. No route job or route Action exists on master yet (§"CI priority record" specifies one), so livespec-dev-tooling-ehnjlt builds it.

The 5-minute bound: unsaturated k3s queue time measures p50 0.3 min and p95 4.4 min (ci-runtime-and-cost STANDING FINDINGS). An admitted runner pod was bound within 50 s across a 30-min saturated window (mtvxde acceptance window, 2026-11-13). A job with reserved, unlent admission capacity therefore starts inside 5 minutes; today's wait exceeded 11 minutes with no ceiling. Work item livespec-dev-tooling-ehnjlt (stop-the-line for the expedited incident lane) carries the implementation.

### Proposed Changes

### SPECIFICATION/contracts.md §"Expedited incident execution"

Insert the following paragraphs after the paragraph that begins "Repair output MUST contain a legal adjacent code/test comment":

While incident mode is enabled for this repository, this repository's `incident-ci` job, and every other job of its gating workflow that reads the incident observer (`LIVESPEC_INCIDENT_OBSERVER_URL`), MUST run on self-hosted capacity that reaches the incident observer. It MUST NOT be routed to GitHub-hosted capacity while incident mode is enabled for this repository, and `CI_INCIDENT_RUNNER_LABELS` MUST then be set to a target that reaches the incident observer. Such a job MUST route through the `CI_INCIDENT_RUNNER_LABELS` repository variable, read at its `runs-on` ahead of `CI_RUNNER_LABELS`. `CI_INCIDENT_RUNNER_LABELS` serves every pull request, incident or not, and it is not the expedited lane.

There are deliberately TWO routing variables here, because they route different jobs for different reasons. An expedited incident IS a stop-the-line event, so the admission lane is named for stop-the-line and serves both kinds of designated run:
- `CI_INCIDENT_RUNNER_LABELS` routes `incident-ci` and `check-metadata` (and any other job that reads the incident observer) on EVERY pull request, incident or not. Its purpose is TAILNET REACH: those jobs read the incident observer, which GitHub-hosted runners cannot reach.
- `CI_RUNNER_LABELS_STOP_THE_LINE` routes the gating jobs of a DESIGNATED pull-request run only, where a designated run is an expedited-incident or a stop-the-line pull request (both defined below). Its purpose is ADMISSION PRIORITY: it puts the designated run's required checks on reserved capacity, ahead of ordinary pull-request traffic.

The two MUST NOT be consolidated into one variable, and a duplication or consolidation check MUST NOT merge them. Pointing the reach variable at the reserved lane would move every pull request's `incident-ci` and `check-metadata` legs onto it, which consumes the reservation. Reading only the lane variable would leave an ordinary pull request's observer-reading jobs with no reach-guaranteed target.

A pull-request run is DESIGNATED when its pull request has a same-repository head and carries either of these issue labels:
- `expedited-incident-response`, the trusted incident label. That makes it an EXPEDITED-INCIDENT pull request. Routing reads the label's presence only; the incident arm is not consulted.
- `stop-the-line`. That makes it a STOP-THE-LINE pull request, for example a revert that lifts a fleet-wide factory stop, or a red-master fix-forward whose coverage legs gate the merge.

Applying or removing the forge label `stop-the-line` is reserved to legacy-coordinator-agent BY CONVENTION. Every fleet session acts under one forge identity, so the forge cannot enforce it.
- The coordinator MUST record each designation and its reason on the pull request's work item, or, with none, on its own plan epic. Routing never reads that record.
- The coordinator's tick MUST list every open pull request that carries `stop-the-line` with no such record, and then remove the label or record the designation.
- An undue designation uses only the lane's own quota, which lends nothing, so it never harms ordinary traffic. It can delay a real incident.

Adding `stop-the-line` MUST take effect on the pull request's newest CI run on its current head by cancelling and re-running that run, as the incident label workflow does for the incident label.

Every gating job of a designated run whose `runs-on` reads a repository variable MUST run on a dedicated self-hosted runner set, the EXPEDITED LANE, named through the `CI_RUNNER_LABELS_STOP_THE_LINE` repository variable.
- That includes `incident-ci`, `check-metadata`, the `CI_PYTHON_RUNNER_LABELS` jobs and every coverage leg that is not omitted.
- A job whose `runs-on` names GitHub-hosted capacity literally, reading no variable, keeps that routing. The route job is one such job.
- The variable MUST be read as the first pull-request term of each such job's `runs-on`: after the push-guarded `CI_RUNNER_LABELS_MASTER` term and ahead of every other term, including `CI_PYTHON_RUNNER_LABELS`, `CI_COVERAGE_RUNNER_LABELS`, `CI_INCIDENT_RUNNER_LABELS` and `CI_RUNNER_LABELS_PRIORITY`, with the hosted literal last.
- It MUST be read only when the route job (constraints.md §"CI matrix shape") reports the run as designated.

The route job MUST decide designation from the pull request's ISSUE labels, read through the forge when the job runs and never from the event payload. These are not ARC runner labels, and the route job never probes runner labels. A re-run keeps its original event payload, and the incident label workflow starts the run in which the label first takes effect as a re-run.

When the route job cannot read the issue labels after the forge-read retries this section requires, it MUST report the run as not designated, so that every job keeps its ordinary routing. That fallback is DEGRADED SERVICE, not a pass: a designated run whose label read failed waits in ordinary pull-request traffic, which is the queue this lane exists to remove. So it MUST NOT be silent:
- On every such fallback the route job MUST emit a GitHub Actions warning annotation and write one line to the run's step summary. Each MUST name the failed read (the pull request number and the forge call), the attempts made, and the last HTTP status or `none`, and MUST state that the run was routed as an ordinary pull request.
- The route job MUST then conclude `failure`.
- It MUST write its outputs before the step that fails. A downstream job still reads the outputs a failed job wrote before its failing step, so every gating job sees the not-designated output and keeps its ordinary routing.
- Every gating job that needs the route job MUST carry `if: ${{ !cancelled() }}` (or a stricter condition that still includes it), so a `failure` of the route job never skips it.
- The route job MUST NOT be among the needs of the aggregate gate job, so its `failure` signals the degraded fallback without blocking the merge.

The expedited lane MUST meet all of the following:
- Its runners MUST reach the incident observer.
- It MUST serve no job of a run that is not designated. No gating job of such a run, including `incident-ci`, `check-metadata` and the coverage legs, MAY read `CI_RUNNER_LABELS_STOP_THE_LINE`.
- Admission to it MUST NOT evict a running job of any queue. A full expedited lane makes the next designated job wait for a designated job to finish, never for an ordinary one.

The expedited lane's ClusterQueue MUST be a member of the runner pool's cohort, with `lendingLimit` 0 on its churn-slot quota and preemption `Never` on all three policies.
- Its nominal quota therefore counts toward the cohort sum that non-functional-requirements.md §"Runner-pool node rebuild recipe" equates with the nodes' declared capacity. That quota is donated from another queue's quota in the Kueue derivation record.
- It MAY borrow idle cohort capacity.
- Its quota MUST equal at least the number of jobs in one designated run's required-check graph that run on self-hosted capacity, counted from the gating workflow. A change to that workflow that raises the count MUST raise the quota in the same change.
- Its scale set's `maxRunners` MUST be at least that quota.
- The reserved slots stay idle while no designated run is queued, and that cost is accepted.

When designated work exceeds the quota, the 5-minute bound does not hold for the excess jobs. That is DEGRADED SERVICE: a fleet trigger MUST fire when the expedited lane's ClusterQueue has had a pending workload for more than 5 minutes, naming the queue and its pending and admitted counts.

While the expedited lane's reserved quota has room, every job a designated run routes to the lane MUST start on a runner within 5 minutes of being queued. Its start MUST NOT wait on any ordinary pull-request job starting or completing: it MUST start within 5 minutes of being queued even when no ordinary pull-request job of this repository starts or completes in that time. Ordinary pull-request jobs MUST keep starting and completing on their own labels while a designated job is queued or running.

A `push` or `merge_group` event MUST NOT read `CI_RUNNER_LABELS_STOP_THE_LINE`. If stale-base-merge-options adopts a merge queue, a designated pull request's `merge_group` run would go back into ordinary traffic. That is revisited when a merge queue is adopted.

While `CI_RUNNER_LABELS_STOP_THE_LINE` is unset or empty, a designated run's jobs MUST route exactly as an ordinary pull request's do. Deleting the variable is the manual revert. On such a run the route job MUST emit a warning annotation and a step-summary line stating that the run is designated but `CI_RUNNER_LABELS_STOP_THE_LINE` is unset, so it routed as ordinary.

In the paragraph that begins "Every forge call that the `incident-ci` job, the `ci-green` job and the incident label workflow", add the route job's read of the pull request's issue labels to the calls the rule covers. In the trust-boundary paragraph that begins "This repository's `incident-ci` and `ci-green` jobs already check the tree out", add: "The route job runs on GitHub-hosted capacity and checks nothing out, so it MUST reference the `forge-read` Action at a release tag of this library, as the incident label workflow does."

### SPECIFICATION/contracts.md §"CI priority record"

Replace the sentence that begins "This library MUST ship the route job as a reusable composite Action whose only inputs are" with:

"This library MUST ship the route job as a reusable composite Action whose inputs are `CI_PRIORITY_RECORD`, the run's event and, for a pull-request run, a token able to read the pull request's issue labels, and whose outputs are the run's band, computed as constraints.md §"CI matrix shape" states, and whether the run is designated (§"Expedited incident execution")."

### SPECIFICATION/constraints.md §"CI matrix shape"

In the paragraph that begins "The route job MUST meet all of the following:", replace the bullet "It MUST be a pure function of `CI_PRIORITY_RECORD` and the run's event, and it MUST NOT probe runner capacity, runner labels or runner health." with:

- It MUST be a pure function of `CI_PRIORITY_RECORD`, the run's event and, for a pull-request run, the pull request's current issue labels read through the forge (contracts.md §"Expedited incident execution"). It MUST NOT probe runner capacity, ARC runner labels or runner health.
- For a pull-request run it MUST report whether the run is DESIGNATED (an expedited-incident or stop-the-line pull request), as contracts.md §"Expedited incident execution" defines.

Replace the sentence "The priority variables, the band output and the existing variables together, with the inline fallback, are the entire routing contract." with:

"The priority variables, the band output, the tailnet-reach variable `CI_INCIDENT_RUNNER_LABELS`, the stop-the-line lane variable `CI_RUNNER_LABELS_STOP_THE_LINE` with the route job's designated output (contracts.md §"Expedited incident execution"), and the existing variables together, with the inline fallback, are the entire routing contract."

The inline hosted literal MUST stay the LAST term of every gating job's `runs-on`, including the incident and stop-the-line terms.

### SPECIFICATION/scenarios.md

Add these scenarios after "## Scenario: an expedited PR defers coverage and spec work while master runs normally":

## Scenario: an expedited incident's required checks start on the expedited lane ahead of queued pull-request traffic

Given `CI_RUNNER_LABELS_STOP_THE_LINE` names the expedited lane and its reserved quota has room

And the repository's pull-request runner labels have ordinary pull-request jobs queued and not started

When an expedited-incident pull request's run queues its gating jobs, `incident-ci` and every coverage leg not omitted included

Then every one of those jobs whose `runs-on` reads a repository variable MUST run on the expedited lane and MUST start within 5 minutes of being queued

And no such job's start MUST wait on an ordinary pull-request job starting or completing

And those ordinary pull-request jobs MUST keep starting and completing on their own labels

## Scenario: an incident label added after the run started routes the re-run's jobs to the expedited lane

Given a pull request whose CI run was created without the `expedited-incident-response` label

When the label is added and the incident label workflow cancels and re-runs that run

Then the re-run's route job MUST read the issue label through the forge and report the run as designated

And every gating job of the re-run whose `runs-on` reads a repository variable MUST run on the expedited lane that `CI_RUNNER_LABELS_STOP_THE_LINE` names

## Scenario: an incident route job whose label read fails warns and routes the run as ordinary

Given the route job's read of a pull request's issue labels fails after the forge-read retries

When the route job decides the run's routing

Then it MUST report the run as not designated, so every job of the run routes as an ordinary pull request's does

And it MUST emit a GitHub Actions warning annotation naming the failed read, the attempts made and the last HTTP status

And it MUST write one step-summary line naming the same failed read and stating that the run was routed as an ordinary pull request

And the route job MUST conclude `failure` while the aggregate gate job's verdict does not depend on it

And that run MUST NOT be reported as having taken the expedited lane

## Scenario: a coordinator-designated stop-the-line pull request's required checks run on the expedited lane ahead of pull-request traffic

Given `CI_RUNNER_LABELS_STOP_THE_LINE` names the expedited lane and its reserved quota has room

And the repository's pull-request runner labels, coverage included, have ordinary pull-request jobs queued and not started

And legacy-coordinator-agent has labelled a same-repository pull request `stop-the-line` and recorded the designation on its work item

When the label is added while that pull request's newest run on its current head is queued or running

Then that run MUST be cancelled and re-run, and the re-run's route job MUST report the run as designated

And every gating job of the re-run whose `runs-on` reads a repository variable, coverage legs included, MUST run on the expedited lane and MUST start within 5 minutes of being queued

And no such job's start MUST wait on an ordinary pull-request job starting or completing

And when the label is removed, the next run of that pull request MUST route every job exactly as an ordinary pull request's

## Scenario: an ordinary pull request's jobs never run on the expedited lane

Given `CI_RUNNER_LABELS_STOP_THE_LINE` names the expedited lane

When a pull request with neither the `expedited-incident-response` nor the `stop-the-line` label runs its gating workflow

Then its `incident-ci`, `check-metadata` and every other gating job MUST NOT run on the expedited lane

And its `incident-ci` and `check-metadata` jobs MUST still run on the target `CI_INCIDENT_RUNNER_LABELS` names, which reaches the incident observer

And every job of a `push` or `merge_group` run MUST NOT run on the expedited lane

### Revise-time co-edits

At revise time, each of the five new scenario headings MUST be added to tests/heading-coverage.json in the same commit. Each is a spec-first TODO row owned by livespec-dev-tooling-ehnjlt, carrying `"work_item": "livespec-dev-tooling-ehnjlt"`, naming the integration tier, and registered in the heading-coverage debt register with `just generate-heading-coverage-debt-register`.

## Proposal: No repository's incident lane is enabled while its incident-ci routes to GitHub-hosted capacity

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add an adopter precondition to contracts.md §"Expedited incident execution": the fleet audit MUST NOT list a repository ready for incident enablement while that repository's `incident-ci` job, or any job that reads the incident observer, resolves its `runs-on` to GitHub-hosted capacity under the repository's current variables. Add one scenario.

### Motivation

GitHub-hosted runners cannot reach the tailnet incident observer, so an `incident-ci` job routed there can never decide an incident.
- A read-only fleet survey on 2026-11-13 found that livespec-orchestrator-beads-fabro's `incident-ci` reads `CI_RUNNER_LABELS`, which is `["ubuntu-latest"]` there (hybrid since 2026-11-04), so its incident lane would route to hosted runners.
- livespec and livespec-overseer route `incident-ci` on their shared pull-request label.
- On 2026-11-11 this repository's own hosted flip broke `incident-ci` (stop-the-line livespec-dev-tooling-bqnzcm, run 43022867200) until the `CI_INCIDENT_RUNNER_LABELS` carve-out (livespec-dev-tooling-onk27y) landed.

The precondition makes that failure impossible to enable, rather than something each adopter rediscovers. legacy-coordinator-agent required it on 2026-11-13 as part of the incident-lane design.

### Proposed Changes

### SPECIFICATION/contracts.md §"Expedited incident execution"

Append, after the paragraphs that define the expedited lane:

No repository's incident mode MAY be enabled while its `incident-ci` job, or any other job of its gating workflow that reads the incident observer, would run on GitHub-hosted capacity.
- The fleet audit MUST read each consumer's gating workflow and repository variables.
- It MUST NOT list a repository ready for incident enablement while that job's `runs-on`, resolved for a pull-request run under the current variables, names GitHub-hosted capacity.
- When it refuses on this ground, it MUST name the repository, the job and the resolved labels.
- This precondition MUST be checked before every enablement and MUST NOT be waived per repository.

### SPECIFICATION/scenarios.md

Add after "## Scenario: the incident fleet audit command refuses enablement for a consumer without verified serving evidence":

## Scenario: the incident fleet audit refuses enablement for a consumer whose incident-ci routes to hosted capacity

Given a consumer repository whose `incident-ci` job's `runs-on` resolves, under its current repository variables, to GitHub-hosted capacity

When the incident fleet audit evaluates that repository for incident enablement

Then the audit MUST NOT list it ready for enablement

And its refusal MUST name the repository, the `incident-ci` job and the resolved hosted labels

And once the repository routes `incident-ci` to a target that reaches the incident observer, this precondition MUST no longer refuse it

### Revise-time co-edits

At revise time this scenario heading MUST be added to tests/heading-coverage.json as a spec-first TODO row owned by livespec-dev-tooling-ehnjlt, carrying `"work_item": "livespec-dev-tooling-ehnjlt"`, naming the integration tier, and registered in the heading-coverage debt register with `just generate-heading-coverage-debt-register`.
