---
topic: the-pre-push-gate-confirms
author: claude-opus-5-5
created_at: 2026-11-11T13:32:51Z
---

## Proposal: The pre-push gate confirms reused delegated pre-commit evidence against the cluster's record of its gate Job

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a confirmation condition to contracts.md §"Delegated pre-push gate" **Same-tree delegated pre-commit verdict**. Before a push reuses delegated pre-commit evidence, the pre-push gate reads the named gate Job's record from the cluster. It accepts the evidence only when that record shows the Job succeeded, carried the tree the evidence names, and reported the member list the evidence names. When the cluster no longer holds the record, or the record disagrees on its outcome, its tree or its member list, the push gates exactly as it would with no reusable evidence, and a disagreement prints which field disagreed. Two scenarios are added to scenarios.md, one for the missing-record fall-back and one for a disagreeing record.

### Motivation

Carrier: work item livespec-dev-tooling-7uae5p, the hardening follow-up to livespec-dev-tooling-73ocxb (revise v186, proposal pre-push-accepts-a-same-tree-delegated-pre-commit-pass, released in v1.196.0). legacy-coordinator-agent asked whether reused evidence should be confirmed against the cluster's own record of the gate Job, because the fleet's precedent for an exemption is evidence an agent cannot fabricate. Today the pre-push gate trusts a local file, livespec-pre-push-evidence.json, which any process in the worktree can write. The v186 independent reviewer judged that this is not a gate weakening, since the green token is an equally local file, and recommended not adopting the confirmation inside v186. Per the coordinator's rule it was filed as 7uae5p, which needs this propose-change before implementation because it adds a reuse condition to the ratified text. Measured facts this proposal relies on: every gate Job carries the label livespec.gate/tree-hash (ci-runner/k3s/phase2/gates/gate-job-template.yaml); its Complete or Failed condition is in the Job's status; its member list is the LIVESPEC_GATE_MEMBERS line in its pod's log (livespec_dev_tooling/_gate_member_report.py), which the gate client already reads through the gates credential; and a finished Job is kept for one hour (ttlSecondsAfterFinished in the same template), after which the Job and its pod log are gone. The cost is therefore stated plainly: a push made more than about an hour after its delegated pre-commit verdict finds no record and submits a gate Job, as every push did before v186. This proposal does not change the Job's retention; a revise that wants a longer reuse window would change the template's TTL, which is a separate decision. The co-edit of tests/heading-coverage.json for the two new scenarios lies outside the spec target and lands in the revise commit.

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated pre-push gate", bullet **Same-tree delegated pre-commit verdict**, replace the sentences that define when a run qualifies ("A run qualifies only when two things hold. First, ... Second, at push time the pushing worktree is clean and its `HEAD` tree is the tree that evidence names.") with three conditions, adding the third:

> A run qualifies only when three things hold. First, §"Delegated pre-commit aggregate" **Evidence for the pre-push gate** recorded pre-push evidence for it, which names its gate Job in a field of its own. Second, at push time the pushing worktree is clean and its `HEAD` tree is the tree that evidence names. Third, the cluster's own record of that gate Job confirms the evidence. Before it accepts the evidence, the pre-push gate MUST read, through `with-gates-kubeconfig`, the gate Job the evidence names from the `gates` namespace, and the log of that Job's pod. The record confirms the evidence only when all three of these agree with it: the Job's status carries a `Complete` condition with status `True` and no `Failed` condition with status `True`; the Job's `livespec.gate/tree-hash` label equals the tree hash the evidence names; and the member list of the last `LIVESPEC_GATE_MEMBERS` line in the pod's log names, as run and passed, exactly the members the evidence names as run and passed. The gate MUST NOT treat any other source, including the evidence file itself or the green token, as the cluster's record.

Add, after the sentence "A pre-commit record that carries no gate Job name MUST NOT qualify.":

> When the cluster no longer holds that gate Job, or holds it without a readable pod log, the run MUST NOT qualify, and the pre-push gate MUST gate exactly as it does when no reusable evidence exists: it MUST submit a gate Job, or take the local fall-through where **Host eligibility** requires it. It MUST print a line naming the gate Job and saying that the cluster no longer holds its record. A cluster that cannot be reached, or a credential that cannot be refreshed, while reading the record MUST be handled the same way: the evidence does not qualify, and the push is then gated as the other bullets of this section require, including the **Verdict** bullet's rule that a push with no verdict is refused. When the cluster's record disagrees with the evidence on the Job's outcome, its tree or its member list, the run MUST NOT qualify, the pre-push gate MUST submit a gate Job exactly as it does when no reusable evidence exists, and it MUST print, before that submission, the gate Job's name, each field that disagreed, the value the evidence named and the value the cluster's record carried. A disagreement MUST NOT refuse the push by itself; only the verdict of the Job it then submits decides the push. The read of the record MUST NOT change the retention of any gate Job.

In the bullet's spec-first paragraph, append:

> The confirmation against the cluster's record (the third condition, and the missing-record and disagreement rules after it) is spec-first: as of its ratification the shipped pre-push gate accepts the evidence file without reading the cluster, and work item livespec-dev-tooling-7uae5p owns the change.

In SPECIFICATION/scenarios.md, add two scenarios after "## Scenario: a repository that does not set both delegated keys keeps pre-commit-to-pre-push green token reuse":

```gherkin
## Scenario: reused delegated pre-commit evidence whose gate Job the cluster no longer holds does not stand in for the pre-push gate

Given a consuming repository that sets both delegated_gate = true and delegated_pre_commit = true
And a delegated pre-commit run recorded pre-push evidence naming gate Job J, tree T and a member list
And the pushing worktree is clean and its HEAD tree is T
And the cluster no longer holds gate Job J
When the pre-push gate runs for that push
Then it MUST NOT accept the evidence
And it MUST print a line naming gate Job J and saying that the cluster no longer holds its record
And it MUST submit a gate Job for tree T exactly as it does when no reusable evidence exists
```

```gherkin
## Scenario: reused delegated pre-commit evidence that the cluster's record of its gate Job contradicts does not stand in for the pre-push gate

Given a consuming repository that sets both delegated_gate = true and delegated_pre_commit = true
And a delegated pre-commit run recorded pre-push evidence naming gate Job J, tree T and a member list
And the pushing worktree is clean and its HEAD tree is T
And the cluster holds gate Job J, and its record disagrees with the evidence on its outcome, its livespec.gate/tree-hash label or the members its LIVESPEC_GATE_MEMBERS line names as run and passed
When the pre-push gate runs for that push
Then it MUST NOT accept the evidence
And it MUST print gate Job J's name, each field that disagreed, the value the evidence named and the value the cluster's record carried
And it MUST submit a gate Job for tree T exactly as it does when no reusable evidence exists
And the push MUST be decided only by that Job's verdict
```
