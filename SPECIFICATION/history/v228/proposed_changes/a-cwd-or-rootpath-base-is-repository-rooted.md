---
topic: a-cwd-or-rootpath-base-is-repository-rooted
author: claude-opus-5-5 (seat:fleet-flaky-tests)
created_at: 2026-11-13T01:59:43Z
---

## Proposal: A flake-retry closure path based on the working directory or pytest's rootpath is repository-rooted

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend the list of repository-rooted bases in the "Untouched-test retry" bullet with two more: the current working directory (`Path.cwd()` or `os.getcwd()`) and pytest's root path (`rootpath` or `rootdir` read from a pytest config object). A closure path built on either base then names a repository path, so a change to that path touches the test. Add one scenario whose two cases cover a test that names a changed file through `Path.cwd()` and one that names it through `request.config.rootpath`.

### Motivation

The ratified "Untouched-test retry" bullet, in section "Testing approach" of `SPECIFICATION/non-functional-requirements.md`, defines three repository-rooted bases: a string literal, an expression derived from `__file__`, and a name the closure binds to one of those. It names as non-rooted a function parameter, `tmp_path` or a directory derived from it, a home directory and a state directory. It says nothing about `Path.cwd()` or `os.getcwd()`, and nothing about pytest's root path (`config.rootpath`, `request.config.rootpath`, `pytestconfig.rootpath`, and the older `rootdir`). Real tests use them: livespec-orchestrator-beads-fabro's `test_closed_item_integrity.py` builds `Path.cwd() / "tests"`.

The plugin must classify these bases one way or the other, and today the spec does not say which. Both are in fact the repository root in this fleet. pytest's root path is the repository root for every fleet repository, and pytest runs from the repository root in every fleet gate and CI job, so the working directory is the repository root too.

Treating both as repository-rooted errs toward "touched", the direction the bullet already prefers when a closure's paths cannot be determined. Treating them as non-rooted would retry a test whose closure really names a changed repository path, and a real regression would then be retried as if it were a flake.

Found by legacy-coordinator-agent while grading livespec-dev-tooling#4413 on 2026-11-13. Work item: livespec-dev-tooling-wc23r2. Owner: plan fleet-flaky-tests (epic livespec-dev-tooling-zwveqp).

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, bullet "Untouched-test retry", replace the sentence:

"A base is repository-rooted when it is a string literal; an expression derived from `__file__`, such as `Path(__file__).resolve().parents[2]`; or a name that the closure binds by assignment, anywhere in the closure, to a repository-rooted expression."

with:

"A base is repository-rooted when it is a string literal; an expression derived from `__file__`, such as `Path(__file__).resolve().parents[2]`; the current working directory (`Path.cwd()` or `os.getcwd()`); pytest's root path (`rootpath` or `rootdir` read from a pytest config object, such as `request.config.rootpath` or `pytestconfig.rootpath`); or a name that the closure binds by assignment, anywhere in the closure, to a repository-rooted expression. This holds even when the test changes its working directory (for example `monkeypatch.chdir(tmp_path)`) before the expression runs; counting such a base as rooted errs toward touched."

The rest of the bullet is unchanged. In particular, the following sentence's list of non-rooted bases (a function parameter, `tmp_path`, a directory derived from it, a home directory or a state directory) stays as it is.

In `SPECIFICATION/scenarios.md`, add a new scenario directly after `## Scenario: a failing test that copies a repository directory into a temporary root is still touched`:

"## Scenario: a failing test whose closure names a changed file through the working directory is touched

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a change set that contains `tests/fixtures/data.json`

And a failing test whose closure names that file only as `Path.cwd() / "tests" / "fixtures" / "data.json"`

When the flake-retry plugin decides that test's retry

Then the plugin MUST treat the test as touched

And the session MUST fail on that first failure, and the plugin MUST NOT re-run the test

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a change set that contains `tests/fixtures/data.json`

And a failing test whose closure names that file only as `request.config.rootpath / "tests" / "fixtures" / "data.json"`

When the flake-retry plugin decides that test's retry

Then the plugin MUST treat the test as touched

And the session MUST fail on that first failure, and the plugin MUST NOT re-run the test"

The scenario's two Given/When/Then cases prove the two new bases, the working directory and pytest's root path, under its one heading.

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the revise commit. The entry is a TODO row whose `reason` names the integration tier and livespec-dev-tooling-wc23r2 as the owning work item, and which carries the explicit key `"work_item": "livespec-dev-tooling-wc23r2"`. The revise MUST also regenerate the heading-coverage debt register (`just generate-heading-coverage-debt-register`) and stage `tests/heading-coverage-debt.json`.
