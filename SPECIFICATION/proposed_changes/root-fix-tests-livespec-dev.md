---
topic: root-fix-tests-livespec-dev
author: claude-opus-5-5
created_at: 2026-11-12T02:23:02Z
---

## Proposal: Host-independent test verdicts

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a Testing approach bullet requiring that a test's pass-or-fail verdict never depend on how fast the host runs it. A wall-clock bound, a real-time wait, a subprocess timeout or a scheduling margin MUST NOT decide a verdict; a test that needs time or ordering controls them itself. Add a scenario that states the observable consequence: the same test reaches the same verdict on a loaded host as on an idle one.

### Motivation

Plan fleet-flaky-tests (epic livespec-dev-tooling-zwveqp) has root-fixed over a hundred flaky tests, and most share one cause: a wall-clock bound decides the verdict, so a loaded CI runner or dev host fails a test whose code behaves correctly. Examples are livespec-dev-tooling-xrdhfl (a 3 s node-wait deadline), livespec-dev-tooling-hzhw6y (a 15 s git bound in the incident inverse helpers), livespec-dev-tooling-oczx3k (a gate-wait return measured by wall clock) and livespec-dev-tooling-i4prpx (a run-order assertion resting on spawn timing). The ratified Testing approach states environment-independent coverage and the untouched-test retry backstop, but nothing says a verdict must be host-independent. So on 2026-11-12 the spec-change tier judge, on orchestrator v0.320.0, classified oczx3k, i4prpx and hzhw6y as spec-change tier (verdicts partial and unstated, topic root-fix-tests-livespec-dev) and they were merge-held. This clause states the rule these root fixes implement. The retry plugin is a backstop for flakes; it is not a licence for a timing-dependent verdict.

### Proposed Changes

In non-functional-requirements.md, section "## Testing approach", add this bullet directly after the "Environment-independent test coverage" bullet:

- **Host-independent test verdicts.** A test in this repository's test tree MUST reach the same verdict whatever the speed or load of the host that runs it. A wall-clock bound, a real-time wait, a subprocess timeout or a scheduling margin MUST NOT decide whether a test passes or fails. A test that needs time to pass MUST control it, through an injected or controlled clock, and a test that needs an ordering MUST control it, through a rendezvous the test owns or a count of events it observes, so that a slow, loaded or starved host cannot change the verdict. A timeout MAY still bound how long a test waits for a process that has hung, provided reaching it fails the test with a message saying the bound was reached, and provided no passing verdict depends on finishing within it. When a test asserts several facts at once, its failure message SHOULD name each fact that was false.

In scenarios.md, add this scenario:

## Scenario: a test reaches the same verdict on a loaded host as on an idle one

Given a test in this repository's test tree whose subject starts a subprocess and waits for it

And a host loaded so heavily that the subprocess takes 20 seconds longer to answer than on an idle host

When the test runs on the loaded host and on the idle host

Then the test MUST reach the same verdict on both hosts

And when the subject behaves correctly, that verdict MUST be a pass on both hosts
