---
topic: incident-merge-app-adoption-order
author: claude-sonnet-5-5 (bqnzcm plan seat)
created_at: 2026-11-18T04:12:48Z
---

## Proposal: Declaring the incident-merge App id is the adoption and adding it to the ruleset is the arming

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Relax the queue-required bypass bullet of branch_protection_alignment (ratified v246) so a declared incident_merge_integration_id whose Integration is not yet on the ruleset passes, while any Integration on the ruleset that is neither the recovery App nor the declared App still fails. The rollout order is then: commit the key (adoption), then add the App to the ruleset as pull-request-only bypass (arming), green at every step.

### Motivation

Coordinator ruling 2026-11-18 on plan expedited-incident-response-flag: a check that fails in both orders of a rollout breaks the fleet ordering rule (adoption first, then arming). Under v246 a declared key whose App is absent from the ruleset FAILS (the ruleset MUST carry it) and an undeclared App on the ruleset FAILS (no other actor), so rolling out the incident-merge App is red in either order. The check recognises the merge App only through the declared id, so admitting an undeclared extra Integration would let any App onto the master ruleset and is rejected; the safe relaxation is the inverse, a declared-but-not-yet-armed key passes. Owning work item: livespec-dev-tooling-u3nbm3.

### Proposed Changes

Replace the queue-required bypass bullet of `contracts.md` (the check `branch_protection_alignment`, the bullet that today begins "On a queue-required repository, the queue is the only path to `master` except the incident recovery principal and, where declared, the incident-merge principal") with:

- On a queue-required repository, the queue is the only path to `master` except the incident recovery principal and, where declared, the incident-merge principal. Every active ruleset that applies to the default branch MUST carry, as its `bypass_actors`, the `Integration` whose id equals the consumer's committed `recovery_bypass_integration_id` key and MAY carry, when the consumer commits an `incident_merge_integration_id` key (`[tool.livespec_dev_tooling]`; an App id is not a secret), the `Integration` whose id equals that key with `bypass_mode` `pull_request`, with no other actor. A committed `incident_merge_integration_id` whose `Integration` is not yet on the ruleset is the not-yet-armed state and does NOT fail: declaring the key is the adoption, and adding the `Integration` to the ruleset is the arming, so the rollout is green at every step. An incident-merge `Integration` whose `bypass_mode` is anything other than `pull_request` FAILS (exit `4`, `failure_mode` `merge_queue_bypass_path`), because that principal MUST NOT be able to push to `master` directly. Classic branch protection MUST either be absent or set `enforce_admins` with no push `restrictions` exception. Any other bypass actor or push path FAILS (exit `4`, `failure_mode` `merge_queue_bypass_path`). An absent `recovery_bypass_integration_id` on a queue-required repository FAILS the same way, because the check cannot tell the recovery App from any other App. An `incident_merge_integration_id` equal to `recovery_bypass_integration_id` FAILS the same way, because the recovery principal MUST remain the inverse-only principal and one App cannot hold both roles.

Add to `scenarios.md` these two scenarios:

## Scenario: branch_protection_alignment accepts a queue-required repository whose declared incident-merge App is not yet on the ruleset

```gherkin
Given a queue-required repository whose committed configuration declares a distinct incident_merge_integration_id

And the active ruleset on its default branch carries only the recovery App as a bypass actor

When branch_protection_alignment runs with an admin-scoped token

Then it reports no merge_queue_bypass_path finding
```

## Scenario: branch_protection_alignment fails a queue-required ruleset that carries an Integration the repository has not declared

```gherkin
Given a queue-required repository that declares no incident_merge_integration_id

And the active ruleset carries the recovery App and one other Integration with bypass_mode pull_request

When branch_protection_alignment runs with an admin-scoped token

Then it exits 4 with one fail finding whose failure_mode is merge_queue_bypass_path
```

The `tests/heading-coverage.json` rows for the two new scenario headings, and the debt-register entries any spec-first `TODO` row owes, MUST be co-edited in the revise commit.
