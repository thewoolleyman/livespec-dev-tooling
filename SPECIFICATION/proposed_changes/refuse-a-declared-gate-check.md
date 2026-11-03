---
topic: refuse-a-declared-gate-check
author: claude-opus-5-5:dev-host-test-gate-load
created_at: 2026-11-03T09:49:00Z
---

## Proposal: refuse a declared gate check suite that ends in the pre-commit aggregate

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a bullet to contracts.md §"Delegated pre-push gate" that states the declared `gate_check_suite` key, and require the shared consumer check aggregates to refuse a delegated repository whose declared suite ends in the pre-commit aggregate. Add a scenario that states the refusal and the accepted shapes.

### Motivation

A declared `gate_check_suite` is the suite for BOTH delegated gates. The pre-push gate Job runs it as declared. The delegated pre-commit client replaces only its LAST entry with `check-pre-commit-gated-tree`. So a suite that ends in `check-pre-commit` makes every delegated pre-push run the pre-commit aggregate instead of the pre-push aggregate. Nothing errors and the push goes green. In the driver repositories that aggregate runs no tests. This happened silently on 2026-11-02 in livespec-driver-codex (4d5f5b7), livespec-driver-claude (fb3fd58) and livespec-overseer (c0280fa0), and was repaired by hand under livespec-dev-tooling-jrcp4m. The spec does not state the key at all today, so no check can be held to it. The rule is a denylist of the pre-commit recipes rather than "must equal check-pre-push", because livespec-dev-tooling's own suite legitimately ends in `hook_gate=1 check`, and an equality rule would refuse the canonical repository. Work item: livespec-dev-tooling-5d3cvr.

### Proposed Changes

1. In SPECIFICATION/contracts.md §"Delegated pre-push gate", insert this new bullet immediately after the bullet "**The consumer's own recipe, and a missing one.**":

- **Declared gate check suite.** A consuming repository MAY declare `gate_check_suite` in its `[tool.livespec_dev_tooling]` table: an array of `just` invocations that the delegated gate Job runs in order against the tree under test. When the key is absent, the gate Job runs the `check` recipe that the local fall-through runs. An entry MAY carry leading `name=value` variable assignments. The recipe an entry names is its first token that is not such an assignment. The declared suite is shared by both delegated gates. The pre-push gate Job runs it as declared, and the delegated pre-commit aggregate (§"Delegated pre-commit aggregate") runs it with only its final entry replaced by the pre-commit recipe. Its final entry is therefore the pre-push slot. When `delegated_gate = true`, the shared consumer pre-commit and pre-push check aggregates that this repository ships MUST refuse a declared suite whose final entry names the recipe `check-pre-commit` or `check-pre-commit-gated-tree`. The refusal MUST name `pyproject.toml`, the key `gate_check_suite`, the offending final entry and the expected final recipe `check-pre-push`. The refusal does NOT apply to a final entry that names another recipe (for example `check-pre-push`, or this repository's own `hook_gate=1 check`), to a repository that declares no `gate_check_suite`, or to a repository whose `delegated_gate` is not the literal boolean `true`. The rule is a denylist of the pre-commit recipes rather than a required final recipe, so a repository whose gate recipe is not called `check-pre-push` is not refused.

2. In SPECIFICATION/scenarios.md, add this scenario immediately after "## Scenario: a delegated pre-commit aggregate with no cluster verdict gates locally":

## Scenario: a delegated gate check suite ending in the pre-commit aggregate is refused

Given a consuming repository whose `[tool.livespec_dev_tooling]` sets `delegated_gate = true`

And declares `gate_check_suite = ["install-worktree-pack", "check-pre-commit"]`

When its shared pre-commit or pre-push check aggregate runs

Then the aggregate MUST fail

And its output MUST name `pyproject.toml`, the key `gate_check_suite`, the final entry `check-pre-commit` and the expected final recipe `check-pre-push`

And the same aggregate MUST NOT fail on that rule when the declared suite ends in `check-pre-push` or in `hook_gate=1 check`, when the key is absent, or when `delegated_gate` is not `true`

3. tests/heading-coverage.json gains a row for the new scenario heading in the revise commit, as a spec-first `TODO` whose reason names the tier the owed test runs at and names work item livespec-dev-tooling-5d3cvr as its owner. The heading-coverage debt register is regenerated in the same commit.
