---
topic: absorb-compat-schema-and-semver-discipline
author: claude-fable-5
created_at: 2026-06-10T20:48:07Z
---

This propose-change absorbs two obligations the livespec core spec delegated to this repository.

At livespec v103 the contract + reference implementations re-steering's normative decision record (item 3, DECIDED) relocated pin-and-bump out of core: "the `compat` block schema and bump-pin policy move to the family/dev-tooling coordination surface (`livespec-dev-tooling`'s spec, which already owns the automation); the `contract-version-compatibility` doctor invariant is DROPPED from core's catalogue". At v104 the cleanup pass restated `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump" in pointer form: the schema, the bump-pin policy, and any compatibility enforcement "are owned by `livespec-dev-tooling`'s own spec … the relocation lands via that sibling's own propose-change cycle" (Proposal 1 below is that cycle). Independently, livespec contracts.md §"Shared code sync — livespec-dev-tooling" mandates that "The canonical surface enumeration … MUST live in `livespec-dev-tooling`'s own `contracts.md` §\"Semver discipline\"" — a section this repo's `contracts.md` does not have (the enumeration currently lives in `constraints.md` §"Semver discipline"; Proposal 2 relocates it to the mandated home). Both proposals descend from the livespec-tenant epic livespec-4moata.

## Proposal: Absorb the consumer compat-block schema and pin-and-bump policy

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add a new H2 section `## Consumer compat block — pin-and-bump policy` to `contracts.md`, immediately before §"Cross-repo coordination automation surface", carrying the per-consumer `compat` block schema and the consumer-facing bump-pin policy that livespec core relocated here at v103/v104. Adjust the §"Cross-repo coordination automation surface" preamble so it docks onto the new policy section instead of attributing the policy to livespec's spec.

### Motivation

livespec v103 decision-record item 3 relocated the `compat` block schema and bump-pin policy to this repository's spec, and v104 reduced `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump" to a pointer AT this repository ("owned by `livespec-dev-tooling`'s own spec, whose `contracts.md` already owns the bump-pin automation per its §\"Cross-repo coordination automation surface\"; the relocation lands via that sibling's own propose-change cycle"). Until this repo's spec actually states the schema and policy, the family contract dangles: livespec points here, and here says (in the §"Cross-repo coordination automation surface" preamble) "livespec's spec declares the policy, this section owns the implementation surface" — a circular reference with no normative home. The pin-autodiscovery rules in §"Cross-repo coordination automation surface" already PARSE the `compat` block (`compat.pinned` / `livespec` fields) but nothing in this spec DEFINES it.

### Proposed Changes

1. Insert a new H2 section immediately before §"Cross-repo coordination automation surface":

```markdown
## Consumer compat block — pin-and-bump policy

This section owns the release-level coordination policy between `livespec` and every livespec-governed sibling consumer (`livespec-impl-*` plugins, this library, `livespec-runtime`, and any future sibling). It was relocated here from `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump" at livespec v103/v104; livespec's section is now a pointer at this one. §"Cross-repo coordination automation surface" below owns the automation that implements this policy.

### `compat` block schema

Every consumer MUST declare a top-level section in its `.livespec.jsonc` keyed by the consumer's own plugin / library name (e.g., `livespec-impl-beads`, `livespec-dev-tooling`, `livespec-runtime`), carrying a `compat` block with two REQUIRED fields:

- `livespec` — a semver range describing the supported `livespec` versions (e.g., `">=2.0.0,<3.0.0"`).
- `pinned` — the specific `livespec` release tag the consumer currently runs against (e.g., `"v2.3.0"`).

`.livespec.jsonc` MUST NOT carry secrets; the `compat` block contains only non-sensitive version metadata. This is the same block shape the pin-autodiscovery walk recognizes per §"Pin autodiscovery rules" (the `.livespec.jsonc` `compat.pinned` format).

### Bump-pin policy

- **Every consumer pins.** Each consumer's automation and autonomous workflows MUST run against the pinned `livespec` release, NEVER against HEAD. Running against HEAD bypasses the audited coordination mechanism and is an out-of-contract operation.
- **Releases fire bump-pin PRs.** When `livespec` ships a new release tag, a bump-pin pull request MUST be opened automatically in every consumer per §"Cross-repo coordination automation surface". The bump-pin PR's acceptance criterion is that the consumer continues to pass its post-bump invariant suite (`just check` per §"`reusable-bump-pin-from-dispatch.yml`").
- **Breaking changes land additively.** Breaking contract changes in `livespec` MUST be landed additively: the old contract surface stays valid for one or more releases; every consumer migrates at its own cadence; only after the active consumers' releases adopting the new surface ship MAY the old surface be removed in a subsequent `livespec` release (the `N` / `N-1` support-window pattern).

### Enforcement status

livespec core's doctor no longer enforces any of this: the `contract-version-compatibility` invariant was DROPPED from core's catalogue at livespec v103. Compatibility enforcement, if any, is this repository's choice — e.g., a shared check under `livespec_dev_tooling/checks/` that validates `compat` block presence/shape or pin freshness — and MAY be specified by a follow-on propose-change. This proposal deliberately does NOT decide whether or how to enforce.
```

2. In the §"Cross-repo coordination automation surface" preamble, replace the sentence fragment "This section codifies the reusable GitHub workflow surface that implements livespec's pin-and-bump mechanism (per `livespec/SPECIFICATION/contracts.md` §\"Cross-repo coordination — pin-and-bump\") uniformly across every livespec-governed sibling repository. The contract here is the canonical implementation specification; livespec's spec declares the policy, this section owns the implementation surface." with: "This section codifies the reusable GitHub workflow surface that implements the pin-and-bump policy declared in §\"Consumer compat block — pin-and-bump policy\" uniformly across every livespec-governed sibling repository. The contract here is the canonical implementation specification; the preceding section owns the policy (relocated from livespec core at v103/v104, whose `contracts.md` §\"Cross-repo coordination — pin-and-bump\" now points here)."

3. Heading-coverage co-edit: accepting this proposal adds one `## ` H2 to `contracts.md`, so the accepting revise pass MUST include a corresponding `TODO` + `reason` entry for `## Consumer compat block — pin-and-bump policy` in `tests/heading-coverage.json` via `resulting_files[]` (path `../tests/heading-coverage.json`). This propose-change file itself changes no spec H2 set.

