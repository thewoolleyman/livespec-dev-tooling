---
topic: dev-host-retention-reports-merged-aged-worktrees
author: claude-opus-5-5
created_at: 2026-11-14T15:25:34Z
---

## Proposal: Dev host retention reports merged, aged worktrees and removes none

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a report-only leg to the retention run. It names each linked worktree under `~/.worktrees` whose content is provably on its default branch and that is older than a report period, with its size, gives their total, and sends one ntfy notification when the total reaches a threshold. It never removes a worktree; that stays with each worktree's owner.

### Motivation

The same 2026-11-14 climb was mostly worktrees. `~/.worktrees` held 153G: livespec-orchestrator-beads-fabro 53G in 117 worktrees, livespec-dev-tooling 51G in 217, and the rest across thirteen more repositories. Each seat is meant to remove its own merged worktrees, but nothing reports when they don't. Under legacy-coordinator-agent's ruling (9b979c55, item 2), a one-time sweep removed 251 worktrees whose content was provably on master, 77.4G, taking / from 87% to 76% (comment DEV-HOST-WORKTREE-RECLAIM-RESULT on livespec-dev-tooling-qgwxo4). It skipped 201 for their owners. The coordinator approved a durable leg that REPORTS rather than removes (item 3). A worktree a session is about to use can look idle, clean and merged, for example one freshly created from master that has no commits yet. Removal stays an owner's act, or a ruled sweep like this one. The report turns a silent climb into a named list well before the capacity threshold. Image reclaim is not part of this proposal. Role `container_reclaim` already runs hourly on `dev_hosts` and `sandbox_hosts`, and removes unused images older than 72 h (`docker image prune -af --filter until=72h`). The 27.09 G pruned on 2026-11-14 were all 21 h to 2 days old, so that existing leg would have reached them within a day. The climb was the worktrees, 153 G against 27 G. FLEET SCOPE: seats create `~/.worktrees` on vmi3006760 and on hetzner-xubuntu. This section governs the host `ansible/dev-host.yml` selects. hetzner-xubuntu is provisioned by hetzner-xubuntu-info, which owns its own retention, so the matching leg there is filed in that repository the same day.

### Proposed Changes

**1. `non-functional-requirements.md` §"Dev host disk retention", **What one run reclaims, and what it leaves.****. Insert this bullet after the bulk-dump directory bullet:

> - It MUST REPORT, and MUST NOT remove, each linked worktree under the retention user's worktree root (`~/.worktrees`) whose content is provably on its repository's default branch and that is older than the worktree report period. A worktree's content is provably on the default branch when its working tree has no change and no untracked, non-ignored file, and its HEAD is an ancestor of the remote default branch, or every commit of HEAD not on it is patch-equivalent to one that is. Its age is the time since its index was last written. The report MUST go to the run's log. It MUST name each such worktree, its repository, its branch (or `detached` when HEAD is detached) and its size, and MUST give their total. When that total is at or above the worktree report threshold, the run MUST publish one notification to the host's ntfy topic naming the total and the count. Removal stays with each worktree's owner, because a worktree a session is about to use can look idle.

In **Alert before full.**, replace the last sentence:

> The two thresholds, the scratch retention period, the bulk-dump directory, its size cap and the repeat interval MUST be role variables documented in the role's `HOST_VARS.md`, with defaults of 85% for the root filesystem, 75% for `/tmp`, 6 hours for scratch retention, `/var/tmp/livespec-dumps` for the bulk-dump directory, 20 G for its cap and 1 hour for the repeat interval.

with:

> The two thresholds, the scratch retention period, the bulk-dump directory, its size cap, the repeat interval, the worktree report period and the worktree report threshold MUST be role variables documented in the role's `HOST_VARS.md`, with defaults of 85% for the root filesystem, 75% for `/tmp`, 6 hours for scratch retention, `/var/tmp/livespec-dumps` for the bulk-dump directory, 20 G for its cap, 1 hour for the repeat interval, 3 days for the worktree report period and 40 G for the worktree report threshold.

The 3-day period gives a seat time to finish its own post-merge cleanup. 40 G is about 6% of vmi3006760's 678 G root filesystem, roughly two to three days of the growth measured from 2026-11-08 to 2026-11-14.

**2. `scenarios.md`.** Append:

> ## Scenario: dev host retention reports merged, aged worktrees and removes none
>
> Given a dev host whose worktree root holds a worktree whose branch is merged into the remote default branch, clean and older than the worktree report period
>
> And a worktree with an uncommitted change
>
> And a worktree whose branch has a commit not on the default branch
>
> When the retention run executes
>
> Then the run's log names the merged, clean, aged worktree with its repository, branch and size
>
> And it names neither of the other two
>
> And all three worktrees are still present after the run

**3. `tests/heading-coverage.json` (the revise commit).** Add a spec-first `"test": "TODO"` row for the scenario, with `work_item` livespec-dev-tooling-yratl6, which adds the report leg. Its reason names the integration tier. Register it in the debt register. Note for the revise: the-dev-host-capacity-alert and dev-host-tmp-refills-about also edit **Alert before full.**, so take them in queue order and re-base this sentence on whichever lands first.
