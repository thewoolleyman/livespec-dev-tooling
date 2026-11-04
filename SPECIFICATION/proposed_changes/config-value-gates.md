---
topic: config-value-gates
author: claude:ci-runtime-and-cost
created_at: 2026-11-04T19:10:08Z
---

## Proposal: Config-value fast path at pre-commit

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add an H2 to contracts.md: a staged change whose every changed line is the value of a key on the shared tooling's committed config-value fast-path list runs schema and parse validation of the changed files only at pre-commit, runs no test suite, and refuses an invalid value naming the file and the key. Add a scenario for it.

### Motivation

Maintainer direction recorded verbatim in the ~18:4xZ 2026-11-04 scope event on livespec-dev-tooling-6tgd2z: "why does it takes a whole PR just to make the change. Even if the file is committed, it should be a short circuit, no-tests change to change the wip or cap values. NO TEST SHOULD BE TIED TO CONFIG VALUE ACTUAL VALUES. IF any of this is the case, fix it." legacy-coordinator-agent accepts this proposal under R301 on the maintainer's behalf. No H2 of this spec states either rule, so items livespec-dev-tooling-hmztez and livespec-dev-tooling-symfx2 were refused approval: their References lines named sections that do not govern their assertions.

### Proposed Changes

Add to `contracts.md`, after §"Delegated pre-commit aggregate":

## Config-value fast path at pre-commit

- **The key list.** livespec-dev-tooling MUST ship ONE committed config-value fast-path list. It names each qualifying key by file pattern and key path, and at least covers `.livespec.jsonc` `dispatcher.wip_cap` and `stall_timeout_seconds`, ansible host_vars `max_concurrent_runs`, and `ci-runner` profile `ADMISSION_CAPACITY_C`. Consumers read the list from the shared tooling, and a consumer MAY extend it only through its own committed configuration.
- **The class.** A staged change is a config-value change when every line it changes is the value of a key on that list, in a file matching the list's pattern for that key. Adding, removing or renaming a listed key, or changing any other line, makes it not a config-value change.
- **What runs.** For a config-value change, the pre-commit hook MUST run schema and parse validation of every changed file, and MUST run no test suite and no other aggregate member.
- **Refusal.** A changed value that fails that validation MUST refuse the commit, and the refusal MUST name the file and the key.
- **Everything else.** Every other staged change MUST take the pre-commit path it takes today.
- **Pre-push and CI.** The pre-push and CI halves follow livespec core's rule for this class (proposal config-value-fast-path, livespec PR #3099) once it is ratified there.

Add to `scenarios.md`:

## Scenario: a staged capacity value change commits on schema validation alone

Given a repository whose committed config-value fast-path list names `.livespec.jsonc` `dispatcher.wip_cap`
When a commit stages only a change of `dispatcher.wip_cap` from 4 to 6
Then the pre-commit hook runs schema and parse validation of `.livespec.jsonc` and no test suite, and the commit proceeds
And a commit that stages `dispatcher.wip_cap` changed to a value the schema rejects is refused, naming `.livespec.jsonc` and `dispatcher.wip_cap`
And a commit that also stages any other changed line runs the normal pre-commit aggregate

## Proposal: Tests never pin committed configuration values

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add an H2 to contracts.md stating that a test never asserts a committed configuration or capacity VALUE: it asserts shape and derivation, or a value it writes itself. Add a scenario for it.

### Motivation

Maintainer direction recorded verbatim in the ~18:4xZ 2026-11-04 scope event on livespec-dev-tooling-6tgd2z: "why does it takes a whole PR just to make the change. Even if the file is committed, it should be a short circuit, no-tests change to change the wip or cap values. NO TEST SHOULD BE TIED TO CONFIG VALUE ACTUAL VALUES. IF any of this is the case, fix it." legacy-coordinator-agent accepts this proposal under R301 on the maintainer's behalf. No H2 of this spec states either rule, so items livespec-dev-tooling-hmztez and livespec-dev-tooling-symfx2 were refused approval: their References lines named sections that do not govern their assertions.

### Proposed Changes

Add to `contracts.md`:

## Tests never pin committed configuration values

A test never asserts a committed configuration or capacity VALUE; it asserts shape and derivation, or a value it writes itself.

- A test MUST NOT assert the literal committed value of any key on the config-value fast-path list (§"Config-value fast path at pre-commit"), or of any other capacity, cap, timeout or quota key in a committed configuration file.
- A test of such a key MUST assert the value's shape, for example that it is a positive integer, or its derivation, for example that per-node capacities sum to the cohort quota. Alternatively it MUST exercise behaviour against a fixture value it writes itself.
- Changing any such committed value to another value its schema accepts MUST leave every test of the repository passing.

Add to `scenarios.md`:

## Scenario: changing a committed capacity value to another valid value leaves every test passing

Given a repository whose committed `ci-runner` profile sets `ADMISSION_CAPACITY_C` to 8
When `ADMISSION_CAPACITY_C` is changed to 6, a value its schema accepts
Then every test of the repository passes
And a test that checks the profile asserts that the capacity is a non-negative integer and that the profiles sum to the cohort quota, not that it equals 8
