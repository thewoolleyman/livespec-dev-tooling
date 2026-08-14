---
topic: adaptive-jit-nfr-heading-coverage
author: gpt-5.6
created_at: 2026-08-14T05:52:48Z
---

## Proposal: Map the adaptive JIT NFR heading to its implementation proof

### Target specification files

- tests/heading-coverage.json

### Summary

Add the required heading-coverage entry for the adaptive JIT admission NFR introduced in v044.

### Motivation

PR #1403 CI and a local reproduction show that the new NFR heading lacks the mandatory coverage-map entry. The v044 and v045 history snapshots must remain immutable.

### Proposed Changes

Add a TODO coverage entry for `## Adaptive JIT runner admission budget`, explicitly tied to livespec-s43svm.5 and the required controller integration proof.
