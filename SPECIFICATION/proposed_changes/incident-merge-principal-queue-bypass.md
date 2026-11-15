---
topic: incident-merge-principal-queue-bypass
author: claude-opus-5-5 (bqnzcm plan seat)
created_at: 2026-11-15T22:45:59Z
---

## Proposal: An incident-merge principal may merge a green expedited repair outside the merge queue

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Admit exactly one more ruleset bypass actor on a queue-required repository, the incident-merge principal named by a committed incident_merge_integration_id key distinct from recovery_bypass_integration_id. Define that principal in Expedited incident execution: it merges only a labelled, genesis-recorded, pr-bound incident repair, only after verifying every effective required check green on the exact head at merge time, with an expected-head rebase merge, and logs each merge or refusal on the incident item. Add four scenarios.

### Motivation

Maintainer ruling on livespec-dev-tooling-72b33c, 2026-11-15, verbatim: "Yes option A is acceptable. The merge train can be bypassed for an incident". In a queue-required repository the expedited lane speeds the commit but not the merge: a forward repair waits behind the whole queue, and an expedited product-.py commit cannot pass the queue's own replay gate (livespec-dev-tooling-yfrepg). Today the only queue bypass is the recovery principal, which livespec core limits to merging the validated complete inverse, so a forward merge needs a distinct principal and this check must admit it. A ruleset bypass also skips required_status_checks, so the ratified text must keep the principal from merging past a red check. This proposal depends on the companion livespec core proposal that ratifies a distinct incident-merge principal; it should be revised after that one. Fleet scope: every queue-required repository's ruleset and alignment check.

### Proposed Changes

Replace the queue-required bypass bullet of `contracts.md` (the check `branch_protection_alignment`, the bullet that today begins "On a queue-required repository, the queue is the only path to `master` except the incident recovery principal") with:

- On a queue-required repository, the queue is the only path to `master` except the incident recovery principal and, where declared, the incident-merge principal. Every active ruleset that applies to the default branch MUST carry, as its `bypass_actors`, the `Integration` whose id equals the consumer's committed `recovery_bypass_integration_id` key and, when the consumer commits an `incident_merge_integration_id` key (`[tool.livespec_dev_tooling]`; an App id is not a secret), the `Integration` whose id equals that key, with no other actor. Classic branch protection MUST either be absent or set `enforce_admins` with no push `restrictions` exception. Any other bypass actor or push path FAILS (exit `4`, `failure_mode` `merge_queue_bypass_path`). An absent `recovery_bypass_integration_id` on a queue-required repository FAILS the same way, because the check cannot tell the recovery App from any other App. An `incident_merge_integration_id` equal to `recovery_bypass_integration_id` FAILS the same way, because the recovery principal MUST remain the inverse-only principal and one App cannot hold both roles.

Add to `contracts.md` §"Expedited incident execution" a paragraph headed "Incident-merge principal":

An independently provisioned incident-merge principal MAY merge one expedited repair pull request into the default branch outside the merge queue. It MUST merge only when every one of the following holds, each read at merge time: the incident work item has a genesis record in the canonical incident authority chain; the pull request carries the `expedited-incident-response` label; the chain's current attempt for that item is `pr-bound` to that pull request number and names the pull request's forge-read base and head; and every context of the default branch's EFFECTIVE required-check set (the set `branch_protection_alignment` grades) has concluded `success` on that exact head SHA. A ruleset bypass also skips `required_status_checks`, so this green-check verification is the principal's own obligation and MUST NOT be delegated to the ruleset. It MUST merge with the repository's rebase method and the expected head SHA, so a head that moved after verification refuses rather than merges. When any condition fails it MUST NOT merge and MUST record the named refusal on the incident work item. For each merge it MUST record on the incident work item the acting principal, the merged head SHA, the resulting `master` SHA, the UTC time, and the merge-queue state before the merge (the entries ahead of the pull request). It MUST NOT merge a pull request that is not an incident repair, and it MUST NOT merge an incident inverse, which remains the recovery principal's only merge. It skips no hook, required check, master CI run, incident recovery or unexpedited factory follow-up.

Add to `scenarios.md` these four scenarios:

## Scenario: branch_protection_alignment accepts a queue-required ruleset whose bypass actors are the recovery App and the declared incident-merge App

```gherkin
Given a queue-required repository whose committed configuration declares recovery_bypass_integration_id and a different incident_merge_integration_id

And the active ruleset on its default branch carries exactly those two Integrations as its bypass actors

When branch_protection_alignment runs with an admin-scoped token

Then it reports no merge_queue_bypass_path finding
```

## Scenario: branch_protection_alignment fails a queue-required repository whose incident-merge App is the recovery App

```gherkin
Given a queue-required repository whose committed incident_merge_integration_id equals its recovery_bypass_integration_id

When branch_protection_alignment runs with an admin-scoped token

Then it exits 4 with one fail finding whose failure_mode is merge_queue_bypass_path
```

## Scenario: the incident-merge principal merges a green expedited repair outside the merge queue and records it

```gherkin
Given an incident work item with a genesis record whose current attempt is pr-bound to a labelled pull request at its forge-read base and head

And every context of the effective required-check set concluded success on that head

When the incident-merge principal merges the pull request

Then the pull request is rebase-merged without entering the merge queue

And the incident work item records the acting principal, the merged head, the resulting master SHA, the UTC time and the queue entries that were ahead of it
```

## Scenario: the incident-merge principal refuses an expedited repair whose required check is not green on its head

```gherkin
Given an incident work item whose current attempt is pr-bound to a labelled pull request

And one context of the effective required-check set has not concluded success on the pull request's head

When the incident-merge principal is asked to merge the pull request

Then it does not merge

And the incident work item records the refusal naming that required check
```

The `tests/heading-coverage.json` rows for the four new scenario headings, and the debt-register entries any spec-first `TODO` row owes, MUST be co-edited in the revise commit.
