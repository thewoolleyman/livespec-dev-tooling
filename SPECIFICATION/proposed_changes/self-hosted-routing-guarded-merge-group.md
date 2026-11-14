---
topic: self-hosted-routing-guarded-merge-group
author: claude-opus-5-5
created_at: 2026-11-13T23:54:32Z
---

## Proposal: self_hosted_routing admits a guarded merge_group trigger and branch_protection_alignment grades the merge queue

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Two checks change for the org move. The self_hosted_routing check gets a contract. It keeps merge_group in its forbidden-trigger set except for the guarded shape that livespec NFR §"Self-hosted CI runner host requirements" → **Event routing** defines. branch_protection_alignment learns the merge queue. On an organization-owned repository that livespec requires to use the queue, the check fails on any of four conditions: a missing merge_queue rule, a build concurrency below 2, a merge method other than rebase, or any bypass or push path to master other than the committed recovery App.

### Motivation

This realizes, in dev-tooling, the two livespec proposals filed with it. They are "merge queue on organization-owned fleet repositories" and "merge_group under the Fork-exclusion precondition", both from plan stale-base-merge-options (epic livespec-dev-tooling-xowhol). The maintainer's call-3 ruling (option A, epic comment 27, 2026-11-13) requires the self_hosted_routing change to be ratified before its code. Today the check puts merge_group in `_FORBIDDEN_TRIGGERS` with no lever. ci.yml repeats that rule ("Re-add it WITH hosted routing only if a merge queue is adopted"). So queue CI could never reach the guarded self-hosted lane the maintainer chose. No dev-tooling spec clause states the check's contract today, so the exception has to be written down with the check rather than coded silently. The plan's Definition of Done also requires that the queue be the only path to master on dev-tooling and the orchestrator. branch_protection_alignment is the check that already reads the live rulesets, so it is the place that notices when the queue requirement is missing.

### Proposed Changes

1. In SPECIFICATION/contracts.md §"Shared check inventory", add a subsection after "### `branch_protection_alignment` check":

> ### `self_hosted_routing` check
>
> Invocation: `python -m livespec_dev_tooling.checks.self_hosted_routing`. This is a fail-by-default security guard with no severity lever. It reads only the repository's own `.github/workflows/*.yml` and `*.yaml`, and asserts two properties per workflow file.
>
> - **Reachability.** If any job's `runs-on` can resolve to a gating self-hosted label, the workflow's `on:` set MUST NOT contain a forbidden trigger. The forbidden triggers are `pull_request_target`, `workflow_run`, `issue_comment`, `repository_dispatch`, `merge_group` and `workflow_dispatch`. The gating label set is the built-in `local-ci` plus the consumer's `gating_self_hosted_labels`, unioned and never substituted.
> - **Fail-closed routing.** A `runs-on` that falls back from a repository variable MUST NOT name self-hosted capacity in its fallback.
>
> **The guarded `merge_group` exception.** `merge_group` is NOT a finding in a workflow where all of the following hold. This is the guarded shape of livespec NFR §"Self-hosted CI runner host requirements" → **Event routing**.
> - (a) The workflow declares a guard job whose `runs-on` names hosted capacity only and whose `permissions` are read-only.
> - (b) Every job whose `runs-on` can resolve to a gating self-hosted label lists the guard job in `needs:`.
> - (c) On a `merge_group` event, that `runs-on` selects self-hosted capacity only through an expression conditioned on the guard job's boolean output, and otherwise resolves to a hosted literal.
> - (d) The consumer declares a non-empty `merge_queue_author_allowlist` in its `[tool.livespec_dev_tooling]` block.
> - (e) A failed or cancelled guard never yields a green batch. Each gating job that needs the guard carries `if: ${{ !cancelled() }}`, so it still runs, routed to the hosted literal by (c), when the guard failed. Alternatively, the all-green gate job (`ci-green`) fails a `merge_group` run in which any gating job it lists in `needs:` concluded `skipped`. The check accepts either shape. A workflow with neither shape is a finding, because today's `ci-green` fails only on `failure` or `cancelled`, so a skipped job would let an untested batch pass.
> - (f) The guard job runs on every event. On `pull_request` and `push` it makes no API call and outputs `true`, because those events are already governed by the first two classes of **Event routing**. The guard computes its output from the forge API only on `merge_group`. So `needs:` is always satisfied, and no `pull_request` or `push` run changes its routing.
>
> Any other workflow that combines a gating self-hosted route with `merge_group` is a finding, exactly as before. The check verifies the guard's SHAPE statically. Whether the guard's API query is correct is proven by the guard's own tests, and the repository's fork-approval setting is graded by `branch_protection_alignment`.

