---
topic: incident-test-worlds-raise-the
author: claude-opus-5-5
created_at: 2026-11-14T03:50:00Z
---

## Proposal: A test world raises the product child-process bounds it reaches to the hang guard, and a wrong refusal fails naming its code

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Add one bullet, "Product bounds in test worlds", to non-functional-requirements.md §"Testing approach", directly after the "Load-independent concurrency waits" bullet. That bullet already says a test's verdict MUST NOT depend on how fast the host runs it, but its hang-guard rule names only the test's own waits. The new bullet extends the rule to product timeouts that a test world reaches for real:
- A shared world fixture raises each such timeout, together with any cap that bounds or validates it, to the hang guard, by construction. The product default does not change.
- A test that expects one refusal and gets another fails naming the refusal code it got.
- The incident test files pass with every CPU of the host saturated.

### Motivation

Work item livespec-dev-tooling-vm4vcn, filed 2026-11-14 as the forge-bound remainder of livespec-dev-tooling-rs6o3q, after legacy-coordinator-agent split rs6o3q. Its pre-dispatch screen refused it at the spec-change tier at 03:40:08Z (verdict partial against ## Testing approach, linked topic incident-test-worlds-raise-the).

Incident test worlds run real product code, and that code calls child processes under short product timeouts:
- ProcessInverseForge's timeout_seconds = 15 is checked against _MAX_TIMEOUT_SECONDS = 60. A call whose timeout is not under that cap returns {} at once, so raising the timeout alone breaks every call.
- incident_git's INCIDENT_GIT_TIMEOUT_SECONDS = 10 and INCIDENT_GIT_FETCH_TIMEOUT_SECONDS = 120.
- incident_observer_reconcile's _PRINCIPAL_TIMEOUT_SECONDS = 45.

On a loaded CI runner these expire, and the failure surfaces as a product refusal such as 'inverse-scope-unavailable' or 'incident git write-tree exceeded its 10 s ceiling'. Some show only as a downstream symptom: in test_publish_interrupted_after_preparing_resends_the_same_commit, a FileNotFoundError on the publication journal hid a refusal before the prepare step.

Measured failures: CI runs 43491008875, 43511942840, 43512128617 and 43502256904, all on 2026-11-13. #4557 (rs6o3q) moved the tests' own waits to tests/hang_guard.HANG_GUARD_SECONDS, but the product bounds those tests reach are still the product defaults.

### Proposed Changes

**1. Product bounds in test worlds (`non-functional-requirements.md` §"Testing approach").**

Insert the following bullet immediately after the bullet that begins "**Load-independent concurrency waits.**":

> - **Product bounds in test worlds.** When a test world runs product code that bounds a child process, or a call to another service, by a product timeout, the world MUST raise that timeout to no less than the hang guard. In the same step it MUST raise any cap that bounds or validates that timeout, so that raising the timeout alone can never make a call fail at once. The world MUST apply these raises itself, through one shared fixture, so that a test reaches them without opting in. The product defaults MUST NOT change. When a test expects a particular refusal and the code under test refuses for another reason, the test MUST fail with a report that names the refusal code it received, never with a later symptom of that refusal such as a missing file. The repository's incident test files MUST pass with every CPU of the host saturated by concurrent load. These sentences are spec-first: incident test worlds still run `ProcessInverseForge`, `incident_git` and the recovery principal under their product timeouts, and work item livespec-dev-tooling-vm4vcn owns the change.

No heading is added, renamed or removed, so `tests/heading-coverage.json` needs no co-edit.
