---
topic: the-bump-pin-reconcile-inserts
author: claude-opus-5-5 (implement-test-performance)
created_at: 2026-11-13T13:45:34Z
---

## Proposal: The bump-pin canonical-wiring reconcile skips a slug the consumer waives and still inserts every missing unwaived slug

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The specification does not yet state the canonical-wiring reconcile that a livespec-dev-tooling bump commit performs on a consumer's `just check` aggregate and ci.yml, and the Canonical-check waivers clause names only check-aggregate-completeness and the fleet row as readers of the waiver key. This proposal states the reconcile under §"`reusable-bump-pin-from-dispatch.yml`", requires both of its halves to read the one waiver key and skip every waived slug while still inserting every missing unwaived slug, names the reconcile as a third reader in the waivers clause, and adds a scenario whose control asserts that an unwaived missing slug is still inserted.

### Motivation

Work item livespec-dev-tooling-mlhzau (plan epic livespec-dev-tooling-sv6m5p): `livespec_dev_tooling/cross_repo/justfile_canonical_reconcile.py` inserts every canonical slug missing from the consumer's resolved aggregate and never reads `canonical_check_waivers`, and `ci_yaml_canonical_reconcile.py` requires every slug that aggregate wires, so it inherits the defect. Every dev-tooling bump to livespec-console-beads-fabro, the one consumer that declares waivers today (check-heading-coverage, check-ci-single-container-image), re-inserted both waived slugs and came out red by construction: check-aggregate-completeness failed with stale_canonical_waiver, the waived checks ran and failed, and check-ci-parity flagged the new targets. Three consecutive bumps needed a hand fix: livespec-console-beads-fabro#1363 (v1.204.0, item i2rqln), #1364 (v1.205.0, item amekgk) and #1365 (v1.206.0, item fiv6uc). mlhzau's filing-stage spec-change-tier verdict (tier spec-change, partial) found that the visible text never says the bump-pin reconciles must skip waived slugs while still inserting unwaived missing ones, and named §"Cross-repo coordination automation surface" as the generalization target. Filed on legacy-coordinator-agent's ruling, 2026-11-13, which also asked for the control that an unwaived missing slug IS inserted. Out of target: the revise owes a tests/heading-coverage.json row for the new scenario heading.

### Proposed Changes

Three coordinated edits. Each uses BCP14 normative language.

**1. `SPECIFICATION/contracts.md`, §"Cross-repo coordination automation surface" → §"`reusable-bump-pin-from-dispatch.yml`".** Add this paragraph immediately after the "Sandbox-image readiness" paragraph:

> **Canonical-wiring reconcile (livespec-dev-tooling tags only).** When `source_repo` is livespec-dev-tooling, the bump commit MUST also reconcile the consumer's canonical check wiring against the canonical check set of the bumped release, through the `bump-pin-rewrite` composite Action, so that a canonical slug the release adds is wired in the same commit that moves the pin. The justfile reconcile MUST insert each canonical slug missing from the consumer's resolved `just check` aggregate (its committed `check-targets.txt` when that file exists, otherwise the justfile's `targets=(...)` array) in alphabetical position, and MUST append a zero-argument `check-<slug>:` recipe for an inserted slug that has no recipe header yet. The ci.yml reconcile MUST insert, in alphabetical position, into the consumer's `.github/workflows/ci.yml` (its `strategy.matrix.target` list or its batched accumulator block) each canonical slug that the reconciled aggregate wires and CI does not yet run, except a world gate.
>
> Both reconciles MUST read the consumer's waivers from the one key that §"Shared check inventory" **Canonical-check waivers** names: `canonical_check_waivers` under `[tool.livespec_dev_tooling]` in the consumer's `pyproject.toml`, read from the tree the bump commit is built on. Neither reconcile MAY insert a slug that key waives. The justfile reconcile MUST NOT add a waived slug to the aggregate and MUST NOT append a `check-<slug>:` recipe for it. The ci.yml reconcile MUST NOT add a `just check-<slug>` run line or a matrix target for a waived slug, even when the aggregate wires it. Every canonical slug that is missing and NOT waived MUST still be inserted by both reconciles, so a waiver never suppresses the adoption of any other slug. When that `pyproject.toml` cannot be read or parsed, or its `canonical_check_waivers` value is malformed as the waivers clause defines, both reconciles MUST apply no waiver, so that the bump PR's own `check-aggregate-completeness` reports the defect rather than the reconcile hiding it.

**2. `SPECIFICATION/contracts.md`, §"Shared check inventory", the **Canonical-check waivers** paragraph.** Replace the sentence

> `check-aggregate-completeness` and the fleet-conformance row `canonical-check-slugs-wired` MUST read this one key; neither may read a waiver from any other surface.

with

> `check-aggregate-completeness`, the fleet-conformance row `canonical-check-slugs-wired`, and the bump-pin canonical-wiring reconcile (§"`reusable-bump-pin-from-dispatch.yml`") MUST read this one key; none of them MAY read a waiver from any other surface.

**3. `SPECIFICATION/scenarios.md`.** Add this scenario immediately after `## Scenario: a canonical check waived in pyproject.toml is exempt from the aggregate and fleet gates`:

```gherkin
## Scenario: a livespec-dev-tooling bump leaves a waived canonical slug unwired and still wires an unwaived missing one

Given a consumer whose pyproject.toml declares canonical_check_waivers under [tool.livespec_dev_tooling] with slug `check-heading-coverage` and a non-empty reason
And whose master `just check` aggregate and .github/workflows/ci.yml both omit `check-heading-coverage`, and whose master passes `check-aggregate-completeness`
And a livespec-dev-tooling release whose canonical check set contains `check-heading-coverage` and a slug `check-new-canonical` that the consumer's aggregate and ci.yml also omit
When the bump-pin workflow builds that consumer's bump commit for the release
Then the reconciled `just check` aggregate MUST NOT select `check-heading-coverage`, and the justfile MUST NOT gain a `check-heading-coverage:` recipe
And the reconciled ci.yml MUST NOT carry a `just check-heading-coverage` run line or a `check-heading-coverage` matrix target
And `check-new-canonical` MUST be inserted in alphabetical position into the reconciled aggregate and into the reconciled ci.yml
And `check-aggregate-completeness` on the reconciled tree MUST report no stale canonical-check waiver
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` row for the new scenario heading, and register any `"test": "TODO"` row in the debt register, in the revise commit (repository CLAUDE.md §"Revise co-edit discipline"); that file is outside the spec target, so it is not listed above.