2. In "### `branch_protection_alignment` check", add three ALIGNMENT-gate rules and their exit codes:

> - The check reads the repository owner's `type` from `repos/{owner}/{repo}`. The repository is QUEUE-REQUIRED when the owner is an `Organization` and its name is in `QUEUE_REQUIRED_REPOSITORIES`. That is a module-level constant of `livespec_dev_tooling.checks.branch_protection_alignment`, which today holds `livespec-dev-tooling` and `livespec-orchestrator-beads-fabro`, the set livespec NFR §"CI as a merge gate (branch protection)" names. It is deliberately not consumer configuration, because a repository must not be able to opt itself out of the queue. It changes only with a livespec specification revision. A queue-required repository with no `merge_queue` rule among its active rulesets' rules for the default branch FAILS (exit `4`, `failure_mode` `merge_queue_absent`).
> - A `merge_queue` rule whose build concurrency is below 2 FAILS (exit `4`, `failure_mode` `merge_queue_concurrency_below_floor`).
> - A `merge_queue` rule whose `merge_method` is not `REBASE` FAILS (exit `4`, `failure_mode` `merge_queue_method_not_rebase`). `master` accepts only rebase-merges, so each PR's per-commit Red-Green-Replay TDD trailers survive.
> - On a queue-required repository, the queue is the only path to `master` except the incident recovery principal. Every active ruleset that applies to the default branch MUST carry, as its ONLY `bypass_actors` entry, the `Integration` whose id equals the consumer's committed `recovery_bypass_integration_id` key (`[tool.livespec_dev_tooling]`; an App id is not a secret), with no other actor. Classic branch protection MUST either be absent or set `enforce_admins` with no push `restrictions` exception. Any other bypass actor or push path FAILS (exit `4`, `failure_mode` `merge_queue_bypass_path`). An absent `recovery_bypass_integration_id` on a queue-required repository FAILS the same way, because the check cannot tell the recovery App from any other App.
> - On a repository whose workflows use the guarded `merge_group` exception of `self_hosted_routing`, a fork-PR workflow-approval setting below `all_external_contributors` FAILS (exit `4`, `failure_mode` `fork_approval_below_strictest`). An unreadable setting takes the existing outcome-3 graceful-skip path.
>
> On a personal-account repository a `merge_queue` rule cannot exist, and none of these rules fire. The `strict_enabled` rule is unchanged.

In the exit-code list, add `merge_queue_absent`, `merge_queue_concurrency_below_floor`, `merge_queue_method_not_rebase`, `merge_queue_bypass_path` and `fork_approval_below_strictest` to the exit-`4` fail branches.

3. In SPECIFICATION/scenarios.md, add:

```gherkin
## Scenario: self_hosted_routing passes a guarded merge_group route and fails an unguarded one

Given a workflow whose gating job routes to a gating self-hosted label and whose on: set includes merge_group

And the workflow declares a hosted, read-only guard job that the gating job needs

And the gating job's merge_group route selects self-hosted capacity only on the guard's true output and otherwise names a hosted literal

And the consumer declares a non-empty merge_queue_author_allowlist

And each gating job that needs the guard carries if: ${{ !cancelled() }}

When self_hosted_routing runs

Then it reports no finding for that workflow

And when the gating job's needs: omits the guard job, self_hosted_routing fails naming the workflow file and the merge_group trigger

And when the gating job lacks the !cancelled() condition and ci-green does not fail a skipped gating job, self_hosted_routing fails naming the workflow file
```

```gherkin
## Scenario: branch_protection_alignment fails a queue-required repository whose master does not require the merge queue

Given livespec-dev-tooling is owned by an organization

And no active ruleset on its default branch carries a merge_queue rule

When branch_protection_alignment runs with an admin-scoped token

Then it exits 4 with one fail finding whose failure_mode is merge_queue_absent
```

The revise commit adds `tests/heading-coverage.json` rows for both new `## Scenario:` headings, as spec-first TODOs at the unit tier, with `work_item` livespec-dev-tooling-mvqo6h. It also regenerates `tests/heading-coverage-debt.json`.
