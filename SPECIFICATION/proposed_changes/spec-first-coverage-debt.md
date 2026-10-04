---
topic: spec-first-coverage-debt
author: codex-gpt-6
created_at: 2026-10-04T05:28:58Z
---

## Proposal: admit-owned-spec-first-debt-without-reopening-covered-headings

### Target specification files

- non-functional-requirements.md
- scenarios.md

### Summary

Preserve the existing-debt ratchet while admitting mechanically registered, owned transitional coverage debt for genuinely new specification headings. Emptying the legacy register must not disable spec-first development.

### Motivation

The user authorized this scoped upstream repair after orchestrator plan bd-ib-q622ls was blocked: push gate 20261004T013331Z-1893607 rejected the newly ratified Scenario 135 TODO as unregistered_todo; adding its owned register row would be register_grew. Charter fleet-heading-coverage-convergence D2 and research/004 explicitly preserve spec-first placeholders, but D3 and the v064 frozen-key rule prohibit them. This proposal explicitly supersedes that conflicting part of D3 and D9, preserving D1, D2, D4 and D5: real tests remain owed, old debt converges, and no unowned or permanent exemption is introduced. It does not authorize fake coverage, hook bypasses, or silently weakening release-tier checks.

### Proposed Changes

In non-functional-requirements.md, Testing approach / Scenario-tier coverage, replace the unconditional frozen-key growth ban and automatic retirement-at-zero rule with the following contract. Every TODO MUST still have an exact-key entry in tests/heading-coverage-debt.json; unregistered TODOs MUST fail. Existing registered debt MUST only shrink on resolution or removal. A new register key MAY be admitted only as spec-first debt: the same change introduces its exact H2 heading into the governed live specification, its heading and coverage key are absent from the comparable pre-change HEAD specification and coverage registry, the coverage row declares TODO with a nonempty work_item and an acknowledgment that a real test at the required tier is owed, and mechanical regeneration supplies a matching owner and first_seen date. The exception MUST NOT apply to a pre-existing heading, a real-test-to-TODO regression, an orphan or dangling key, or a registry-only change. Renaming or removing an existing heading in the same specification file MUST NOT be used to admit replacement debt: a change that removes a heading in that file MUST supply real coverage for replacement headings. An unreadable or unavailable comparison MUST NOT establish new-heading eligibility; report the evidence failure and refuse the admission, while preserving the existing first-adoption baseline behavior rather than changing adoption policy in this repair. The comparison is against HEAD during authoring; committed admitted rows remain ordinary registered debt at pre-push and CI, with no temporary environment override. Once admitted, first_seen MUST NOT move later than the recorded date, owner changes MUST stay synchronized with the coverage row, and all normal reason, liveness, age, scope, stale-entry and schema checks MUST still apply. Liveness and clock-based age remain release-tier-only; authoring admission MUST depend only on repository data. Mechanical generation MUST preserve existing first_seen dates and add only genuinely new rows rather than resetting the register's age. A register with zero rows MUST still permit the same narrowly defined new-heading admission; zero does not retire the acknowledgment/ownership or scoped-authorship machinery needed for future ratification. No free-text reason is an exemption from writing a real test.

In scenarios.md, amend the existing debt-register scenarios atomically with the clause: unregistered TODO still fails even for a new heading; new registered debt fails unless it satisfies the spec-first admission conditions; new H2 plus matching owned generated debt passes authoring and remains valid after commit; pre-existing heading, covered-to-TODO regression, missing/mismatched owner, missing required-tier acknowledgment, dangling key, registry-only addition, removed-and-renamed heading, and unreadable comparison each fail; empty register admits a genuinely new owned heading but rejects regressions; resolving debt still requires register removal; generator preserves first_seen and repeated regeneration is identical; an attempted date reset fails and stale/closed-owner debt still fails the existing release checks. Use Given/When/Then clauses. Update heading-coverage links whenever a heading changes; coverage for these new branches MUST be integration-tier consumer tests, not merely structural assertions about this prose. Existing scenarios may be expanded without inventing new headings. The later factory implementation work item owns the additional executable coverage.
