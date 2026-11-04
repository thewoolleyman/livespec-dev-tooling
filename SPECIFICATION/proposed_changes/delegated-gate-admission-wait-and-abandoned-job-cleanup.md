---
topic: delegated-gate-admission-wait-and-abandoned-job-cleanup
author: claude-opus-5-5
created_at: 2026-11-04T22:30:03Z
---

## Proposal: Delegated gate Jobs: admission wait outside the poll budget, abandoned Jobs deleted

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds two bullets to contracts.md §"Delegated pre-push gate", the gate-client contract every delegated gate shares (pre-push, commit-time replay, pre-commit aggregate, gate-runner runs). The first bullet starts a submitted gate Job's poll budget at Kueue admission rather than at submission, and bounds the wait before admission separately. The second requires the client to delete a submitted Job it stops waiting on, and grants the gates credential delete on Jobs in the gates namespace for that. Three scenarios state the behaviour. The pre-commit Verdict bullet's existing duty to print the gate Job's name is not changed.

### Motivation

Measured by plan dev-host-test-gate-load (epic livespec-dev-tooling-6vuiwe) on 2026-11-03 at 03:49Z. The gates ClusterQueue admitted three 5-CPU gate Jobs against its 15-CPU quota, so 3 Jobs were Running and 13 were Suspended, the oldest for 36 minutes. gate_remote_client._await_terminal_state spends its 3600 s poll budget from submission, so queue time counts against it. When the budget runs out the client returns no verdict and deletes nothing, because gates-rbac.yaml grants the gate-submitter credential no delete verb. A delegated pre-commit then runs its whole aggregate on the dev host, while the abandoned Job stays queued and runs on the cluster later anyway: double load, which the plan's dev-host load target forbids. The ratified text says only that a Job that 'is lost or times out' is an absent verdict. It does not say when the budget starts, bound the admission wait, or require an abandoned Job to be removed. So the fix work items (livespec-dev-tooling-t5ct2q, -dtaiyu and -f2dgn6, regroomed from -wdte2s) add behaviour and wait on this proposal (legacy-coordinator-agent, 2026-11-04).

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated pre-push gate", insert after the **Credential use.** bullet:

- **Admission wait.** The gate client's poll budget for a submitted gate Job MUST start when Kueue admits the Job, that is, when the Job is no longer suspended. Time the Job spends suspended awaiting admission MUST NOT count toward that budget. The wait before admission MUST have its own bound, the admission bound, which defaults to 1800 seconds. The poll budget after admission keeps its default of 3600 seconds. A gate request MAY override either bound. A Job still suspended when the admission bound runs out is a Job that timed out, so the run has no verdict. In that case the client's output MUST name the Job and say that it was not admitted. A run that stops waiting after admission without a verdict MUST name the Job and say that it was admitted.
- **Abandoned Job.** When the gate client stops waiting on a submitted gate Job without a verdict, it MUST delete that Job, through `with-gates-kubeconfig`, before it returns. The Job then does not run on the cluster after the caller has acted on the absent verdict. A delete the cluster refuses or that fails MUST be reported in the client's output, and it MUST NOT turn the absent verdict into a verdict. The gates credential MUST therefore grant delete on Jobs in the `gates` namespace, and MUST NOT grant delete on any other resource.

These bullets bind every delegation that uses the gate client: §"Delegated pre-push gate", §"Delegated commit-time replay test runs", §"Delegated pre-commit aggregate" and §"Delegated gate-runner runs". Each caller's own absent-verdict rule still decides what happens next: pre-push refuses, and the pre-commit aggregate and replay legs gate locally.

In SPECIFICATION/scenarios.md, add three scenarios after §"Scenario: a delegated pre-commit aggregate with no cluster verdict gates locally":

## Scenario: a delegated gate Job's Kueue admission wait does not consume its poll budget

Given a delegating host that submits a gate Job to the `gates` namespace
And the Job stays suspended awaiting Kueue admission for less than the admission bound
When Kueue admits the Job and the Job reaches a verdict within the poll budget measured from admission
Then the gate client MUST report that verdict
And the time the Job spent suspended MUST NOT count toward the poll budget

## Scenario: a delegated gate Job never admitted within the admission bound ends without a verdict and is deleted

Given a delegating host that submits a gate Job to the `gates` namespace
When the Job is still suspended awaiting Kueue admission when the admission bound runs out
Then the gate run MUST have no verdict
And the client's output MUST name the Job and say that it was not admitted
And the client MUST delete the Job before it returns

## Scenario: a gate client that stops waiting on an admitted gate Job deletes it

Given a delegating host whose submitted gate Job was admitted
When the poll budget measured from admission runs out before the Job reaches a verdict
Then the gate run MUST have no verdict
And the client's output MUST name the Job and say that it was admitted
And the client MUST delete the Job before it returns
And a refused delete MUST be reported in the output without changing the absent verdict

The revise that accepts this proposal MUST add the three new `## Scenario:` headings to tests/heading-coverage.json in the same commit.
