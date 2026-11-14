---
topic: a-timed-wait-loop-in
author: claude-opus-5-5
created_at: 2026-11-14T03:03:21Z
---

## Proposal: A looped real-time sleep in a coverage-measured test file carries a coverage marker, so per-file coverage does not depend on host load

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md
- SPECIFICATION/contracts.md

### Summary

Add a "Load-independent test coverage" bullet to §"Testing approach": a test-tree Python file MUST NOT hold a real-time sleep (time.sleep, by static name) inside a loop unless the sleep's line carries pragma: no cover or a `# slow-path-covered-by: <path>::<test>` marker naming a test a static read finds. Admit that marker as one narrow exclude_also entry, which the coverage-exclusion paragraph otherwise forbids without a propose-change cycle. A shared check, looped_sleep_coverage, enforces it and refuses the marker on any other line. Add the check to tests_tree_prefix's consumers, plus a scenario. A wait loop's sleep line runs only when the awaited condition is late, so today a file's per-file coverage passes on an idle host and fails on a loaded one.

### Motivation

Work item livespec-dev-tooling-e34ks3 (plan fleet-flaky-tests, epic livespec-dev-tooling-zwveqp) has been held at the spec-change tier since 2026-11-08 on this topic, with generalization target ## Testing approach, and the proposal was never filed. Its Definition of Done asks for a shared check that refuses a looped real-time time.sleep in a coverage-measured test file unless the line carries a pragma or a slow-path-covered-by marker naming an existing test, and that refuses a marker naming a missing test. Measured impact: diagnosis livespec-dev-tooling-b6lw5w (note 007, livespec-dev-tooling#4618) attributes 5 of the 11 coverage-flake master runs of the 7 days to 2026-11-13T22:05Z to this class (b795877a6, ce6288d2f, 8c0900840, d8d23caec, 37850ee7d, each reading "Required test coverage of 100.0% not reached. Total coverage: 100.00%"). That is the largest single share of livespec-dev-tooling master coverage reds. The Dispatcher's spec-stated judgement found the behaviour unstated. The nearest existing rule, "Environment-independent test coverage" (no_ambient_environment_loops), is the same shape for host environment instead of host load, so this bullet sits beside it.

### Proposed Changes

Edits are in `non-functional-requirements.md` (the §"Testing approach" bullet and the coverage-exclusion paragraph), one scenario appended to `scenarios.md`, and one Consumers-list name in `contracts.md`. No H2 heading of `non-functional-requirements.md` or `contracts.md` is added, renamed or removed.

**1. Testing approach bullet (`non-functional-requirements.md`).** Add the bullet below directly after the "Environment-independent test coverage" bullet. If the pending proposal `root-fix-tests-livespec-dev` ("Host-independent test verdicts") has been ratified first and already sits at that position, add this bullet directly after that one instead. The two do not interact: that one governs a test's verdict, this one governs its coverage, and a marker exempts nothing from that one.

- **Load-independent test coverage.** A Python file under the repository's test tree (`tests_tree_prefix`, default `"tests/"`) MUST NOT contain a real-time sleep inside a loop unless the sleep's line carries a coverage marker. Such a sleep runs only while the condition the loop waits for is not yet true, which depends on how fast the host runs the test, so the file's per-file coverage under the 100% gate would depend on host load. A *real-time sleep* is a call written as `time.sleep(...)` where `time` is bound by `import time`, or through an alias the same file binds by `import time as <name>` or `from time import sleep [as <name>]`. A call through any other name, including `asyncio.sleep`, `threading.Event.wait` and a sleep reached through an injected or patched clock, is outside this rule. *Inside a loop* means anywhere lexically within the body or the `else` clause of a `for`, `async for` or `while` statement, including nested blocks, but not inside a function or class defined within that loop. The *coverage marker* is either a `pragma: no cover` comment, or a trailing comment `# slow-path-covered-by: <path>::<test>` on the sleep's own line. There, `<path>` is a repository-relative path to a Python file under the test tree, and `<test>` names a module-level test function or a `<Class>::<method>` test method that a static read of that file finds, without parametrization brackets. That file MAY be the file that carries the marker. The named test is the one that drives the slow path on purpose. The shared check `looped_sleep_coverage` enforces this. It reads source statically and performs no network I/O. It MUST refuse a looped real-time sleep that carries neither marker, naming the file and line. It MUST refuse a `slow-path-covered-by:` marker whose named test that static read does not find, naming the marker's file, its line and the missing test. It MUST refuse a `slow-path-covered-by:` marker on any line that does not hold a looped real-time sleep, naming the file and line, so the marker's coverage exclusion reaches no other line. It MUST pass a file whose looped real-time sleeps all carry a pragma or a marker naming a test it finds. A marker exempts a line only from per-file coverage. It never exempts a test from §"Testing approach"'s rules on test verdicts and concurrency waits. This bullet is spec-first: test files in this repository still carry unmarked looped real-time sleeps, and work item livespec-dev-tooling-e34ks3 owns the change.

**2. Coverage-exclusion paragraph (`non-functional-requirements.md`).** The paragraph that limits `exclude_also` to livespec's exact list currently reads: "`exclude_also` MUST be minimal and limited to structurally-unreachable patterns matching livespec's exact list: `if TYPE_CHECKING:`, `raise NotImplementedError`, `raise ImportError`, `@overload`, `if __name__ == .__main__.:`, `sys.path.insert`, `case _:`. No other exclusions are permitted without a propose-change cycle." Directly after that last sentence, add this sentence:

> The list additionally carries one entry, `# slow-path-covered-by:`, which is not structurally unreachable: it excludes only a looped real-time sleep's own line, as §"Testing approach" bullet "Load-independent test coverage" defines, and the shared check `looped_sleep_coverage` refuses that marker on any other line.

The short coverage-gate bullet in §"Testing approach" ("Exclusions are minimal and documented in `pyproject.toml` `[tool.coverage.report].exclude_also`") stays as it is: the new entry is documented there like every other entry. This proposal is the propose-change cycle that paragraph requires for a new exclusion.

**3. `tests_tree_prefix` consumers (`contracts.md`).** In the `tests_tree_prefix` role key's **Consumers:** list, add `looped_sleep_coverage` in alphabetical position, since the new check walks that tree. If the pending proposal `tests-tree-prefix-consumers-name` (which adds `no_ambient_environment_loops` to the same list) has been ratified first, keep its name and add this one too. The two additions do not interact.

**4. Scenario (`scenarios.md`).** Append the scenario below. The file uses unnumbered `## Scenario:` headings, so it carries none.

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

**5. Revise co-edit.** The revise pass that accepts this proposal MUST add one `tests/heading-coverage.json` row for the new scenario heading in the same revise commit, carrying `test: "TODO"`, `work_item: "livespec-dev-tooling-e34ks3"`, and a `reason` stating that a real test at the integration tier or above is owed (a consumer-style check-runner test running `looped_sleep_coverage` against a fixture mini-project under `tmp_path`) and that livespec-dev-tooling-e34ks3 owns it. The same commit MUST regenerate `tests/heading-coverage-debt.json` with `just generate-heading-coverage-debt-register`, never by hand.

**6. Unchanged.** The coverage gate's 100% line and branch floor, the "Load-independent concurrency waits" and "Environment-independent test coverage" bullets, and every other entry of the exclusion list are unchanged. The marker is the only exclusion this proposal admits, and it reaches only a looped real-time sleep's own line.
