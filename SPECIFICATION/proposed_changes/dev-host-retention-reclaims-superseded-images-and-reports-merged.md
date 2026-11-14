---
topic: dev-host-retention-reclaims-superseded-images-and-reports-merged
author: claude-opus-5-5
created_at: 2026-11-14T15:02:43Z
---

## Proposal: Dev host retention removes superseded unused docker images, keeping each repository's newest

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Widen the retention run's docker leg beyond dangling images. A tagged image that no container uses and that is older than a new image retention period is removed. The exception is its repository's most recently created image, which is kept, as is every image a container uses.

### Motivation

On 2026-11-14 vmi3006760's root filesystem reached 92% (616G of 678G), climbing about 14 to 20G a day from 75% on 2026-11-08. The capacity check had been alerting hourly since it crossed 85%. The docker store held 27.09G in 11 tagged images and no container: livespec-fabro-sandbox python-rust-agent and python-agent v1.200.0 to v1.207.0, at 3.2 to 4.3G each, plus two livespec-orchestrator builds, each pulled as a release rolled. The ratified bullet removes only dangling images and "MUST leave every tagged image" in place, so every superseded sandbox release stays forever. legacy-coordinator-agent (9b979c55) authorized a one-time `docker image prune -a`, which reclaimed 27.09G at 14:40Z (comment DEV-HOST-DOCKER-IMAGE-PRUNE-ONE-TIME on livespec-dev-tooling-qgwxo4). It ruled the durable leg a committed role change. Every pruned image was 21 hours to 2 days old, so age alone is the wrong key. A one-week period would keep them all, and a short one would delete the current sandbox image a factory run is about to use. Keeping each repository's newest image keeps the warm image, and the age period stops a just-pulled image from being removed. Images are re-pullable from their registries, so the removal is recoverable.

### Proposed Changes

**1. `non-functional-requirements.md` §"Dev host disk retention", **What one run reclaims, and what it leaves.****. Replace the first bullet ("It MUST remove dangling docker images and MUST leave every tagged image and every image a container uses in place.") with:

> - It MUST remove dangling docker images. It MUST also remove a tagged image that no container uses when that image is older than the image retention period, unless it is the most recently created image of its repository. It MUST leave every image a container uses, and each repository's most recently created image, in place, whatever their age.

And in **Alert before full.**, in the sentence that lists the role variables ("The two thresholds, the scratch retention period, ..."), add the image retention period to that list.

**2. `scenarios.md`.** Append:

> ## Scenario: dev host retention removes superseded unused images and keeps each repository's newest
>
> Given a dev host whose docker store holds three tagged images of one repository, none used by a container, each older than the image retention period
>
> And a fourth image, of another repository, that a stopped container uses
>
> And a dangling image
>
> When the retention run executes
>
> Then the two older images of the first repository and the dangling image are removed
>
> And that repository's most recently created image and the container's image remain
>
> And the run's log names each removed image

**3. `tests/heading-coverage.json` (the revise commit).** A spec-first `"test": "TODO"` row for the scenario, with work_item the item that widens the role's docker leg. Its reason names the integration tier. Register it in the debt register.

## Proposal: Dev host retention reports merged, aged worktrees and removes none

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a report-only leg to the retention run. It names each linked worktree under `~/.worktrees` whose content is provably on its default branch and that is older than a report period, with its size, gives their total, and sends one ntfy notification when the total reaches a threshold. It never removes a worktree; that stays with each worktree's owner.

### Motivation

The same 2026-11-14 climb was mostly worktrees. `~/.worktrees` held 153G: livespec-orchestrator-beads-fabro 53G in 117 worktrees, livespec-dev-tooling 51G in 217, and the rest across thirteen more repositories. Each seat is meant to remove its own merged worktrees, but nothing reports when they don't. Under legacy-coordinator-agent's ruling (9b979c55, item 2), a one-time sweep removed 251 worktrees whose content was provably on master, 77.4G, taking / from 87% to 76% (comment DEV-HOST-WORKTREE-RECLAIM-RESULT on livespec-dev-tooling-qgwxo4). It skipped 201 for their owners. The coordinator approved a durable leg that REPORTS rather than removes (item 3). A worktree a session is about to use can look idle, clean and merged, for example one freshly created from master that has no commits yet. Removal stays an owner's act, or a ruled sweep like this one. The report turns a silent climb into a named list well before the capacity threshold. FLEET SCOPE: seats create `~/.worktrees` on vmi3006760 and on hetzner-xubuntu. This section governs the host `ansible/dev-host.yml` selects. hetzner-xubuntu is provisioned by hetzner-xubuntu-info, which owns its own retention, so the matching leg there is filed in that repository the same day.

### Proposed Changes

**1. `non-functional-requirements.md` §"Dev host disk retention", **What one run reclaims, and what it leaves.****. Insert this bullet after the bulk-dump directory bullet:

> - It MUST REPORT, and MUST NOT remove, each linked worktree under the retention user's worktree root (`~/.worktrees`) whose content is provably on its repository's default branch and that is older than the worktree report period. A worktree's content is provably on the default branch when its working tree has no change and no untracked file, and its HEAD is an ancestor of the remote default branch or every commit of HEAD not on it is patch-equivalent to one that is. Its age is the time since its index was last written. The report MUST name each such worktree, its repository, its branch and its size, and MUST give their total. When that total is at or above the worktree report threshold, the run MUST publish one notification to the host's ntfy topic naming the total and the count. Removal stays with each worktree's owner, because a worktree in use by a session can look idle.

And in **Alert before full.**, add the worktree report period and the worktree report threshold to the list of role variables documented in `HOST_VARS.md`.

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
> Then the run's report names the merged, clean, aged worktree with its repository, branch and size
>
> And it names neither of the other two
>
> And all three worktrees are still present after the run

**3. `tests/heading-coverage.json` (the revise commit).** A spec-first `"test": "TODO"` row for the scenario, with work_item the item that adds the report leg. Its reason names the integration tier. Register it in the debt register.
