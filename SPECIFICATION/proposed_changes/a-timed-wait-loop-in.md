---
topic: a-timed-wait-loop-in
author: claude-opus-5-5
created_at: 2026-11-14T03:01:15Z
---

## Proposal: A looped real-time sleep in a coverage-measured test file carries a coverage marker, so per-file coverage does not depend on host load

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a "Load-independent test coverage" bullet to §"Testing approach": a coverage-measured test file MUST NOT loop over a real-time time.sleep unless that line carries a pragma: no cover or a slow-path-covered-by: <test node id> marker, which is registered as a coverage exclusion and names an existing test. A shared check, looped_sleep_coverage, enforces it. A scenario states the three verdicts. A wait loop's sleep line runs only when the awaited condition is late, so today a file's per-file coverage passes on an idle host and fails on a loaded one.

### Motivation

Work item livespec-dev-tooling-e34ks3 (plan fleet-flaky-tests, epic livespec-dev-tooling-zwveqp) has been held at the spec-change tier since 2026-11-08 on this topic, with generalization target ## Testing approach, and the proposal was never filed. Its Definition of Done asks for a shared check that refuses a looped real-time time.sleep in a coverage-measured test file unless the line carries a pragma or a slow-path-covered-by marker naming an existing test, and that refuses a marker naming a missing test. Measured impact: diagnosis livespec-dev-tooling-b6lw5w (note 007, livespec-dev-tooling#4618) attributes 5 of the 11 coverage-flake master runs of the 7 days to 2026-11-13T22:05Z to this class (b795877a6, ce6288d2f, 8c0900840, d8d23caec, 37850ee7d, each reading "Required test coverage of 100.0% not reached. Total coverage: 100.00%"). That is the largest single share of livespec-dev-tooling master coverage reds. The Dispatcher's spec-stated judgement found the behaviour unstated. The nearest existing rule, "Environment-independent test coverage" (no_ambient_environment_loops), is the same shape for host environment instead of host load, so this bullet sits beside it.

### Proposed Changes

All edits are in `non-functional-requirements.md` §"Testing approach" and one new scenario appended to `scenarios.md`. No H2 heading of `non-functional-requirements.md` is added, renamed or removed.

**1. Testing approach bullet (`non-functional-requirements.md`).** Add the bullet below directly after the "Environment-independent test coverage" bullet. If the pending proposal `root-fix-tests-livespec-dev` ("Host-independent test verdicts") has been ratified first and already sits at that position, add this bullet directly after that one instead. The two bullets do not interact: that one governs a test's verdict, and this one governs its coverage.

- **Load-independent test coverage.** A coverage-measured Python file under the repository's test tree MUST NOT contain a `for`, `async for` or `while` statement whose body calls the standard library's real-time `time.sleep`, unless the line of that call carries a `pragma: no cover` comment or a `slow-path-covered-by: <test node id>` marker. Such a sleep runs only while the condition the loop waits for is not yet true, which depends on how fast the host runs the test, so the file's per-file coverage would depend on host load. A `slow-path-covered-by:` marker MUST be registered in `pyproject.toml` `[tool.coverage.report].exclude_also`, so that its line is excluded from coverage as a pragma's line is, and the test node id it names MUST exist in the repository: that test is the one that drives the slow path on purpose. The shared check `looped_sleep_coverage` enforces this. It MUST refuse a looped real-time sleep that carries neither marker, naming the file and line. It MUST refuse a `slow-path-covered-by:` marker whose node id names no test in the repository, naming the marker's file, its line and the missing node id. It MUST pass a file whose looped real-time sleeps all carry a pragma or a marker naming an existing test. A sleep through an injected or patched clock is not a real-time `time.sleep` and is outside this rule. This bullet is spec-first: test files in this repository still carry unmarked looped real-time sleeps, and work item livespec-dev-tooling-e34ks3 owns the change.

**2. Scenario (`scenarios.md`).** Append the scenario below. It carries no number; the revise pass assigns one if the file numbers its scenarios.

## Scenario: a looped real-time sleep in a coverage-measured test file is refused unless it carries a coverage marker

Governing clause: `non-functional-requirements.md` §"Testing approach", bullet "Load-independent test coverage".

```gherkin
Feature: looped_sleep_coverage keeps per-file coverage independent of host load
  Scenario: An unmarked looped sleep is refused
    Given a coverage-measured test file whose while loop calls time.sleep(0.05) on line 12 with no marker
    When the looped_sleep_coverage check runs
    Then the check fails naming that file and line 12

  Scenario: A marker that names a missing test is refused
    Given a coverage-measured test file whose looped time.sleep call on line 12 carries "slow-path-covered-by: tests/test_x.py::test_missing"
    And no test tests/test_x.py::test_missing exists in the repository
    When the looped_sleep_coverage check runs
    Then the check fails naming that file, line 12 and the node id tests/test_x.py::test_missing

  Scenario: Validly marked looped sleeps pass
    Given a coverage-measured test file whose looped time.sleep calls each carry a pragma: no cover comment or a slow-path-covered-by marker naming an existing test
    When the looped_sleep_coverage check runs
    Then the check passes
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST add one `tests/heading-coverage.json` row for the new scenario heading in the same revise commit, carrying `test: "TODO"`, `work_item: "livespec-dev-tooling-e34ks3"`, and a `reason` stating that a real test at the integration tier or above is owed (a consumer-style check-runner test running `looped_sleep_coverage` against a fixture mini-project under `tmp_path`) and that livespec-dev-tooling-e34ks3 owns it. The same commit MUST regenerate `tests/heading-coverage-debt.json` with `just generate-heading-coverage-debt-register`, never by hand.

**4. Unchanged.** The coverage gate's 100% line and branch floor, the "Load-independent concurrency waits" bullet and every other bullet of the section are unchanged. A pragma or a marker is the only exclusion this bullet admits, and it admits it only on the looped sleep's own line.
