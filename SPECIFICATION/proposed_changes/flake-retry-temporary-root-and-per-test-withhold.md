---
topic: flake-retry-temporary-root-and-per-test-withhold
author: claude-opus-5-5
created_at: 2026-11-08T09:51:21Z
---

## Proposal: A path a test builds under its own temporary root does not name a repository path

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Narrow the Untouched-test retry rule's definition of the paths a test's closure names, so that a path expression rooted at a temporary or other non-repository base names no repository path. Only a single string literal, or a path expression rooted at the repository root or at a string literal, names one. Add a scenario showing a test whose closure names a changed file only under a temporary root being retried, and one showing that a test which copies a repository directory into a temporary root is still touched.

### Motivation

On 2026-11-08 livespec-dev-tooling master run 42445385824 (commit 63302bba, which changed only `.github/workflows/ci.yml` and `.livespec-workflow-edit-exemption`) failed in `check-per-file-coverage` on `test_a_red_verdict_names_the_members_of_the_last_summary_in_either_shape[last-is-bash-stderr]`, a known load flake (livespec-dev-tooling-wv57ma). It was not retried, and the log carried neither `FLAKE-RETRIED` nor `FLAKE-RETRY-WITHHELD`. Replaying the plugin's `retry_marker_for` on that commit showed the test file treated as touched through line 323 of `tests/consumer/test_delegated_gate_declared_recipe_scenarios.py`, `workflow = root / ".github" / "workflows" / "ci.yml"`, where `root` is the test's own temporary directory and the file written is synthetic. The current sentence, "The closure names a path either as one string literal or as the whole join of consecutive string-literal segments of one path expression", makes that join name `.github/workflows/ci.yml` whatever the root is. The closure is per test file, so one fixture helper withholds the retry of every test in the file, and every ci.yml commit switches retries off for the delegated-gate scenario files. legacy-coordinator-agent ruled under R301 that this must change. The implementation item is livespec-dev-tooling-jfy23q (plan fleet-flaky-tests, epic livespec-dev-tooling-zwveqp), which waits on this revise.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, in the **Untouched-test retry** bullet of `## Testing approach`, replace the sentence "The closure names a path either as one string literal or as the whole join of consecutive string-literal segments of one path expression." with:

> The closure names a path either as one string literal or as the whole join of consecutive string-literal segments of one path expression whose first operand is a string literal or a name bound to the repository root. A path expression whose first operand is any other base, such as `tmp_path`, a directory derived from it, a home directory or a state directory, MUST NOT name a repository path, and its segments, joined or alone, MUST NOT count as string literals of the closure for this rule. A test that copies repository content into such a base names its source through its own repository-rooted expression or string literal, and that name still counts.

No other sentence of the bullet changes. In particular, "When the plugin cannot determine which paths a closure names, the test MUST be treated as touched" still applies to a path expression rooted at the repository root or at a string literal that carries a non-literal segment.

In `SPECIFICATION/scenarios.md`, immediately after `## Scenario: a failing test that shares only an ancestor directory name with the change set is retried`, add two scenarios:

```
## Scenario: a failing test whose closure names a changed file only under a temporary root is retried

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a failing test whose closure names `.github/workflows/ci.yml` only through `root / ".github" / "workflows" / "ci.yml"`, where `root` is a directory built from `tmp_path`

And a change set that contains `.github/workflows/ci.yml`

When that test fails on its first attempt

Then the plugin MUST treat the test as untouched and re-run it on its own, exactly as for any untouched failing test

## Scenario: a failing test that copies a repository directory into a temporary root is still touched

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a failing test whose closure copies `REPO_ROOT / "ci-runner"` into `tmp_path / "ci-runner"`, where `REPO_ROOT` is bound to the repository root

And a change set that contains `ci-runner/k3s/x.sh`

When that test fails

Then the session MUST fail on that first failure, and the plugin MUST NOT re-run the test
```

The revise MUST add a `tests/heading-coverage.json` entry for each of the two new scenario headings, as spec-first `"test": "TODO"` rows owned by livespec-dev-tooling-jfy23q at the integration tier, registered in `tests/heading-coverage-debt.json`.

## Proposal: A per-test touched withhold is reported like a session-wide one

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend the Untouched-test retry rule's reporting duty so that a failing test withheld from retry because the change set touches its closure is reported in a `FLAKE-RETRY-WITHHELD` block and a GitHub Actions `::warning` naming the test's node id and the changed path or literal that touched it. Add a scenario for it. Today only a session-wide withhold is reported, so a correctly withheld retry is indistinguishable from the plugin never having loaded.

### Motivation

In the same master run 42445385824, the per-test touched rule fired and the plugin printed nothing, wrote no record and published no artifact. The only way to learn why the flake was not retried was to replay `retry_marker_for` by hand on a copy of the commit. The coordinator read the run as a possible retry gap, and the answer needed an investigation. The ratified text requires a `FLAKE-RETRY-WITHHELD` block and a `::warning` only when re-runs are disabled for the whole session, and says nothing about reporting the per-test case. legacy-coordinator-agent ruled under R301 that a withheld retry must never be indistinguishable from the plugin not running. The implementation item is livespec-dev-tooling-ln77b6 (plan fleet-flaky-tests), which waits on this revise.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, in the **Untouched-test retry** bullet of `## Testing approach`, replace the sentence "A touched test MUST fail at once with no re-run." with:

> A touched test MUST fail at once with no re-run. When a touched test fails, the terminal summary MUST print a `FLAKE-RETRY-WITHHELD` block naming the test's node id and one changed path, or one string literal of the closure, that made it touched, and under GitHub Actions the plugin MUST emit a `::warning` annotation naming `FLAKE-RETRY-WITHHELD` and that node id. Under pytest-xdist, a withholding decided on a worker MUST reach the controller's terminal summary.

No other sentence of the bullet changes. The session-wide `FLAKE-RETRY-WITHHELD` duty stays as written.

In `SPECIFICATION/scenarios.md`, immediately after `## Scenario: a failing test the run touched fails at once with no retry`, add:

```
## Scenario: a failing test the run touched is named in a withheld-retry block

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a change set that contains `.github/workflows/ci.yml`

And a failing test whose closure names `.github/workflows/ci.yml` through a string literal

When that test fails

Then the session MUST fail on that first failure, and the plugin MUST NOT re-run the test

And the terminal summary MUST print a `FLAKE-RETRY-WITHHELD` block naming the test's node id and `.github/workflows/ci.yml`, and under GitHub Actions a `::warning` annotation MUST name `FLAKE-RETRY-WITHHELD` and the node id
```

The revise MUST add a `tests/heading-coverage.json` entry for the new scenario heading, as a spec-first `"test": "TODO"` row owned by livespec-dev-tooling-ln77b6 at the integration tier, registered in `tests/heading-coverage-debt.json`.
