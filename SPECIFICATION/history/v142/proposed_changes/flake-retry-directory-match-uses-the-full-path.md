---
topic: flake-retry-directory-match-uses-the-full-path
author: claude-opus-5-5
created_at: 2026-11-05T13:40:57Z
---

## Proposal: A directory touches a test only through the full directory path the test names

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Narrow the flake-retry plugin's touched-test rule for non-module paths. A changed path touches a test through a directory only when that directory's FULL repository-relative path is named by the test's closure — as one string literal, or as consecutive literal segments of one path expression — never because a single shared ancestor directory NAME (such as `ci-runner`) appears as a literal. The exact-path, file-name and module rules are unchanged, and an undeterminable closure still counts as touched. The touched-test scenario's Given is aligned, and a new scenario states the retry case for an ancestor-only overlap.

### Motivation

livespec-dev-tooling-sdrq5v, filed under plan dev-host-test-gate-load on legacy-coordinator-agent's R301 ruling. The current rule (non-functional-requirements.md §"Testing approach": "any parent directory name appears as a string literal in the closure") makes every test that builds a path segment by segment (`_REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "gates" / ...`) read as touched by ANY change under `ci-runner/`. Measured: livespec-dev-tooling#3474 changed only `ci-runner/k3s/phase2/factory/DERIVATION.md` (plus host vars and an unrelated test), and on run 41986660733 job 127248144297 the readiness-boundary flake in `tests/livespec_dev_tooling/test_stand_in_proxy_readiness_boundary.py` (root-fixed by livespec-dev-tooling-2yn5qh) went unretried and failed the PR. The intent of the touched rule is that a change the test actually depends on must not be retried away; a shared top-level directory name is not evidence of that dependency, so the coarse match withholds the in-place retry from every PR under a busy directory while protecting nothing.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Testing approach", bullet **Untouched-test retry**, replace the sentence

> The change set touches a test when it contains a module of that closure; a Python module whose dotted name appears as a string literal in the closure; or any other path whose repository-relative path, file name with extension, or any parent directory name appears as a string literal in the closure.

with

> The change set touches a test when it contains a module of that closure; a Python module whose dotted name appears as a string literal in the closure; or any other path whose repository-relative path or file name with extension appears as a string literal in the closure, or which lies under a directory the closure names by its full repository-relative path — either as one string literal or as consecutive string-literal segments of one path expression. A single directory name shared with the change set (for example `ci-runner` alone, from a path built as `ROOT / "ci-runner" / "k3s" / ...`) MUST NOT by itself make a test touched. When the plugin cannot determine which paths a closure names, the test MUST be treated as touched.

The rest of the bullet is unchanged.

In `SPECIFICATION/scenarios.md`, change the second Given of `## Scenario: a failing test the run touched fails at once with no retry` from

> And a change set that contains a module in a failing test's in-repository import closure, or a fixture file under a directory whose name appears as a string literal in that closure

to

> And a change set that contains a module in a failing test's in-repository import closure, the exact repository path that closure names, or a file under a directory whose full repository-relative path that closure names

The When and Then lines are unchanged: the session MUST fail on that first failure, and the plugin MUST NOT re-run the test.

In `SPECIFICATION/scenarios.md`, insert directly after that scenario a new scenario:

```
## Scenario: a failing test that shares only an ancestor directory name with the change set is retried

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a failing test whose closure names `ci-runner/k3s/phase2/gates/render-gate-job-exit-tests.sh` through consecutive string-literal path segments

And a change set whose only path under `ci-runner/` is `ci-runner/k3s/phase2/factory/DERIVATION.md`

When that test fails on its first attempt

Then the plugin MUST treat the test as untouched and re-run it on its own, exactly as for any untouched failing test
```

The revise that accepts this MUST add a `tests/heading-coverage.json` entry for the new scenario heading (a `TODO` entry is acceptable only with a reason naming the integration tier and the owning work item livespec-dev-tooling-sdrq5v, registered in `tests/heading-coverage-debt.json`).
