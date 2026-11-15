---
topic: self-hosted-routing-refuses-a
author: claude-opus-5-5
created_at: 2026-11-15T02:36:14Z
---

## Proposal: self_hosted_routing refuses a merge_group guard job that carries an if: condition

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Condition (f) of the guarded `merge_group` exception in contracts.md section "`self_hosted_routing` check" says the guard job runs on every event, but it does not say that a guard job carrying an `if:` condition fails (f), nor what the check reports. This proposal adds one sentence to (f) stating that such a guard does not satisfy (f) and is reported as a finding naming the workflow file and the guard job, and adds one matching clause to the scenario "self_hosted_routing passes a guarded merge_group route and fails an unguarded one". No `## ` heading is added, changed or removed.

### Motivation

Work item livespec-dev-tooling-o3fbhe (BUG, child of plan stale-base-merge-options, epic livespec-dev-tooling-xowhol) records that condition (f) is not enforced by `livespec_dev_tooling/checks/_merge_group_guard.py`, so a guard job carrying an `if:` is admitted. An independent reviewer found this in the coordinator's grade of livespec-dev-tooling#4734 on 2026-11-15. A guard that is skipped on some event leaves `needs:` unsatisfied there, so every gating job that needs it is skipped or routed without the guard's verdict, which is exactly what (f) exists to prevent. The item was refused at factory launch at the spec-change tier (spec version 227, linked proposal topic self-hosted-routing-refuses-a): the scenario states only the missing-`needs:` and missing-`!cancelled()` failures, and does not say a guard job carrying an `if:` is refused. The spec must say it before the check is changed.

### Proposed Changes

Two edits, both verbatim.

1. In SPECIFICATION/contracts.md, section "### `self_hosted_routing` check", in the list under **The guarded `merge_group` exception.**, append this sentence to the end of item (f), after "So `needs:` is always satisfied, and no `pull_request` or `push` run changes its routing.":

A guard job that carries an `if:` condition does not satisfy (f), and the check reports it as a finding naming the workflow file and the guard job.

2. In SPECIFICATION/scenarios.md, in "## Scenario: self_hosted_routing passes a guarded merge_group route and fails an unguarded one", add this clause inside the gherkin block as the last clause, after "And when the gating job lacks the !cancelled() condition and ci-green carries no ci_green_required_legs step, self_hosted_routing fails naming the workflow file", separated from it by one blank line as the other clauses are:

And when the guard job carries an if: condition, so it does not run on every event, self_hosted_routing fails naming the workflow file and the guard job

No `## ` heading changes, so tests/heading-coverage.json is unchanged. The shipped check admits a guard job carrying an `if:`; work item livespec-dev-tooling-o3fbhe owns the implementation change and its test.
