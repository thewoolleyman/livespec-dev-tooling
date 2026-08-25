---
topic: workflow-checks-release-scope
author: claude-opus-5
created_at: 2026-08-25T23:50:09Z
---

## Proposal: Widen the workflow-checks category to admit release-workflow checks

### Target specification files

- SPECIFICATION/contracts.md

### Summary

§"Shared check inventory" defines `livespec_dev_tooling/workflow_checks/` as REVISE-workflow checks, scoped to "a specific workflow step -- the `/livespec:revise` pre-step". A release-gate check is the same SHAPE (shared, project-agnostic, invoked by a named workflow step, deliberately outside the canonical aggregate) but a different STEP, so the category as worded does not admit it. Widen the category to workflow checks generally, enumerating revise-workflow and release-workflow as its two kinds. Purely additive: no existing member changes, no canonical slug is added, and no consumer is reddened.

### Motivation

livespec-runtime released 0.21.5 for a change its own ratified §"Versioning" classifies as Major -- it tightened a parse contract so previously valid inputs raise -- because release-please derives the bump purely from the Conventional-Commit type and the commit was typed `fix:`. It was caught only by a human reading the release PR title with auto-merge already armed, and corrected out-of-band via a `Release-As:` footer. The accidental 0.21.4 had the same root. Nothing binds a ratified version classification to the bump the automation computes, and that gap is generic to every fleet repo pairing release-please with a ratified versioning rule.

The check that closes it MUST NOT live in `livespec_dev_tooling/checks/`. The canonical set is filesystem-derived -- `canonical_check_slugs()` states that adding a `checks/<name>.py` file automatically extends the returned tuple -- and `aggregate_completeness` rule 1 requires every canonical slug to appear in each consumer's wired targets. Adding it there would redden EVERY governed consumer on its next pin bump until each wires the slug into its justfile and its CI matrix. This specification already records exactly that hazard for `charters/`: "relocating these modules under `checks/` would silently conscript the whole fleet." The same reasoning applies here, and `workflow_checks/` already exists as the home for it -- the category is simply worded one step too narrowly.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Shared check inventory", REPLACE the bullet currently headed "**Revise-workflow checks (`livespec_dev_tooling/workflow_checks/`).**" with a bullet headed "**Workflow checks (`livespec_dev_tooling/workflow_checks/`).**".

The replacement MUST preserve, verbatim in substance, the existing mechanical rationale: that these are shared, project-agnostic checks invoked by a specific workflow step rather than by the per-commit `just check` aggregate; that they live under `workflow_checks/` and NOT `checks/` so the canonical-set derivation auto-excludes them; and that they are therefore NOT subject to the wiring-completeness invariant and NOT members of the canonical aggregate.

It MUST then enumerate TWO kinds, and state that the list is open to further kinds admitted by amendment:
  - REVISE-workflow checks, invoked by the `/livespec:revise` pre-step. `no_stale_revise_branches` remains the member; its load-bearing enforcement is the mandatory pre-step, which fails hard on any stale branch.
  - RELEASE-workflow checks, invoked by a consumer's release-gating step (for example a `pre-push` script or a release job) rather than by the per-commit aggregate. These exist so a consumer can bind a ratified release rule to what its release automation actually computes.

The replacement MUST state explicitly that placement under `workflow_checks/` is LOAD-BEARING rather than a filing preference, for the same reason the `charters/` bullet already records: a module under `checks/` becomes a canonical slug, and a canonical slug obliges EVERY consumer to wire it into `just check` and its CI matrix, so misplacing a workflow check silently conscripts the fleet.

It MUST also state that adopting any workflow check is per-consumer OPT-IN -- a consumer wires it into the workflow step it chooses -- so adding a member to this category never obliges an existing consumer to act and never reddens one.

No `##` heading is added, renamed, or removed; only the text of one bullet under the existing §"Shared check inventory" heading changes.
