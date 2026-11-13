---
topic: an-expedited-incident-s-incident
author: claude-opus-5-5
created_at: 2026-11-13T06:34:42Z
---

## Proposal: An expedited incident's incident-ci job runs on a dedicated incident runner lane admitted ahead of pull-request traffic

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md §"Expedited incident execution" so that an expedited-incident pull request's `incident-ci` job runs on a dedicated self-hosted incident runner set. That set's admission capacity is reserved for it, and the job starts within 5 minutes of being queued even while the pull-request runner label is saturated. It starts ahead of earlier-queued ordinary pull-request jobs, and those jobs are unaffected. Ratify the existing `CI_INCIDENT_RUNNER_LABELS` tailnet carve-out, which no clause states today. Add a separate lane variable, read only when the run is an expedited-incident pull request, as the route job reports from the pull request's current labels. Amend constraints.md §"CI matrix shape" so the routing contract names both variables and the route job's incident output. Add three scenarios.

### Motivation

On 2026-11-13 livespec-dev-tooling master was red (z5cjph's run 43372854805 failed). Incident 3hilpy's EXPEDITED_INCIDENT_RESPONSE fix-forward (PR #4466, run 43377282930) had every check green except `incident-ci`, which sat queued from 06:14:13Z while master merges were held on it. It was behind 12 queued jobs on the label `livespec-dev-tooling-k3s`: ordinary PR coverage, red-green-replay and incident-ci legs of eight other pull requests. The pool was saturated at 20/20 runners, and `livespec-dev-tooling-cq` is BestEffortFIFO with no runner priority class. The only WorkloadPriorityClass is `gate-priority`, which orders gate Jobs only. No committed route existed, so a seat cancelled three low-band runs by hand to move the job up.

ARC runners are generic, so a pod-level Kueue priority cannot target one job: only a separate label routes a job to reserved capacity. The dev-tooling master lane (`livespec-dev-master-k3s`, `CI_RUNNER_LABELS_MASTER`, its own values file and its own LocalQueue/ClusterQueue in DERIVATION.md) already proves that pattern. legacy-coordinator-agent decided this design on 2026-11-13: a dedicated incident runner set and label with its own LocalQueue/ClusterQueue and reserved nominal quota, mirroring the master lane, with preemption staying never.

The incident lane cannot reuse `CI_INCIDENT_RUNNER_LABELS` as its selector. That variable already routes `incident-ci` and `check-metadata` for EVERY pull request (it is the tailnet carve-out, since both jobs read the incident observer). Pointing it at a reserved set would move all ordinary pull-request metadata traffic onto the incident lane. So the lane needs its own variable, read only for an expedited-incident pull request.

Whether a run is an expedited-incident pull request cannot be read from the event payload's labels. The incident label workflow re-runs the CI run when the label is added, and a re-run keeps the ORIGINAL event payload. The route job runs again on a re-run and reads the pull request's current labels through the forge, so its output reflects the label.

The 5-minute bound: unsaturated k3s queue time measures p50 0.3 min and p95 4.4 min (ci-runtime-and-cost STANDING FINDINGS). An admitted runner pod was bound within 50 s across a 30-min saturated window (mtvxde acceptance window, 2026-11-13). A job with reserved, unlent admission capacity therefore starts inside 5 minutes; today's wait exceeded 11 minutes with no ceiling. Work item livespec-dev-tooling-ehnjlt (stop-the-line for the expedited incident lane) carries the implementation.

### Proposed Changes

### SPECIFICATION/contracts.md §"Expedited incident execution"

Insert the following paragraphs after the paragraph that begins "Repair output MUST contain a legal adjacent code/test comment":

This repository's `incident-ci` job, and every other job of its gating workflow that reads the incident observer (`LIVESPEC_INCIDENT_OBSERVER_URL`), MUST run on self-hosted capacity that reaches the incident observer, and MUST NOT run on GitHub-hosted capacity, which cannot reach it. Such a job MUST route through the `CI_INCIDENT_RUNNER_LABELS` repository variable, read at its `runs-on` after the push-event `CI_RUNNER_LABELS_MASTER` term and ahead of `CI_RUNNER_LABELS`. `CI_INCIDENT_RUNNER_LABELS` MUST name a target that reaches the incident observer. It serves every pull request, incident or not, and it is not the incident lane.

An expedited-incident pull request's `incident-ci` job MUST run on a dedicated self-hosted incident runner set, named through the `CI_INCIDENT_LANE_RUNNER_LABELS` repository variable. An expedited-incident pull request is a pull request that carries the trusted incident label `expedited-incident-response` and has a same-repository head. The variable MUST be read at the job's `runs-on` ahead of `CI_INCIDENT_RUNNER_LABELS`, and only when the route job (constraints.md §"CI matrix shape") reports the run as an expedited-incident pull request.

The route job MUST decide that from the pull request's labels read through the forge when the job runs, never from the event payload. A re-run keeps its original event payload, and the incident label workflow starts the run in which the label first takes effect as a re-run. When the route job cannot read the labels after the forge-read retries this section requires, it MUST report the run as not an expedited-incident pull request, so that the job keeps its ordinary routing.

The incident runner set MUST meet all of the following:
- Its runners MUST reach the incident observer.
- It MUST serve no job of an ordinary pull request. An ordinary pull request's `incident-ci`, `check-metadata` and every other gating job MUST NOT read `CI_INCIDENT_LANE_RUNNER_LABELS`.
- Its admission capacity MUST be reserved for it as nominal quota of its own queue. No other queue's workload MAY be admitted against that quota, so the capacity is never lent away when an incident job arrives.
- Admission to it MUST NOT evict a running job of any queue. A full incident lane makes the next incident job wait for an incident job to finish, never for an ordinary job.

While the pull-request runner label of this repository has queued jobs, an expedited-incident pull request's `incident-ci` job MUST start on a runner within 5 minutes of being queued. It MUST start before every ordinary pull-request job of this repository that was queued before it and has not started. Ordinary pull-request jobs MUST keep starting and completing on their own label while that job is queued or running. A gating job of an expedited-incident pull request other than `incident-ci` MAY also read `CI_INCIDENT_LANE_RUNNER_LABELS`. A `push` or `merge_group` event MUST NOT read it.

While `CI_INCIDENT_LANE_RUNNER_LABELS` is unset or empty, an expedited-incident pull request's jobs MUST route exactly as an ordinary pull request's do. Deleting the variable is the manual revert.

### SPECIFICATION/constraints.md §"CI matrix shape"

In the paragraph that begins "The route job MUST meet all of the following:", replace the bullet "It MUST be a pure function of `CI_PRIORITY_RECORD` and the run's event, and it MUST NOT probe runner capacity, runner labels or runner health." with:

- It MUST be a pure function of `CI_PRIORITY_RECORD`, the run's event and, for a pull-request run, the pull request's current labels read through the forge (contracts.md §"Expedited incident execution"). It MUST NOT probe runner capacity, runner labels or runner health.
- For a pull-request run it MUST report whether the run is an expedited-incident pull request, as contracts.md §"Expedited incident execution" defines.

Replace the sentence "The priority variables, the band output and the existing variables together, with the inline fallback, are the entire routing contract." with:

"The priority variables, the band output, the incident variables `CI_INCIDENT_RUNNER_LABELS` and `CI_INCIDENT_LANE_RUNNER_LABELS` with the route job's incident output (contracts.md §"Expedited incident execution"), and the existing variables together, with the inline fallback, are the entire routing contract."

The inline hosted literal MUST stay the LAST term of every gating job's `runs-on`, including the incident terms.

### SPECIFICATION/scenarios.md

Add these scenarios after "## Scenario: an expedited PR defers coverage and spec work while master runs normally":

## Scenario: an expedited incident's incident-ci starts on the incident lane ahead of queued pull-request traffic

Given `CI_INCIDENT_LANE_RUNNER_LABELS` names the dedicated incident runner set and its reserved quota has room

And the repository's pull-request runner label has ordinary pull-request jobs queued and not started

When an expedited-incident pull request's run queues its `incident-ci` job

Then that job MUST run on the incident runner set and MUST start within 5 minutes of being queued

And it MUST start before every ordinary pull-request job that was queued before it and has not started

And those ordinary pull-request jobs MUST keep starting and completing on their own label

## Scenario: an incident label added by a re-run routes that re-run's incident-ci to the incident lane

Given a pull request whose CI run was created without the `expedited-incident-response` label

When the label is added and the incident label workflow re-runs that run

Then the re-run's route job MUST read the label through the forge and report the run as an expedited-incident pull request

And the re-run's `incident-ci` job MUST run on the incident runner set that `CI_INCIDENT_LANE_RUNNER_LABELS` names

And a route job that cannot read the labels MUST report the run as ordinary, so the job keeps its ordinary routing

## Scenario: an ordinary pull request's jobs never run on the incident lane

Given `CI_INCIDENT_LANE_RUNNER_LABELS` names the dedicated incident runner set

When a pull request without the `expedited-incident-response` label runs its gating workflow

Then its `incident-ci`, `check-metadata` and every other gating job MUST NOT run on the incident runner set

And its `incident-ci` and `check-metadata` jobs MUST still run on the target `CI_INCIDENT_RUNNER_LABELS` names, which reaches the incident observer

And no job of a `push` or `merge_group` run MUST run on the incident runner set

At revise time, each new scenario heading MUST be added to tests/heading-coverage.json in the same commit, as a spec-first TODO row owned by livespec-dev-tooling-ehnjlt and naming the integration tier, registered in the heading-coverage debt register.

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

Append, after the paragraphs that define the incident runner set:

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
