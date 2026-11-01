---
topic: coverage-run-names-slowest-tests
author: claude-opus-5-5
created_at: 2026-11-01T03:56:42Z
---

## Proposal: The whole-suite coverage run prints its thirty slowest test phases

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Add to non-functional-requirements.md "## Enforcement-suite invocation" that the `just` target running the whole test suite with coverage prints the thirty slowest test phases of that run with their durations, locally and in CI.

### Motivation

Linked proposal for held work item livespec-dev-tooling-tt4w7h (linked topic this-repository-s-coverage-ci). Plan implement-test-performance (epic livespec-dev-tooling-sv6m5p), assertion 4. Research note plan/implement-test-performance/research/003-suite-time-profile.md measured about 50 s of slow tests at the very end of this repository's coverage run and could not name them because no run records per-test durations.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, "## Enforcement-suite invocation", append a paragraph: "The `just` target that runs the whole test suite with coverage (`check-per-file-coverage`) MUST print the thirty slowest test phases of that run with their durations, so that the run's slow tail is named in every local, sandbox and CI log."
