---
topic: worktree-reap-liveness
author: claude-opus-5-5
created_at: 2026-10-22T00:23:13Z
---

## Proposal: worktree-reap never removes a live or factory-owned worktree

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a clause to contracts.md §"CLI surface" requiring the canonical worktree-discipline pack's `reap` verb to SKIP, and never remove, a worktree a live process holds (cwd or open file), a worktree whose liveness it cannot establish, and a factory-owned `fabro-source-<id>` worktree, with `--force` overriding none of these skips. Add two scenarios.

### Motivation

Measured 2026-10-21 ~18:3xZ during the coordinator R510 dev-host disk sweep (work-item livespec-dev-tooling-7i2z5j). A dry run of `just worktree-reap` across the four repositories that carry the pack listed nine `fabro-source-<uuid>` worktrees as REMOVE ("merged into origin/master: ancestor of origin/master"). Three were the working directory of a live `fabro run` process at that moment, serving runs for livespec-dev-tooling-543kob, overseer-uzvcbn.5 and bd-ib-bvg2w2. A factory source checkout is created at master, so the merged-ness test always reads it as merged, and `worktree_reap` in the pack's `worktree-lib.sh` has no liveness test. An `--execute` would have removed a running run's source tree from under it. The coordinator has held every fleet-wide `just worktree-reap --execute` since (R512). No clause states what `reap` must leave alone, so the defect cannot be judged against the spec, and the fix's Definition of Done has no governing heading (dod-preflight refused it on exactly that, 2026-10-22). Two choices are deliberate. Liveness fails safe: a reaper that cannot tell is a command that deletes work, so it skips. Factory-owned source worktrees are skipped by NAME rather than by a factory run-board lookup: the board needs an authenticated factory client that a consuming repository's host may not hold, and a run that is paused or blocked with its tree preserved holds no process, so a liveness test alone would not protect it. The factory owns its source checkouts' lifecycle.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"CLI surface", insert the following paragraph immediately after the paragraph beginning `Beyond the check modules, the library exposes three operational CLI modules`:

**The pack's `reap` verb never removes a live or factory-owned worktree.** The canonical pack's `just worktree-reap` (a dry run) and `just worktree-reap --execute` select secondary worktrees to remove. Before `reap` selects a worktree for removal it MUST establish that no live process holds it. A worktree that is the current working directory of a live process, or in which a live process holds an open file, MUST be reported as SKIP with a reason naming that process's pid, and `--execute` MUST leave it on disk. When `reap` cannot establish whether a live process holds a worktree, it MUST report that worktree as SKIP, never as REMOVE. A worktree the Fabro factory created as a run's source checkout, whose directory name is `fabro-source-<id>`, is factory-owned: `reap` MUST report it as SKIP with a reason saying it is factory-owned, and MUST NOT remove it. `--force` overrides only the clean-and-merged test; it MUST NOT override any of these skips.

In `SPECIFICATION/scenarios.md`, append these two scenarios:

## Scenario: worktree-reap leaves a worktree that a live process holds

Given a repository with the canonical worktree-discipline pack installed

And a clean secondary worktree whose branch is merged into the base and which is the working directory of a live process

When `just worktree-reap --execute --force` runs

Then that worktree MUST be reported as SKIP with a reason naming the live process's pid

And that worktree MUST remain on disk

## Scenario: worktree-reap never removes a factory-owned source worktree

Given a repository with the canonical worktree-discipline pack installed

And a clean secondary worktree named `fabro-source-<id>` whose head is merged into the base and which no live process holds

When `just worktree-reap --execute --force` runs

Then that worktree MUST be reported as SKIP with a reason saying it is factory-owned

And that worktree MUST remain on disk

The two new `## Scenario` headings each need a `tests/heading-coverage.json` entry (test `TODO`, work_item livespec-dev-tooling-7i2z5j) and a regenerated `tests/heading-coverage-debt.json` row, co-edited in the revise.
