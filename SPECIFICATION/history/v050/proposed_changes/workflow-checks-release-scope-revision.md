---
proposal: workflow-checks-release-scope.md
decision: modify
revised_at: 2026-08-25T23:57:05Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-5
---

## Decision and Rationale

Accepted in substance, recorded as MODIFY for one edit beyond the proposal's named change. The widening is sound and its rationale was verified independently from THIS repo's source rather than taken from the proposal: `canonical_checks._discover_slugs` walks only `checks/` non-recursively, so `workflow_checks/` is excluded from the canonical set BY CONSTRUCTION rather than by convention, and `aggregate_completeness` rule 1 plus `ci_matrix_completeness` together oblige every consumer to wire every canonical slug into both `just check` and its CI matrix. A release-gate module placed under `checks/` would therefore redden every governed consumer on its next pin bump. This specification already records that exact hazard for `charters/`; the widening extends the same reasoning to the category that already exists for it.

ONE FACTUAL CORRECTION to the proposal's motivation, made on the record because the ratified text must not inherit an overstatement: the proposal says livespec-runtime RELEASED 0.21.5. It did not. Release-please COMPUTED 0.21.5 for the `fix:`-typed breaking commit and auto-merge was armed on the release PR, but it was caught before shipping and corrected to v0.22.0 via a `Release-As:` footer; no `v0.21.5` tag exists. The mechanism claim is unaffected and was confirmed -- `bump-minor-pre-major` never engages on an unmarked `fix:` -- and the near-miss is precisely why a mechanical gate is wanted. The candidate spec bytes make no 0.21.5 claim, so nothing ratified here carries the error.

Independent read-only Fable review returned NO BLOCKERS on contracts.md sha256 a6255a5f..., having verified the canonical-derivation claims from source, swept the tree for stale category references, and confirmed the widening obliges no consumer and reddens no repo.

## Modifications

Beyond the proposal's named change (the category bullet), this ratification also amends the `charters/` bullet in the same section. It back-referenced "the same mechanical reason the revise-workflow checks do". The rename demotes "revise-workflow checks" from the category NAME to one of two sub-kinds, so that back-reference would have pointed at a category that no longer exists -- the stale-back-reference defect this fleet keeps shipping, in the very edit that renames the thing. It now reads "the workflow checks". The reviewer confirmed this is correct AND sufficient: no category-level back-reference to the old name survives in the spec tree.

Deliberately NOT changed, and recorded so the follow-up is not lost: `livespec_dev_tooling/workflow_checks/__init__.py`, that package's `CLAUDE.md`, and a `pyproject.toml` per-file-ignore comment all still describe the PACKAGE as "Revise-workflow checks". Those are impl prose rather than spec, their citations still resolve to the surviving sub-kind bullet, and they remain factually true of the package's current single member -- but they define the package one level too narrowly under the widened category. They MUST be aligned no later than the landing of the first release-workflow module.

One non-blocking wording tension is recorded rather than silently fixed: the new text says a consumer "wires it into the workflow step it chooses", which is inexact for the revise-workflow member, since that one is carried by livespec core's mandatory pre-step and is never wired by the consumer. The load-bearing half -- that admitting a member never obliges an existing consumer to act and never reddens one -- holds regardless, and the same bullet restates the mandatory pre-step, so the specific text governs.

No `##` heading is added, renamed, or removed; heading sets are byte-identical between the ratified and candidate files, so no heading-coverage co-edit is required, and no user-observable behavior ships.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-08-25T23:54:00Z
verdict: NO BLOCKERS
proposal_stem: workflow-checks-release-scope
content_digest: 4c279822cc763de6c83af6e0414dc05c8539932a8df697372428725a103b6fb6
