---
topic: a-pin-bump-pr-whose
author: claude-opus-5-5 (expedited-incident-response-flag)
created_at: 2026-11-13T00:55:43Z
---

## Proposal: An open bump PR whose base gains a pin-bearing line is refreshed so the merged tree names the target tag

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a stale-base refresh rule to reusable-bump-pin-from-dispatch.yml in contracts.md section Cross-repo coordination automation surface. While a bump PR is open and behind its consumer's default branch, the bump automation brings the branch up to date, re-runs the same pin rewrite for the PR's source_repo and tag, and pushes the result, so every pin-bearing line on the merged tree names the target tag, including lines the default branch gained after the PR opened. A refresh that rewrites nothing pushes no commit. One scenario is added to scenarios.md.

### Motivation

Measured on 2026-11-13. livespec-overseer master went red at 88221220 (run 43333510978: check-metadata-batch, check-ci-single-container-image). Bump PR livespec-overseer#2966 (dev-tooling pin to v1.202.0) was opened at 22:16:49Z, and its rewrite moved every livespec-fabro-sandbox image line then on master to python-v1.202.0. At 22:5xZ livespec-overseer#2963 merged a NEW image line, the incident-ci job's container, at python-v1.200.0. A merge of master into the bump branch (9862305b2, 22:58:23Z) carried that line in untouched, and the PR merged at 00:00:20Z with it. The rewrite itself covers the line: livespec's own v1.202.0 bump (f2acd171) moved its incident-ci line, because that line was already on master when the bump was computed. The defect is the stale base: nothing re-runs the pin rewrite on an open bump PR after its base gains pin-bearing lines. Implementing item: livespec-dev-tooling-m5cpnl (plan expedited-incident-response-flag, epic livespec-dev-tooling-bqnzcm); topic named by legacy-coordinator-agent. It aligns with the pending a-bump-to-a-livespec proposal, which adds a readiness wait to the same subsection and does not touch the rewrite.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Cross-repo coordination automation surface", subsection "#### `reusable-bump-pin-from-dispatch.yml`", insert the following paragraph after the paragraph that begins "Rewrite path:":

Stale-base refresh: a bump PR is computed against the default branch as it stood when the PR was opened, and the default branch can gain a new pin-bearing line before the PR merges. While a bump PR (title `chore(deps): bump <source_repo> pin to <tag>`) is open and its branch is behind the consumer's default branch, the bump automation MUST bring the PR branch up to date with the default branch, re-run the same pin rewrite for that `source_repo` and `tag` over the result, and push the result to the PR branch, so that every pin-bearing line on the tree that merges names `<tag>`, including a line the default branch gained after the PR was opened. The refresh MUST run each time the consumer's default branch advances while such a PR is open, and on any update of the PR branch that brings it up to date with the default branch. When the re-run rewrite changes no pin-bearing line, the bump automation MUST leave the PR branch as it is and push no commit. The refresh rewrites pins only; it MUST NOT force-push past a failing check, and it does not change §"Fallback to known-good pin".

In SPECIFICATION/scenarios.md, append the following scenario after "## Scenario: a dev-tooling release bump rewrites the factory-reach image pin with the workflow image pins":

## Scenario: a bump PR whose base gains a pin-bearing line at the old tag merges with that line on the target tag

Given a consumer bump PR `chore(deps): bump thewoolleyman/livespec-dev-tooling pin to v2` whose rewrite moved every pin-bearing line on the default branch, as it stood when the PR opened, from v1 to v2

And the default branch then gains a new pin-bearing line that names v1

When the consumer's default branch advances while the bump PR is open

Then the bump automation MUST push to the PR branch a tree, brought up to date with the default branch, in which that new line names v2

And no pin-bearing line on the PR branch names v1

And when a later refresh finds no pin-bearing line to rewrite, it MUST push no commit

Out of scope: livespec-overseer's ruleset 27138269 not requiring ci-green, which let the stale-line PR merge red. legacy-coordinator-agent routed it to plan ci-runtime-and-cost as a fleet sweep.
