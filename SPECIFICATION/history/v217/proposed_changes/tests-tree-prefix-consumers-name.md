---
topic: tests-tree-prefix-consumers-name
author: claude-opus-5-5 (seat:fleet-flaky-tests)
created_at: 2026-11-13T20:10:00Z
---

## Proposal: The `tests_tree_prefix` Consumers list names `no_ambient_environment_loops`

### Target specification files

- SPECIFICATION/contracts.md

### Summary

§"`no_ambient_environment_loops` check" requires the check to walk every `.py` file under the consumer's `tests_tree_prefix`. So the check reads that role key. But the key's bullet in §"Role keys", whose **Consumers:** list is the ratified inventory of the checks that read it, does not name the check. This proposal adds `no_ambient_environment_loops` to that list. It is an internal-consistency repair: no behaviour changes, and the implementation (work item livespec-dev-tooling-dpkz32) already reads the key as its own section requires.

### Motivation

`tests/spec/test_role_key_consumer_inventory.py` derives each role key's consumers from the code and fails when the spec's **Consumers:** list differs. Building dpkz32's check, as its contract section requires, fails that test with `{'tests_tree_prefix': (['no_ambient_environment_loops'], [])}` (delegated gate 20261113T194119Z-4096783, 2026-11-13). The check's own section and the role-key inventory disagree. The section is the more specific clause, and the inventory exists to list what the sections make each check read, so the inventory is the text to repair. Until it does, dpkz32 cannot land.

### Proposed Changes

### SPECIFICATION/contracts.md §"Role keys", the `tests_tree_prefix` bullet

Replace the bullet's **Consumers:** list:

"**Consumers:** `commit_pairs_source_and_test`, `dev_tooling_imports_declared`, `pbt_coverage_pure_modules`, `tests_mirror_pairing`, `tests_no_subprocess_spawn`."

with:

"**Consumers:** `commit_pairs_source_and_test`, `dev_tooling_imports_declared`, `no_ambient_environment_loops`, `pbt_coverage_pure_modules`, `tests_mirror_pairing`, `tests_no_subprocess_spawn`."

The rest of the bullet is unchanged. No `## ` heading is added, renamed or removed, so `tests/heading-coverage.json` needs no co-edit.
