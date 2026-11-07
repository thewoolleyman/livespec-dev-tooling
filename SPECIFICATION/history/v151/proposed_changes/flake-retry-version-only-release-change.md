---
topic: flake-retry-version-only-release-change
author: claude-opus-5-5
created_at: 2026-11-07T15:47:34Z
---

## Proposal: A version-only release change does not disable flake retries, and a whole-session withholding is announced

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Narrow the flake-retry plugin's whole-session disable so that a release commit's version-only `pyproject.toml` and `uv.lock` change does not disable re-runs, keep every other change to those files disabling them, keep a test that names the changed file touched, and require every whole-session disable to announce itself with a `FLAKE-RETRY-WITHHELD` block and a GitHub Actions `::warning`.

### Motivation

Measured 2026-11-07 (livespec-dev-tooling-lbinx7). Release-please commit c48dfc52 changed only the version in `pyproject.toml` and the own-package version in `uv.lock`, among release bookkeeping. Both names disable re-runs for the whole session under the current rule, so CI run 42384603843 ran with zero retries and one load-sensitive flake (tests/spec/test_homelab_worker_serving_csr.py, a pipefail SIGPIPE race) turned master red. That red then refused every livespec-dev-tooling commit through check-master-ci-green, and ended factory run 01M6V7HXME7Y needs-human with that gate as its only failed target. The log carried no retry line and no withholding notice, because the plugin announces only the change-set-cannot-be-computed case. Every release commit on master, in every repository that loads this plugin through the livespec-dev-tooling pin, runs this way. A version value cannot alter a test's behaviour unless the test reads the file, which is why such a test stays touched, while any other build change keeps the conservative disable.

### Proposed Changes

In `non-functional-requirements.md` §"Testing approach", the **Untouched-test retry** bullet's whole-session sentence changes, and two sentences follow it.

Replace:

> Re-runs MUST be disabled for the whole session when the change set contains `pyproject.toml`, `uv.lock`, `justfile`, any `conftest.py` or the plugin itself, when a module of a failing test's closure cannot be parsed, or when the change set cannot be computed: undeterminable means touched.

with:

> Re-runs MUST be disabled for the whole session when the change set contains `pyproject.toml` or `uv.lock` other than as a version-only release change, `justfile`, any `conftest.py` or the plugin itself, when a module of a failing test's closure cannot be parsed, or when the change set cannot be computed: undeterminable means touched. A version-only release change MUST NOT by itself disable re-runs. `pyproject.toml` is version-only when its working-tree text and its text at the change set's base are identical apart from the value of the `[project]` table's `version` key; `uv.lock` is version-only when the two texts are identical apart from the `version` value of the package entry whose `name` is the `[project]` table's `name`. Each file is judged on its own; a file added, deleted or renamed, or a pair of texts that cannot be read or compared, is not version-only. The exception applies to this whole-session rule alone: a test whose closure names `pyproject.toml` or `uv.lock` is still touched by a change to that file. Whenever the plugin disables re-runs for the whole session under this rule, the terminal summary MUST print a `FLAKE-RETRY-WITHHELD` block naming the reason, and under GitHub Actions the plugin MUST emit a `::warning` annotation naming it.

In `scenarios.md`, the existing scenario keeps its heading and changes to:

```gherkin
## Scenario: a change set that touches the build or the plugin disables every retry

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a change set that contains `pyproject.toml` or `uv.lock` other than as a version-only release change, `justfile`, a `conftest.py` or the plugin itself, or a change set that cannot be computed, or a failing test whose closure holds a module that cannot be parsed

When any test in the session fails

Then the plugin MUST NOT re-run any test in that session

And the terminal summary MUST print a `FLAKE-RETRY-WITHHELD` block naming the reason, and under GitHub Actions the plugin MUST emit a `::warning` annotation naming it
```

Two scenarios are added directly after it:

```gherkin
## Scenario: a version-only release change leaves an untouched failing test retried

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a change set in which `pyproject.toml` differs from its base only in the `[project]` `version` value and `uv.lock` differs from its base only in the `version` value of the repository's own package entry, as a release-please release commit makes

And a failing test whose closure names neither file

When that test fails on its first attempt

Then the plugin MUST re-run it on its own, exactly as for any untouched failing test

And the terminal summary MUST NOT print a `FLAKE-RETRY-WITHHELD` block

## Scenario: a version-only release change still touches a test that names the changed file

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a change set in which `pyproject.toml` differs from its base only in the `[project]` `version` value

And a failing test whose closure names `pyproject.toml` through a string literal

When that test fails

Then the session MUST fail on that first failure, and the plugin MUST NOT re-run the test
```

Both new H2 headings MUST be added to `tests/heading-coverage.json` in the revise commit, as `"test": "TODO"` rows whose reason names the owed tier and livespec-dev-tooling-lbinx7, and registered through `just generate-heading-coverage-debt-register`.