## Proposal: Add contracts.md §"Semver discipline" (canonical surface enumeration)

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md

### Summary

Relocate the canonical semver-stable surface enumeration from `constraints.md` §"Semver discipline" into a new `contracts.md` §"Semver discipline" (placed immediately before §"Versioning"), extending it to cover the consumer-configuration key set; reduce `constraints.md` §"Semver discipline" to a pointer (heading retained); update the three in-file cross-references that currently cite `constraints.md` §"Semver discipline".

### Motivation

`livespec/SPECIFICATION/contracts.md` §"Shared code sync — livespec-dev-tooling" (v105) mandates: "The canonical surface enumeration (the specific list of covered elements, the MAJOR/MINOR/PATCH bump rules, and the Conventional Commits → semver mapping) MUST live in `livespec-dev-tooling`'s own `contracts.md` §\"Semver discipline\"". That section does not exist in this repo's `contracts.md` — the enumeration lives in `constraints.md` §"Semver discipline" instead, so the family cross-reference dangles (real drift, found 2026-06-09). `contracts.md` is also the natural home: its own preamble declares "Every contract here is semver-stable", and §"Sibling spec ownership" in livespec's contracts.md places implementation-contract enumeration in siblings' `contracts.md` files. (No sibling currently models a contracts.md §"Semver discipline"; `livespec-runtime` keeps its bump rules in `non-functional-requirements.md` §"Versioning" with a pointer from its contracts.md §"Versioning" — this proposal makes this repo the family's first instance of the mandated section, adapted from the existing `constraints.md` enumeration rather than from runtime's layout.)

### Proposed Changes

1. Add a new H2 section to `contracts.md`, immediately before §"Versioning":

```markdown
## Semver discipline

The library's semver-stable surface — the canonical enumeration required by `livespec/SPECIFICATION/contracts.md` §"Shared code sync — livespec-dev-tooling" — is:

- The `python -m livespec_dev_tooling.checks.<slug>` invocation set (each slug's argv contract and exit-code semantics per §"CLI surface" and §"Exit-code table").
- The composite Action paths and their declared inputs / outputs (per §"Composite Actions wire contract").
- The reusable workflow paths and their declared inputs / outputs / secrets / concurrency (per §"Reusable workflows wire contract").
- The `[tool.livespec_dev_tooling]` consumer-configuration key set (per §"Consumer configuration schema").
- The cross-repo coordination automation surface elements pinned by §"Cross-repo coordination automation surface" §"Semver coverage extension" — the `repository_dispatch` payload contract, the `livespec-sibling` GitHub topic name, and the pin autodiscovery rules' format coverage.

Bump rules:

- **MAJOR** — any change that REMOVES, RENAMES, or BREAKS-COMPATIBILITY-OF a surface element (including removing or incompatibly reinterpreting a recognized `[tool.livespec_dev_tooling]` key).
- **MINOR** — adding a new check, a new composite Action, a new reusable workflow, a new optional configuration key, or a new pin-autodiscovery format.
- **PATCH** — a pure implementation change that preserves every surface element.

The Conventional Commits → semver mapping (`feat:` MINOR, `fix:` PATCH, `feat!:` MAJOR, etc.) MUST be honored by every commit on `master` so that `release-please` derives the correct next version (see §"Versioning").
```

2. Replace the body of `constraints.md` §"Semver discipline" (heading retained, so the constraints.md H2 set is unchanged) with a pointer: "The canonical semver-stable surface enumeration, the MAJOR/MINOR/PATCH bump rules, and the Conventional Commits → semver mapping live in `contracts.md` §\"Semver discipline\", the location mandated by `livespec/SPECIFICATION/contracts.md` §\"Shared code sync — livespec-dev-tooling\". The constraint-level invariant is: NO breaking change to any enumerated surface element may land outside a MAJOR version bump."

3. Update the three cross-references in `contracts.md` that cite the old location:
   - Preamble (line "Every contract here is semver-stable: a breaking change MUST land via a MAJOR version bump per `constraints.md` §\"Semver discipline\".") → cite `§"Semver discipline"` (same file).
   - §"Shared check inventory" fallback-set sentence ("any change is a major-version bump per `constraints.md` §\"Semver discipline\"") → cite `§"Semver discipline"` (same file).
   - §"Cross-repo coordination automation surface" §"Semver coverage extension" ("The semver-stable surface declared in `constraints.md` §\"Semver discipline\" is hereby extended …") → "The semver-stable surface declared in §\"Semver discipline\" is hereby extended …". The extension subsection itself stays in place; the new §"Semver discipline" enumeration references it (final bullet), preserving the existing extension mechanism.

4. Heading-coverage co-edit: accepting this proposal adds one `## ` H2 to `contracts.md` (`## Semver discipline`); the accepting revise pass MUST include the corresponding `TODO` + `reason` entry in `tests/heading-coverage.json` via `resulting_files[]` (path `../tests/heading-coverage.json`). `constraints.md`'s H2 set is unchanged. This propose-change file itself changes no spec H2 set.
