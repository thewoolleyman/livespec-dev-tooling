---
topic: commit-pairs-beside-test-classification
author: codex
created_at: 2026-11-03T00:10:00Z
---

## Proposal: Beside-test modules are test changes

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Refine the `source_tree_prefixes` classification rule so test-named modules
that live beside source code are classified as tests rather than source.

### Motivation

Work item `livespec-dev-tooling-iq7txz` found that
`commit_pairs_source_and_test` treated a staged `test_*.py` module in a
declared source tree as source while recognising tests only below
`tests_tree_prefix`. That makes a Red commit containing only a beside test
impossible in consumers such as livespec-overseer, despite the schema saying
that source-tree prefixes distinguish source from test.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Consumer configuration schema", append this
clause to the `source_tree_prefixes` bullet:

> A Python module under a declared or derived source-tree prefix whose basename
> is `conftest.py` or matches `test_*.py` MUST be classified as a test change,
> not as a source change, by a consumer that uses this key to classify staged
> or changed Python files.
