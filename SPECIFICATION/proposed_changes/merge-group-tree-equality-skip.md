---
topic: merge-group-tree-equality-skip
author: claude-sonnet-5-5
created_at: 2026-11-16T18:35:07Z
---

## Proposal: A single-entry merge group whose tree equals its pull request head's tree reports its required checks green without re-running the suite

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State the guarded merge_group tree-equality skip: the guard outputs skip only for a one-entry group whose head tree equals the pull request head's tree and whose head checks are all green on the forge; ci-green keeps its name; the required-leg reader accepts a skipped leg only under the same run's skip=true.

### Motivation

Maintainer ruling, verbatim on epic livespec-dev-tooling-xowhol, 2026-11-16: "Yes we obviously do that or else we're going to add 20 to 40 minutes to every one-off PR on every one of those repos, right?" and "Yes this needs to be a definition of done and a requirement on the [stale-base-merge-options] plan". Plan assertion 12; carrier livespec-dev-tooling-ymog6r. Measured 2026-11-16: a merge group runs the full suite for about 18 minutes (median) and the first group to merge is about 19.6 minutes after the first group starts, so re-running a suite the pull request's own CI already passed on an identical tree is the avoidable part. Safety bounds from the ruling: skip only on tree equality; read the head's check results from the forge; the guard job always runs; the skip path reports the same required check names. In-flight survey: livespec-dev-tooling#4810 (a-merge-queue-rebuild-cancels) is independent of this change and aligned with it.

### Proposed Changes

Add to `contracts.md` §"### `self_hosted_routing` check" (the section holding **The guarded `merge_group` exception**, contracts.md:111), immediately after the paragraph that ends "...graded by `branch_protection_alignment`.", a new paragraph:

**The merge-group tree-equality skip.** The guard job MAY additionally output `skip`. On `pull_request` and `push` it outputs `skip=false` and makes no API call. On `merge_group` it outputs `skip=true` only when every condition below holds, and in every other case, including any API error, an unresolved queue entry or an unexpected payload, it outputs `skip=false` and the workflow runs its full job graph:
- The merge group contains exactly one merge queue entry, resolved through the same queue read the guard already makes for its allowlist check.
- The tree sha of the merge group's head commit equals the tree sha of that entry's pull request head commit, read from the forge. Equal trees mean the group is byte-identical to the head the pull request's own CI judged.
- The forge reports, for that exact pull request head commit sha, every required check run concluded `success`: each job `ci-green` lists in `needs:`, and `ci-green` itself. The guard reads that list from `.github/workflows/ci.yml` at the GROUP'S BASE commit (the file the group will run), never from the enqueued tree and never from a hard-coded list; a name it cannot resolve to a check run yields `skip=false`. The guard counts ONLY the LATEST check run of each name for that sha, and ONLY check runs whose app is the GitHub Actions app (`github-actions`), so an older attempt, a stale success or a success posted by another app or a status context can never stand in for a current Actions result. The results are read from the check-runs API for that sha and are never inferred from a label, a comment or the queue's own state. Only check runs whose `pull_requests[]` contains the queue entry's pull request number with `base.ref` equal to the group's `base_ref` count, so a run made before the pull request was retargeted to a different base, or a sha that is the head of two pull requests, can never stand in. A required job that is a matrix expands to its legs exactly as `ci_green_required_legs` does (one check run per leg, named `job (leg)`); a leg the guard cannot find yields `skip=false`. The head's run must have an EMPTY incident-omitted set (`incident-ci`'s `omitted` output), because an incident-omitted run concludes success while skipping members; a non-empty set yields `skip=false`.
- The queue entry's base commit equals the group's base commit, so master did not move under the entry.
- The group's base commit is an ANCESTOR of (or equal to) the pull request head commit. The `pull_request` CI run tests `refs/pull/<N>/merge`, the head merged with whatever master was when that run started, not the bare head tree. Because master only moves forward, a base that is an ancestor of the head means master has not gained commits the head lacks, so every base the pull request's run could have merged into is also an ancestor, and the merge ref's tree equals the head tree. Without this condition, a master change X that was present when the pull request ran and was later reverted would make the group tree equal the bare head tree, which no run ever tested. The guard reads the relation from the compare API (`status` is `identical` or `ahead` for base...head, never `behind` or `diverged`); any other answer or error outputs `skip=false`.

