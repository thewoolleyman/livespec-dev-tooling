---
topic: cvstale-reclassify-workflow-check
author: livespec-implementer (epic li-cvaudit / li-cvstale)
created_at: 2026-06-02T16:27:04Z
---

## Proposal: Reclassify no_stale_revise_branches as a revise-workflow check; eliminate the --allow-stale-branches carve-out

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Reclassify `no_stale_revise_branches` from a per-commit canonical check into a revise-workflow check. The check moves from `livespec_dev_tooling/checks/` to a new `livespec_dev_tooling/workflow_checks/` package, so the canonical-set derivation (which walks `checks/*.py`) auto-excludes it and it leaves the per-commit `just check` aggregate and the wiring-completeness invariant. Its load-bearing enforcement becomes the mandatory `/livespec:revise` pre-step, which is the sole caller and fails hard (exit 4) on any stale branch. The `--allow-stale-branches` downgrade flag is removed: with no per-commit-aggregate invocation there is no longer anything that needs a downgrade lever, so the carve-out is eliminated rather than retained as an escape hatch.

### Motivation

Epic li-cvaudit, sub-task li-cvstale: the carve-out ratio (escape-hatch flags vs invariants) signals a mis-scoped invariant. The check was wired into the per-commit aggregate AND carried an `--allow-stale-branches` downgrade flag. Removing the per-commit-aggregate wiring and reclassifying it as a revise-workflow check removes the need for the downgrade lever entirely — the check now always fails hard on stale branches at the one place it actually runs (the revise pre-step). User has pre-approved this exact reclassification.

### Proposed Changes

In SPECIFICATION/contracts.md §"Shared check inventory": (1) remove `no_stale_revise_branches` from the "Shared (migrate to `livespec_dev_tooling/checks/`)" bullet's CI-alignment gates enumeration; (2) add a new classification bullet "Revise-workflow checks (`livespec_dev_tooling/workflow_checks/`)" describing shared, project-agnostic checks invoked by a specific workflow step (the `/livespec:revise` pre-step) rather than by the per-commit `just check` aggregate — they live under `workflow_checks/` (NOT `checks/`) so the canonical-set derivation auto-excludes them and they are NOT subject to the wiring-completeness invariant; `no_stale_revise_branches` is the first such check. In §"`no_stale_revise_branches` check": (3) note the revise-workflow classification and the `workflow_checks/` location; (4) change the invocation path to `python -m livespec_dev_tooling.workflow_checks.no_stale_revise_branches`; (5) state that the revise pre-step is the sole caller and load-bearing enforcement; (6) state that the `--allow-stale-branches` downgrade flag is REMOVED and the check always fails hard (exit 4) on any stale branch.
