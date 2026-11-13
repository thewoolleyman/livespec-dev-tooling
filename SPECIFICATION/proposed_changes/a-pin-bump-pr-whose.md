---
topic: a-pin-bump-pr-whose
author: claude-opus-5-5 (expedited-incident-response-flag)
created_at: 2026-11-13T00:55:43Z
---

## Proposal: An open bump PR whose base gains a discovered pin is refreshed so its head names the target tag

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a stale-base refresh rule to reusable-bump-pin-from-dispatch.yml in contracts.md section Cross-repo coordination automation surface. While a bump PR is open and behind its consumer's default branch, the bump automation resets its bot-owned branch to the default tip, re-runs the same pin rewrite for the PR's source_repo and tag, commits it with a chore: subject and pushes it with --force-with-lease. On the refreshed head, every pin that Pin autodiscovery rules discovers for source_repo names the target tag. The trigger is a push to the default branch, added to the existing bump-pin-from-dispatch.yml shim, so no shim is added. reusable-pin-freshness.yml is the backstop for the race between a refresh and the merge. A refresh with nothing to change pushes nothing. One scenario is added to scenarios.md.

### Motivation

Measured on 2026-11-13. livespec-overseer master went red at 88221220 (run 43333510978: check-metadata-batch, check-ci-single-container-image). Bump PR livespec-overseer#2966 (dev-tooling pin to v1.202.0) was opened at 22:16:49Z, and its rewrite moved every livespec-fabro-sandbox image line then on master to python-v1.202.0. At 22:5xZ livespec-overseer#2963 merged a NEW image line, the incident-ci job's container, at python-v1.200.0. A merge of master into the bump branch (9862305b2, 22:58:23Z) carried that line in untouched, and the PR merged at 00:00:20Z with it. The rewrite itself covers the line: livespec's own v1.202.0 bump (f2acd171) moved its incident-ci line, because that line was already on master when the bump was computed. The defect is the stale base: nothing re-runs the pin rewrite on an open bump PR after its base gains pin-bearing lines. Implementing item: livespec-dev-tooling-m5cpnl (plan expedited-incident-response-flag, epic livespec-dev-tooling-bqnzcm); topic named by legacy-coordinator-agent. It aligns with the pending a-bump-to-a-livespec proposal, which adds a readiness wait to the same subsection and does not touch the rewrite.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Cross-repo coordination automation surface", subsection "#### `reusable-bump-pin-from-dispatch.yml`", insert the following paragraph after the paragraph that begins "Rewrite path:":

Stale-base refresh: a bump PR is computed against the default branch as it stood when the PR was opened, and the default branch can gain, before the PR merges, a new pin that §"Pin autodiscovery rules" discovers for the PR's `source_repo`. While a bump PR (title `chore(deps): bump <source_repo> pin to <tag>`, on a branch the bump automation owns) is open and its branch is behind the consumer's default branch, the bump automation MUST refresh it: reset the bump branch to the default branch's tip, re-run the same pin rewrite for that `source_repo` and `tag`, commit the result with a `chore:` subject per §"PR commit-message convention", and push it with `--force-with-lease` against the branch head it read. The guarantee is observable on the REFRESHED PR HEAD: every pin §"Pin autodiscovery rules" discovers for `source_repo` on that head names `<tag>`, including a pin the default branch gained after the PR was opened. It is a guarantee about the head, not the merged tree: required-status-check `strict` is OFF (§"`branch_protection_alignment` check") and the PR merges with `--auto --rebase` (§"Fallback to known-good pin"), so the tree that merges is one GitHub composes, not one the automation pushed, and the default branch can still gain such a pin between a refresh and the merge. `reusable-pin-freshness.yml` is the backstop for that remaining race: each sweep MUST also refresh, in the same way, every open bump PR whose head carries a discovered pin for its `source_repo` that does not name the PR's `<tag>`. Trigger surface: the consumer's existing `bump-pin-from-dispatch.yml` shim MUST additionally run on `push` to the default branch, and on that trigger `reusable-bump-pin-from-dispatch.yml` MUST refresh every open bump PR of the consumer instead of opening one; no shim is added (a full participant keeps its three shims and a receiving-only consumer its two, per §"Bump-pin policy"), and only that shim's trigger list and this workflow's invocation change. When the refresh's rewrite changes no discovered pin relative to the default branch's tip beyond what the PR already carries, and the PR head is not behind, the bump automation MUST leave the PR branch as it is and push no commit. Rewriting the bot-owned bump branch this way is permitted: §"Fallback to known-good pin" forbids silently force-pushing PAST A FAILING CHECK ("MUST NOT silently force-push past a failing check"), and a refresh does not do that, because the pushed head gets a fresh run of every required check before auto-merge can complete. The refresh MUST NOT touch any branch the bump automation does not own, and it does not change §"Fallback to known-good pin".

In SPECIFICATION/scenarios.md, append the following scenario after "## Scenario: a dev-tooling release bump rewrites the factory-reach image pin with the workflow image pins":

## Scenario: a bump PR whose base gains a pin-bearing line at the old tag is refreshed so that line names the target tag

Given a consumer bump PR `chore(deps): bump thewoolleyman/livespec-dev-tooling pin to v2` whose rewrite moved every pin §"Pin autodiscovery rules" discovers for that source on the default branch, as it stood when the PR opened, from v1 to v2

And the default branch then gains a new such pin that names v1

When the consumer's default branch advances while the bump PR is open

Then the bump automation MUST push to the PR branch, with --force-with-lease, a head reset to the default branch's tip in which that new pin names v2

And no pin §"Pin autodiscovery rules" discovers for that source on the refreshed PR head names v1

And when a later refresh finds the PR head current and no discovered pin to rewrite, it MUST push no commit

Owed at revise: the revise that ratifies this proposal MUST add a `tests/heading-coverage.json` row for the new scenario heading with `"test": "TODO"`, a reason naming the tier the owed test runs at (integration tier or above) and `"work_item": "livespec-dev-tooling-m5cpnl"`, and MUST regenerate `tests/heading-coverage-debt.json` with `just generate-heading-coverage-debt-register`.

Related, also out of scope: a release-please release PR whose contents were computed on an older base can carry a stale pin line in the same way; measured on 2026-11-13, livespec-overseer 65dce2d8 (#2972) rolled the dev-tooling pin back to v1.200.0. That sibling class is owned by plan ci-runtime-and-cost as a required pre-merge check against the current base, and this proposal does not cover it.

Out of scope: livespec-overseer's ruleset 27138269 not requiring ci-green, which let the stale-line PR merge red. legacy-coordinator-agent routed it to plan ci-runtime-and-cost as a fleet sweep.