The guard job's token permissions stay read-only and are exactly `contents: read`, `pull-requests: read` and `checks: read`, which condition (a) of the guarded exception allows. The guard job still runs on every event with no `if:` condition, so condition (f) of the guarded exception is unchanged. When `skip` is true, the gating jobs do not execute: each carries `if: ${{ !cancelled() && needs.<guard>.outputs.skip != 'true' }}` in place of `if: ${{ !cancelled() }}`, and `ci-green` keeps its name, keeps `if: always()` and reports the same required check context. The required-leg reader (`python3 -m livespec_dev_tooling.ci_green_required_legs`) MUST count a leg whose conclusion is `skipped` as satisfied only when the guard job of the SAME run concluded `success` with output `skip=true`; in every other run a skipped leg still fails `ci-green` closed. `self_hosted_routing` accepts the extra `skip` condition on a gating job as the shape of condition (e).

KILL SWITCH and REVERT TRIGGER: a repository variable `LIVESPEC_MERGE_GROUP_SKIP_DISABLED` set to `true` forces `skip=false` on every merge group, so one variable write turns the skip off without a workflow edit. The detector is the master-health reconcile job (it already reads master's push runs), and the owner of the same-hour switch-off is the plan coordinator of record; a red master commit whose merge group ran through the skip path is read from the merge_group run's guard output `skip=true`. The skip MUST be turned off the same hour, by setting that variable, when a master commit that is red was produced by a skipped merge group, or when any group reports green through the skip path whose tree differs from its pull request head's tree.

Known limit, stated so it is never read as a defect: the skip fires only when the pull request head already contains the group's base commit, which condition 5 requires, so a pull request branched before the latest master commit (`diverged`) runs in full; on a fast-moving master this removes part of the saving, by design. Also: when the merge queue builds more than one group concurrently, a group queued behind another pull request contains that pull request's commits, so its tree is not equal to its own head's tree and it runs in full. The skip fires for a group at the head of an otherwise empty queue.

Add to `scenarios.md`, immediately after "## Scenario: self_hosted_routing passes a guarded merge_group route and fails an unguarded one":

## Scenario: a single-entry merge group whose tree equals its pull request head's tree reports ci-green without re-running the suite

```gherkin
Given a merge group that contains exactly one merge queue entry

And the tree sha of the group's head commit equals the tree sha of that entry's pull request head commit

And the forge reports every required check run, and ci-green, concluded success for that pull request head commit

When the merge_group CI run starts

Then the guard job runs and outputs skip=true

And the gating jobs are skipped and ci-green concludes success under its unchanged required check name

And when the group's tree differs from the head's tree, or the group holds more than one queue entry, or the base commit moved, or any forge read fails, the guard outputs skip=false and the full job graph runs

And when a gating leg is skipped in a run whose guard did not output skip=true, ci-green fails naming the leg
```

The revise that ratifies this proposal adds, in the same revise commit, the `tests/heading-coverage.json` row for the new scenario heading (a `TODO` row whose reason names the tier it runs at, "A real test at the integration tier or above is owed for this heading", with `"work_item": "livespec-dev-tooling-ymog6r"`) and the regenerated `tests/heading-coverage-debt.json` (`just generate-heading-coverage-debt-register`).

Gap-id effect: the new paragraph under contracts.md `### `self_hosted_routing` check` adds no `## ` heading, so it changes no derived heading gap-id; the new scenario adds one `## Scenario` heading in scenarios.md, which is the one new heading-coverage row named above.

The required-leg reader (`python3 -m livespec_dev_tooling.ci_green_required_legs`) reads the Actions jobs API, which does not expose job outputs, so the guard's `skip` reaches it as an input passed from ci-green's `needs` context (for example `--guard-skip`), never inferred from the jobs list.
