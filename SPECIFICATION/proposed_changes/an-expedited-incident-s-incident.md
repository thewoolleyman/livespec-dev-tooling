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

Amend contracts.md §"Expedited incident execution" so that every gating job of a designated pull-request run runs on a dedicated self-hosted expedited lane. A designated run is an expedited-incident pull request, or a stop-the-line pull request that legacy-coordinator-agent labels `stop-the-line`. That set's admission capacity is reserved for it, and the job starts within 5 minutes of being queued even while the pull-request runner label is saturated. It starts ahead of earlier-queued ordinary pull-request jobs, and those jobs are unaffected. Ratify the existing `CI_INCIDENT_RUNNER_LABELS` tailnet carve-out, which no clause states today. Add a separate lane variable, read only when the run is an expedited-incident pull request, as the route job reports from the pull request's current labels. Amend constraints.md §"CI matrix shape" so the routing contract names both variables and the route job's incident output. State why the two incident variables exist and forbid consolidating them. Make a failed label read a loud, degraded fallback. Widen the lane to every required check of a designated run: an expedited-incident pull request, or a stop-the-line pull request the coordinator labels. Add five scenarios.

### Motivation

On 2026-11-13 livespec-dev-tooling master was red (z5cjph's run 43372854805 failed). Incident 3hilpy's EXPEDITED_INCIDENT_RESPONSE fix-forward (PR #4466, run 43377282930) had every check green except `incident-ci`, which sat queued from 06:14:13Z while master merges were held on it. It was behind 12 queued jobs on the label `livespec-dev-tooling-k3s`: ordinary PR coverage, red-green-replay and incident-ci legs of eight other pull requests. The pool was saturated at 20/20 runners, and `livespec-dev-tooling-cq` is BestEffortFIFO with no runner priority class. The only WorkloadPriorityClass is `gate-priority`, which orders gate Jobs only. No committed route existed, so a seat cancelled three low-band runs by hand to move the job up.

The same morning showed the same starvation for stop-the-line carriers. legacy-coordinator-agent required, on 2026-11-13, that the lane also cover them:
- livespec-orchestrator-beads-fabro#5138, the revert that lifts the fleet-wide factory stop: three per-file-coverage shards queued from 06:30:07Z behind about 12 jobs on `livespec-orchestrator-k3s`.
- livespec-dev-tooling#4466 (3hilpy): its coverage legs pending behind ordinary pull-request traffic.

A stop-the-line pull request is designated the same way an expedited incident is, by a label, `stop-the-line`, which only the coordinator applies and records.

ARC runners are generic, so a pod-level Kueue priority cannot target one job: only a separate label routes a job to reserved capacity. The dev-tooling master lane (`livespec-dev-master-k3s`, `CI_RUNNER_LABELS_MASTER`, its own values file and its own LocalQueue/ClusterQueue in DERIVATION.md) already proves that pattern. legacy-coordinator-agent decided this design on 2026-11-13: a dedicated incident runner set and label with its own LocalQueue/ClusterQueue and reserved nominal quota, mirroring the master lane, with preemption staying never.

The expedited lane cannot reuse `CI_INCIDENT_RUNNER_LABELS` as its selector. That variable already routes `incident-ci` and `check-metadata` for EVERY pull request (it is the tailnet carve-out, since both jobs read the incident observer). Pointing it at a reserved set would move all ordinary pull-request metadata traffic onto the incident lane. So the lane needs its own variable, read only for an expedited-incident pull request.

Whether a run is an expedited-incident pull request cannot be read from the event payload's labels. The incident label workflow re-runs the CI run when the label is added, and a re-run keeps the ORIGINAL event payload. The route job runs again on a re-run and reads the pull request's current labels through the forge, so its output reflects the label.

The 5-minute bound: unsaturated k3s queue time measures p50 0.3 min and p95 4.4 min (ci-runtime-and-cost STANDING FINDINGS). An admitted runner pod was bound within 50 s across a 30-min saturated window (mtvxde acceptance window, 2026-11-13). A job with reserved, unlent admission capacity therefore starts inside 5 minutes; today's wait exceeded 11 minutes with no ceiling. Work item livespec-dev-tooling-ehnjlt (stop-the-line for the expedited incident lane) carries the implementation.

### Proposed Changes

### SPECIFICATION/contracts.md §"Expedited incident execution"

Insert the following paragraphs after the paragraph that begins "Repair output MUST contain a legal adjacent code/test comment":

This repository's `incident-ci` job, and every other job of its gating workflow that reads the incident observer (`LIVESPEC_INCIDENT_OBSERVER_URL`), MUST run on self-hosted capacity that reaches the incident observer, and MUST NOT run on GitHub-hosted capacity, which cannot reach it. Such a job MUST route through the `CI_INCIDENT_RUNNER_LABELS` repository variable, read at its `runs-on` after the push-event `CI_RUNNER_LABELS_MASTER` term and ahead of `CI_RUNNER_LABELS`. `CI_INCIDENT_RUNNER_LABELS` MUST name a target that reaches the incident observer. It serves every pull request, incident or not, and it is not the incident lane.

There are deliberately TWO routing variables here, because they route different jobs for different reasons. An expedited incident IS a stop-the-line event, so the admission lane is named for stop-the-line and serves both kinds of designated run:
- `CI_INCIDENT_RUNNER_LABELS` routes `incident-ci` and `check-metadata` (and any other job that reads the incident observer) on EVERY pull request, incident or not. Its purpose is TAILNET REACH: those jobs read the incident observer, which GitHub-hosted runners cannot reach.
- `CI_STOP_THE_LINE_RUNNER_LABELS` routes every gating job of a DESIGNATED pull-request run only: an expedited-incident pull request, or a stop-the-line pull request (both defined below). Its purpose is ADMISSION PRIORITY: it puts the designated run's required checks on reserved capacity, ahead of ordinary pull-request traffic.

The two MUST NOT be consolidated into one variable, and a duplication or consolidation check MUST NOT merge them. Pointing the reach variable at the reserved lane would move every pull request's `incident-ci` and `check-metadata` legs onto it, which consumes the reservation. Reading only the lane variable would leave an ordinary pull request's observer-reading jobs with no reach-guaranteed target.

A pull-request run is DESIGNATED when its pull request has a same-repository head and carries either label:
- `expedited-incident-response`, the trusted incident label. That makes it an EXPEDITED-INCIDENT pull request.
- `stop-the-line`. That makes it a STOP-THE-LINE pull request, for example a revert that lifts a fleet-wide factory stop, or a red-master fix-forward whose coverage legs gate the merge.

Applying or removing `stop-the-line` is legacy-coordinator-agent's act alone. The coordinator MUST record each designation, with its reason, on the pull request's work item. A pull request that carries `stop-the-line` without such a record MUST be treated as designated all the same, because routing never reads the ledger. The record is how an undue designation is found and removed.

Every gating job of a designated run MUST run on a dedicated self-hosted runner set, the EXPEDITED LANE, named through the `CI_STOP_THE_LINE_RUNNER_LABELS` repository variable. That includes `incident-ci`, `check-metadata` and every coverage leg that is not omitted. The variable MUST be read at each gating job's `runs-on` ahead of `CI_INCIDENT_RUNNER_LABELS` and `CI_RUNNER_LABELS`, and only when the route job (constraints.md §"CI matrix shape") reports the run as designated. It MUST be read ahead of `CI_COVERAGE_RUNNER_LABELS` for the coverage legs.

The route job MUST decide that from the pull request's labels read through the forge when the job runs, never from the event payload. A re-run keeps its original event payload, and the incident label workflow starts the run in which the label first takes effect as a re-run. When the route job cannot read the labels after the forge-read retries this section requires, it MUST report the run as not designated, so that every job keeps its ordinary routing. That fallback is DEGRADED SERVICE, not a pass: a designated run whose label read failed waits in ordinary pull-request traffic, which is the queue this lane exists to remove. So it MUST NOT be silent. On every such fallback the route job MUST emit a GitHub Actions warning annotation and write one line to the run's step summary. Each MUST name the failed read (the pull request number and the forge call), the attempts made, and the last HTTP status or `none`, and MUST state that the run was routed as an ordinary pull request.

The expedited lane MUST meet all of the following:
- Its runners MUST reach the incident observer.
- It MUST serve no job of a run that is not designated. No gating job of such a run, including `incident-ci`, `check-metadata` and the coverage legs, MAY read `CI_STOP_THE_LINE_RUNNER_LABELS`.
- Its admission capacity MUST be reserved for it as nominal quota of its own queue. No other queue's workload MAY be admitted against that quota, so the capacity is never lent away when a designated job arrives.
- That quota MUST hold at least the full required-check graph of one designated run at once, its coverage legs included.
- Admission to it MUST NOT evict a running job of any queue. A full expedited lane makes the next designated job wait for a designated job to finish, never for an ordinary one.

While the pull-request runner labels of this repository have queued jobs and the expedited lane's reserved quota has room, every gating job of a designated run MUST start on a runner within 5 minutes of being queued. It MUST start before every ordinary pull-request job of this repository that was queued before it and has not started. Ordinary pull-request jobs MUST keep starting and completing on their own labels while a designated job is queued or running. A `push` or `merge_group` event MUST NOT read `CI_STOP_THE_LINE_RUNNER_LABELS`.

While `CI_STOP_THE_LINE_RUNNER_LABELS` is unset or empty, a designated run's jobs MUST route exactly as an ordinary pull request's do. Deleting the variable is the manual revert.

### SPECIFICATION/constraints.md §"CI matrix shape"

In the paragraph that begins "The route job MUST meet all of the following:", replace the bullet "It MUST be a pure function of `CI_PRIORITY_RECORD` and the run's event, and it MUST NOT probe runner capacity, runner labels or runner health." with:

- It MUST be a pure function of `CI_PRIORITY_RECORD`, the run's event and, for a pull-request run, the pull request's current labels read through the forge (contracts.md §"Expedited incident execution"). It MUST NOT probe runner capacity, runner labels or runner health.
- For a pull-request run it MUST report whether the run is DESIGNATED (an expedited-incident or stop-the-line pull request), as contracts.md §"Expedited incident execution" defines.

Replace the sentence "The priority variables, the band output and the existing variables together, with the inline fallback, are the entire routing contract." with:

"The priority variables, the band output, the tailnet-reach variable `CI_INCIDENT_RUNNER_LABELS` and the stop-the-line admission variable `CI_STOP_THE_LINE_RUNNER_LABELS`, with the route job's designated output (contracts.md §"Expedited incident execution"), and the existing variables together, with the inline fallback, are the entire routing contract."

The inline hosted literal MUST stay the LAST term of every gating job's `runs-on`, including the incident terms.

### SPECIFICATION/scenarios.md

Add these scenarios after "## Scenario: an expedited PR defers coverage and spec work while master runs normally":

## Scenario: an expedited incident's required checks start on the expedited lane ahead of queued pull-request traffic

Given `CI_STOP_THE_LINE_RUNNER_LABELS` names the expedited lane and its reserved quota has room

And the repository's pull-request runner labels have ordinary pull-request jobs queued and not started

When an expedited-incident pull request's run queues its gating jobs, `incident-ci` and every coverage leg not omitted included

Then every one of those jobs MUST run on the expedited lane and MUST start within 5 minutes of being queued

And each MUST start before every ordinary pull-request job that was queued before it and has not started

And those ordinary pull-request jobs MUST keep starting and completing on their own label

## Scenario: an incident label added by a re-run routes that re-run's jobs to the expedited lane

Given a pull request whose CI run was created without the `expedited-incident-response` label

When the label is added and the incident label workflow re-runs that run

Then the re-run's route job MUST read the label through the forge and report the run as designated

And the re-run's `incident-ci` job MUST run on the expedited lane that `CI_STOP_THE_LINE_RUNNER_LABELS` names

And a route job that cannot read the labels MUST report the run as ordinary, so the job keeps its ordinary routing

## Scenario: an incident route job whose label read fails warns and routes the run as ordinary

Given the route job's read of a pull request's labels fails after the forge-read retries

When the route job decides the run's routing

Then it MUST report the run as not designated, so every job of the run routes as an ordinary pull request's does

And it MUST emit a GitHub Actions warning annotation naming the failed read, the attempts made and the last HTTP status

And it MUST write one step-summary line naming the same failed read and stating that the run was routed as an ordinary pull request

And that run MUST NOT be reported as having taken the expedited lane

## Scenario: a coordinator-designated stop-the-line pull request's required checks run on the expedited lane ahead of pull-request traffic

Given `CI_STOP_THE_LINE_RUNNER_LABELS` names the expedited lane and its reserved quota has room

And the repository's pull-request runner labels, coverage included, have ordinary pull-request jobs queued and not started

And legacy-coordinator-agent has labelled a same-repository pull request `stop-the-line` and recorded the designation on its work item

When that pull request's run queues its gating jobs, coverage legs included

Then the route job MUST report the run as designated

And every one of those jobs MUST run on the expedited lane and MUST start within 5 minutes of being queued

And each MUST start before every ordinary pull-request job that was queued before it and has not started

And when the label is removed, the next run of that pull request MUST route every job exactly as an ordinary pull request's

## Scenario: an ordinary pull request's jobs never run on the expedited lane

Given `CI_STOP_THE_LINE_RUNNER_LABELS` names the expedited lane

When a pull request with neither the `expedited-incident-response` nor the `stop-the-line` label runs its gating workflow

Then its `incident-ci`, `check-metadata` and every other gating job MUST NOT run on the expedited lane

And its `incident-ci` and `check-metadata` jobs MUST still run on the target `CI_INCIDENT_RUNNER_LABELS` names, which reaches the incident observer

And no job of a `push` or `merge_group` run MUST run on the expedited lane

At revise time, each of the five new scenario headings MUST be added to tests/heading-coverage.json in the same commit, as a spec-first TODO row owned by livespec-dev-tooling-ehnjlt and naming the integration tier, registered in the heading-coverage debt register.

## Proposal: No repository's incident lane is enabled while its incident-ci routes to GitHub-hosted capacity

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add an adopter precondition to contracts.md §"Expedited incident execution": the fleet audit MUST NOT list a repository ready for incident enablement while that repository's `incident-ci` job, or any job that reads the incident observer, resolves its `runs-on` to GitHub-hosted capacity under the repository's current variables. Add one scenario.

### Motivation

GitHub-hosted runners cannot reach the tailnet incident observer, so an `incident-ci` job routed there can never decide an incident. A read-only fleet survey on 2026-11-13 found that livespec-orchestrator-beads-fabro's `incident-ci` reads `CI_RUNNER_LABELS`, which is `["ubuntu-latest"]` there (hybrid since 2026-11-04). Its incident lane would therefore route to hosted runners. livespec and livespec-overseer route `incident-ci` on their shared pull-request label. On 2026-11-11 this repository's own hosted flip broke `incident-ci` (stop-the-line livespec-dev-tooling-bqnzcm, run 43022867200) until the `CI_INCIDENT_RUNNER_LABELS` carve-out (livespec-dev-tooling-onk27y) landed. The precondition makes that failure impossible to enable rather than something each adopter rediscovers. legacy-coordinator-agent required it on 2026-11-13 as part of the incident-lane design.

### Proposed Changes

### SPECIFICATION/contracts.md §"Expedited incident execution"

Append, after the paragraphs that define the expedited lane:

No repository's incident lane MAY be enabled while its `incident-ci` job, or any other job of its gating workflow that reads the incident observer, would run on GitHub-hosted capacity. The fleet audit MUST read each consumer's gating workflow and repository variables. It MUST NOT list a repository ready for incident enablement while that job's `runs-on`, resolved for a pull-request run under the current variables, names GitHub-hosted capacity. When it refuses on this ground, it MUST name the repository, the job and the resolved labels. This precondition MUST be checked before every enablement and MUST NOT be waived per repository.

### SPECIFICATION/scenarios.md

Add after "## Scenario: the incident fleet audit command refuses enablement for a consumer without verified serving evidence":

## Scenario: the incident fleet audit refuses enablement for a consumer whose incident-ci routes to hosted capacity

Given a consumer repository whose `incident-ci` job's `runs-on` resolves, under its current repository variables, to GitHub-hosted capacity

When the incident fleet audit evaluates that repository for incident enablement

Then the audit MUST NOT list it ready for enablement

And its refusal MUST name the repository, the `incident-ci` job and the resolved hosted labels

And once the repository routes `incident-ci` to a target that reaches the incident observer, this precondition MUST no longer refuse it

At revise time this scenario heading MUST be added to tests/heading-coverage.json as a spec-first TODO row owned by livespec-dev-tooling-ehnjlt, naming the integration tier, and registered in the debt register.
