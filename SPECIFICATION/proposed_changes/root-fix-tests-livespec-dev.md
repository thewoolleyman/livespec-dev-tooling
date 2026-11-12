---
topic: root-fix-tests-livespec-dev
author: claude-opus-5-5
created_at: 2026-11-12T03:18:37Z
---

## Proposal: Host-independent test verdicts

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a Testing approach bullet requiring that a test's pass-or-fail verdict never depend on how fast the host runs it. A time limit the test itself owns - a wall-clock bound, a real-time wait, a subprocess timeout or a scheduling margin set in the test or its fixtures - MUST NOT decide a verdict; a test that needs time or ordering controls them itself. A time limit in the code under test may still be relied on when the outcome does not move with host speed, and exactly one scenario, the staged type-error refusal within 60 seconds, is exempt by name. A failure message that asserts several facts MUST name each false one. Add a scenario stating the observable consequence for a subject with no time limit of its own: the same test reaches the same verdict on a loaded host as on an idle one.

### Motivation

Plan fleet-flaky-tests (epic livespec-dev-tooling-zwveqp) has root-fixed over a hundred flaky tests, and most share one cause: a wall-clock bound decides the verdict, so a loaded CI runner or dev host fails a test whose code behaves correctly. Examples are livespec-dev-tooling-xrdhfl (a 3 s node-wait deadline), livespec-dev-tooling-hzhw6y (a 15 s git bound in the incident inverse helpers), livespec-dev-tooling-oczx3k (a gate-wait return measured by wall clock) and livespec-dev-tooling-i4prpx (a run-order assertion resting on spawn timing). The ratified Testing approach states environment-independent coverage and the untouched-test retry backstop, but nothing says a verdict must be host-independent. So on 2026-11-12 the spec-change tier judge, on orchestrator v0.320.0, classified oczx3k, i4prpx and hzhw6y as spec-change tier (verdicts partial and unstated, topic root-fix-tests-livespec-dev) and they were merge-held. This clause states the rule these root fixes implement. The retry plugin is a backstop for flakes; it is not a licence for a timing-dependent verdict. Revised after the coordinator's grade of livespec-dev-tooling#4246: the rule now bans only time limits the test owns, so it does not contradict ratified scenarios that rely on a limit in the code under test (the kill-matrix per-test timeout, the suite-green stall window). It explicitly exempts a test of an elapsed-time bound the specification states (the staged-precheck 60-second refusal). It scopes the loaded-host scenario to a subject with no time limit of its own, and it makes naming each false fact a MUST, as hzhw6y's Definition of Done requires.

### Proposed Changes

In non-functional-requirements.md, section "## Testing approach", add this bullet directly after the "Environment-independent test coverage" bullet:

- **Host-independent test verdicts.** A test in this repository's test tree MUST reach the same verdict whatever the speed or load of the host that runs it. A time limit the test itself owns - a wall-clock bound, a real-time wait, a subprocess timeout or a scheduling margin set in the test or its fixtures - MUST NOT decide whether the test passes or fails. A test that needs time to pass MUST control it through an injected or controlled clock, and a test that needs an ordering MUST control it through a rendezvous the test owns or a count of events it observes, so that a slow, loaded or starved host cannot change the verdict. The test MAY still set a hang-guard limit on how long it waits for a process that has hung, provided reaching that limit fails the test with a message saying the limit was reached, and provided no passing verdict depends on finishing within it. A time limit in the code under test is not owned by the test: a test MAY rely on such a limit firing, for example a per-test timeout ending a mutant that loops forever, or a stall window ending a run that has stopped printing, when the test's outcome is the same however fast or slow the host runs. This rule has exactly one exemption: a test of the scenario "a staged type error refuses the commit before the full pre-commit aggregate", whose specified behaviour is itself the bound "the commit MUST be refused within 60 seconds of the commit starting", MAY measure elapsed wall-clock time against that bound, and MUST assert no tighter bound than it. A test of any other elapsed-time bound this specification states, such as `gate-wait` returning within five seconds of a run's `exit_code` appearing, MUST check that bound through a measure the host's load cannot move, such as the number of polls made against it. When a test asserts several facts at once, its failure message MUST name each fact that was false.

In scenarios.md, add this scenario:

## Scenario: a test reaches the same verdict on a loaded host as on an idle one

Given a test in this repository's test tree whose subject starts a subprocess and waits for it

And the subject sets no time limit of its own and this specification states no elapsed-time bound for it

And a host loaded so heavily that the subprocess takes 20 seconds longer to answer than on an idle host

When the test runs on the loaded host and on the idle host

Then the test MUST reach the same verdict on both hosts

And when the subject behaves correctly, that verdict MUST be a pass on both hosts
