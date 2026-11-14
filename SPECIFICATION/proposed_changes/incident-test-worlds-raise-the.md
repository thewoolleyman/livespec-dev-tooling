---
topic: incident-test-worlds-raise-the
author: claude-opus-5-5
created_at: 2026-11-14T03:50:00Z
---

## Proposal: A test world raises the product child-process bounds it reaches to the hang guard, and a wrong refusal fails naming its code

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add one bullet, "Product bounds in test worlds", to non-functional-requirements.md §"Testing approach", directly after the "Load-independent concurrency waits" bullet. That bullet already says a test's verdict MUST NOT depend on how fast the host runs it, but its hang-guard rule names only the test's own waits. The new bullet extends the rule to product timeouts that a test world reaches for real:
- A shared world fixture raises each such timeout to the hang guard, together with any cap that bounds or validates it. It keeps every ordering the product defaults hold, and the product defaults do not change.
- A bound whose expiry a test expects, set by that test itself, is outside the rule.
- A test that expects one refusal and gets another fails naming the refusal code it got.
- Four named incident test files pass with every CPU of the host saturated, and a change to the world fixture records 20 such consecutive runs on its pull request.

Add one scenario that exercises the bullet.

### Motivation

Work item livespec-dev-tooling-vm4vcn, filed 2026-11-14 as the forge-bound remainder of livespec-dev-tooling-rs6o3q, after legacy-coordinator-agent split rs6o3q. Its pre-dispatch screen refused it at the spec-change tier at 03:40:08Z (verdict partial against ## Testing approach, linked topic incident-test-worlds-raise-the).

Incident test worlds run real product code, and that code calls child processes under short product timeouts:
- ProcessInverseForge's timeout_seconds = 15 is checked against _MAX_TIMEOUT_SECONDS = 60. A call whose timeout is not under that cap returns {} at once, so raising the timeout alone breaks every call.
- incident_git's INCIDENT_GIT_TIMEOUT_SECONDS = 10 and INCIDENT_GIT_FETCH_TIMEOUT_SECONDS = 120.
- incident_observer_reconcile's _PRINCIPAL_TIMEOUT_SECONDS = 45.

The product defaults hold orderings that tests pin. For example, tests/livespec_dev_tooling/test_incident_git.py keeps the git timeout under the forge timeout the recovery principal runs under, and keeps the fetch timeout above the git timeout. A raise that broke an ordering would recreate in tests the failure those orderings prevent in production: an outer bound expires before the inner one, and the hung child is orphaned.

On a loaded CI runner these timeouts expire, and the failure surfaces as a product refusal such as 'inverse-scope-unavailable' or 'incident git write-tree exceeded its 10 s ceiling'. Some show only as a downstream symptom: in test_publish_interrupted_after_preparing_resends_the_same_commit, a FileNotFoundError on the publication journal hid a refusal before the prepare step.

Measured failures: CI runs 43491008875, 43511942840, 43512128617 and 43502256904, all on 2026-11-13. #4557 (rs6o3q) moved the tests' own waits to tests/hang_guard.HANG_GUARD_SECONDS, but the product bounds those tests reach are still the product defaults.

Some tests expect a bound to expire. Examples are the deadline_seconds=1.0 slow target in test_incident_gate_rereview.py and the timeout tests in test_incident_git.py and test_incident_inverse_service.py. They set those bounds themselves and stay outside the rule, as the waits bullet already exempts a wait whose expiry is the outcome a test expects.

legacy-coordinator-agent graded this proposal on livespec-dev-tooling#4631 (2026-11-14) and asked for four changes, all included: the expiry exception, the ordering clause, the load run stated as recorded evidence over four named files, and a scenario.

### Proposed Changes

**1. Product bounds in test worlds (`non-functional-requirements.md` §"Testing approach").**

Insert the following bullet immediately after the bullet that begins "**Load-independent concurrency waits.**":

> - **Product bounds in test worlds.** When a test world runs product code that bounds a child process, or a call to another service, by a product timeout, the world MUST raise that timeout to no less than the hang guard. In the same step it MUST raise any cap that bounds or validates that timeout, so that raising the timeout alone can never make a call fail at once. The raised values MUST keep each ordering the product defaults hold: a timeout stays strictly under its cap, and an inner call's bound stays under the bound of the call that waits for it. The world MUST apply these raises itself, through one shared fixture, so that a test reaches them without opting in. The product defaults MUST NOT change. A bound whose expiry is the outcome a test expects, and which that test sets itself, is outside this rule. When a test expects a particular refusal and the code under test refuses for another reason, the test MUST fail with a report that names the refusal code it received, never with a later symptom of that refusal such as a missing file. Every test in `tests/livespec_dev_tooling/test_incident_recovery_principal.py`, `tests/livespec_dev_tooling/test_incident_recovery_principal_target_branch.py`, `tests/livespec_dev_tooling/test_incident_conflict_chain.py` and `tests/livespec_dev_tooling/test_incident_observer_invalidation.py` MUST pass with every CPU of the host saturated by concurrent load. A change to the shared world fixture MUST record on its pull request the outcome of 20 consecutive runs of those four files under that load. These sentences are spec-first: incident test worlds still run `ProcessInverseForge`, `incident_git` and the recovery principal under their product timeouts, and work item livespec-dev-tooling-vm4vcn owns the change.

**2. A scenario for the bullet (`scenarios.md`).**

Insert the following scenario immediately after `## Scenario: incident focused verification reads its changed set through the isolated object view and disposes symlinked and submodule paths explicitly`:

```text
## Scenario: an incident test world raises the product child-process bounds it reaches to the hang guard

Given an incident test world built through the shared world fixture, with no opt-in by the test, on a host whose every CPU is saturated by a concurrent load generator

And product code in that world that runs the inverse forge, incident git and the recovery principal under their product timeouts

When a test in that world drives an incident through recovery

Then the inverse forge timeout, its cap, the incident git timeouts and the recovery principal timeout MUST each be no shorter than the hang guard

And the inverse forge timeout MUST stay strictly under its cap, and the incident git timeout MUST stay under the inverse forge timeout

And the same product timeouts read outside the test world MUST equal their product defaults

And when the recovery principal refuses for a reason other than the one the test expects, the test MUST fail with a report that names the refusal code it received

And a bound that the test sets itself, and whose expiry the test expects, MUST still expire at the value the test set
```

The fence above is presentation only. Write the scenario in scenarios.md unfenced, in the plain Given/When/Then line style of the scenarios at the end of the file.

**Heading-coverage co-edit owed by the revise.** The scenario adds a new H2 heading. The revise commit MUST add a `tests/heading-coverage.json` row for it with `"test": "TODO"` and `"work_item": "livespec-dev-tooling-vm4vcn"`. Its reason names the integration tier, for example: "A real test at the integration tier or above is owed for this heading: livespec-dev-tooling-vm4vcn owns it." The commit MUST also regenerate and stage `tests/heading-coverage-debt.json` with `just generate-heading-coverage-debt-register`. The bullet in change 1 adds no heading.
