---
topic: branch-protection-strict-off
author: strict-off
created_at: 2026-06-22T18:32:49Z
---

## Proposal: branch_protection_alignment strict-off failure mode

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add a strict_enabled failure mode to the branch_protection_alignment check's ALIGNMENT gate: when master branch protection is present and required_status_checks.strict is TRUE, the check FAILS (exit 4) with a fail finding (failure_mode strict_enabled). Strict (require-branches-up-to-date) MUST be OFF per livespec core NFR §"CI as a merge gate (branch protection)".

### Motivation

livespec core NFR §"CI as a merge gate (branch protection)" was changed (core PR #521) so branch protection MUST NOT enable GitHub's strict flag. dev-tooling's branch_protection_alignment contract currently lists failure modes for enforce_admins / required-check coverage but says nothing about strict; bring its contract in line with the strict-off merge-gate rule and ENFORCE strict-off.

### Proposed Changes

In SPECIFICATION/contracts.md §"`branch_protection_alignment` check", extend the ALIGNMENT gate (outcome 1) with a strict-off assertion. Add a new bullet at the top of the gate's bullet list: `required_status_checks.strict` is TRUE → ERROR; the check FAILS (exit 4) with one fail finding (failure_mode strict_enabled). Strict (require-branches-up-to-date) MUST be OFF per livespec/SPECIFICATION/non-functional-requirements.md §"CI as a merge gate (branch protection)": strict makes GitHub keep a behind PR current by merging master into its branch, injecting a Merge branch 'master' commit that violates required_linear_history and buries the per-commit Red-Green-Replay TDD trailers; since master accepts only rebase-merges, strict adds no correctness guarantee. Update the gate's intro sentence to note the strict-off assertion, and update the Exit codes line to list strict_enabled alongside protection_absent and required_check_missing_from_ci as a fail branch. Keep everything else (the three-outcome disambiguation, the protection-present + matrix-alignment behavior, the CI-token caveat) intact.
