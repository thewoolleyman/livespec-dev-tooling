---
topic: fleet-arc-runners-set-up
author: claude-opus-5-5:ci-cache-optimization
created_at: 2026-11-03T15:17:17Z
---

## Proposal: Action-archive cache tier for the runner pool

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Name a node-local action-archive cache as a tier of §"Runner-pool build cache tiers". The stock runner reads it in place of codeload.github.com. A trusted populator fills it from the `uses:` refs pinned on the routed repositories' default branches, and a missing or faulty entry degrades the job to a normal download.

### Motivation

Measured 2026-11-03 14:20Z over the previous 6 h across the seven fleet repositories: 4,359 job attempts, 10 failed at Set up job. All 10 were the runner's own download of actions/checkout from codeload.github.com (9 HTTP 429, 1 'action could not be found'), all on k3s ARC runners, in one 14-minute burst. Hosted runners showed none. The pool's runners share one egress, so a burst of job starts exhausts codeload's rate limit for the whole pool. The `Set up job` step also costs about 45 raw k3s job-hours a week (plan ci-cache-optimization, research 002). The stock runner already supports the fix: actions/actions-runner 2.336.0 reads ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE, a directory of pre-downloaded action archives, before calling codeload. The section today states the general pool-cache rules, but it does not name an action-archive tier or say what it must cover. Work item livespec-dev-tooling-a35sa4 needs that clause to exist before it can be implemented.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Runner-pool build cache tiers", append to the **Tiers.** paragraph:

"The pool MUST provide an action-archive cache: a host-side tree of the archives of every `uses:` action ref pinned in the workflow files on the default branch of each routed repository, read by the stock runner through its action-archive cache setting (`ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE`) before it downloads an action from the forge. Its store MUST live under the cache tier (the `ci-cache` role), and a `runner-only` node MUST read it over the pool's node network, or run cold, under the same rule as every other host-served cache. A routed job whose `uses:` actions are all present in the tree MUST set them up from it, without a download from the forge's archive host. The populator, the one trusted writer under **Trust by construction**, MUST add a newly pinned ref within one populator run after that pin reaches a routed repository's default branch. A ref absent from the tree, or a tree that is unreadable, MUST leave the runner to download the action as it would without the tier (**Fail-soft and kill switch**), and the fleet kill switch MUST disable this tier with the others."

In §"Runner-pool cache telemetry" **Per-job spans.**, the existing per-tier span rule then covers the new tier unchanged: one span per tier recording hit or miss. No other section changes.
