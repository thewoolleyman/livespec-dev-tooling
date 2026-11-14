---
topic: dev-host-retention-s-uv
author: claude-opus-5-5
created_at: 2026-11-14T17:24:18Z
---

## Proposal: Dev host retention's uv-cache ownership walk is budgeted, records its start, and carries on from changed paths after a cut-off

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend the uv-cache bullet of Dev host disk retention. The ownership walk is bounded by a budget role variable (default 300 s). It records each walk's start time; later walks visit only paths changed since, and a walk cut off by its budget still records its start, so the full walk is never repeated. One log line gives the walk's duration and outcome. A scenario is added.

### Motivation

livespec-dev-tooling-umy3ry, plan dev-host-disk-retention (livespec-dev-tooling-qgwxo4), is a reproduced defect, coordinator-ruled on 2026-11-10. On vmi3006760 the uv cache holds 5,319,730 entries, and a full ownership walk took 1,746 s. That is over the 300 s budget role dev_host_retention's script carries (`UV_OWNERSHIP_BUDGET_SECONDS`), so every walk is cut off. Measured on manual runs at 2026-11-10 07:41Z and 20:58Z. The script records its incremental stamp only when a walk completes, so no stamp was ever written (`/var/lib/livespec-dev-host-retention/` is empty), and every run restarts the full walk. A foreign path deep in the cache is never reached, which is the 2026-10-21 failure livespec-dev-tooling-4rcuxp was meant to close. On 2026-11-14 the coordinator (45f74b) ruled this spec-first, with no clause release. The ratified bullet requires ownership to be restored before the prune, but it states none of the item's own behaviour: the walk's budget, the recorded start, the changed-paths-only later walks, the carry-over from a cut-off walk, or the log line. This proposal states them, so that umy3ry is released against this topic. The carry-over has one deliberate edge, stated in the clause. A path that was foreign before the first recorded walk and has not changed since is outside every later walk. The full walk of 2026-11-10 found no foreign path among 5.3M entries, and the prune's existing log-and-continue rule names any such path that blocks it. "Re-owned" means a status change, so the implementation uses the inode change time and not only the modification time: a root `chown` of an existing path does not change its mtime.

### Proposed Changes

**1. `non-functional-requirements.md` §"Dev host disk retention", **What one run reclaims, and what it leaves.****. Replace the uv-cache bullet:

> - It MUST prune the uv cache AS THE USER THAT OWNS THAT CACHE. The run executes with root privilege so that, before the prune, it MUST restore the cache owner's ownership of every path in the cache that another user owns, and it MUST then run the prune as the cache owner, the role's configured retention user. When the prune still cannot remove a path, the run MUST log that path and continue with its remaining steps, never abort.

with:

> - It MUST prune the uv cache AS THE USER THAT OWNS THAT CACHE. The run executes with root privilege so that, before the prune, it MUST restore the cache owner's ownership of every path in the cache that another user owns, and it MUST then run the prune as the cache owner, the role's configured retention user. When the prune still cannot remove a path, the run MUST log that path and continue with its remaining steps, never abort.
>   - The ownership walk that restores ownership MUST be bounded by the ownership-walk budget, a role variable. When the budget runs out, the walk stops and the prune still runs.
>   - Each walk MUST record the time it started. A later walk MUST visit only the paths created, modified or re-owned since the start of the last walk that recorded one, and the first walk, with nothing recorded, visits the whole cache. A walk cut off by its budget MUST still record its start, so the next run carries on from the changed paths and never restarts the full walk. A path that another user owned before the first recorded walk began, and that has not changed since, is outside every later walk; if the prune then cannot remove it, the log-and-continue rule above applies.
>   - The run MUST log one ownership-walk line naming how long the walk ran, whether it completed or was cut off by its budget, and how many paths it handed back.

In **Alert before full.**, add the ownership-walk budget to the list of role variables documented in `HOST_VARS.md`, with a default of 300 seconds. Take that sentence as it stands when this revise lands: dev-host-retention-reports-merged-aged-worktrees, the-dev-host-capacity-alert and dev-host-tmp-refills-about also edit it.

**2. `scenarios.md`.** Append:

> ## Scenario: dev host retention's uv-cache ownership walk cut off by its budget carries on from the changed paths
>
> Given a dev host whose uv cache is too large for the ownership walk to finish inside its budget, and holds no recorded walk start
>
> When the retention run executes
>
> Then the walk stops at its budget, the prune still runs, and the run logs the walk as cut off with its duration
>
> And the walk's start time is recorded
>
> When a path owned by another user is written into the cache, and the retention run executes again
>
> Then the second walk visits only the paths changed since the recorded start, hands that path back to the cache owner before the prune, and logs the walk as completed

**3. `tests/heading-coverage.json` (the revise commit).** Add a spec-first `"test": "TODO"` row for the scenario, with `work_item` livespec-dev-tooling-umy3ry. Its reason names the integration tier. Register it in the debt register.
