---
topic: retire-pre-1-0-stance-and-transitional-accepting-loader
author: claude-opus-5
created_at: 2026-07-28T22:15:04Z
---

## Proposal: Retire the pre-1.0 semver stance now that v1.0.0 is released and consumed

### Target specification files

- SPECIFICATION/contracts.md

### Summary

SPECIFICATION/contracts.md §"Default layout fallback" records this library as pre-1.0, "where the MAJOR component is pinned at `0` and breaking changes necessarily land in lower components". That is now factually false: v1.0.0 is tagged, contains the Phase 4 commit `b36e0b8`, and every one of the eight fleet siblings both declares `tag = "v1.0.0"` and resolves `livespec-dev-tooling==1.0.0` in its lockfile. The clause MUST be rewritten to state the post-1.0 regime that actually applies, while PRESERVING the historical record of the v0.54.12 deviation it exists to document.

### Motivation

Filed as livespec-dev-tooling-5ror. The pre-1.0 sentence was accurate when written and was falsified by events — the same amendment-left-a-standing-statement shape this thread has now found nine times. It matters more than ordinary prose staleness because it is NORMATIVE: it tells a future editor that a breaking change may land in a lower component, which under a released 1.0.0 is an instruction to ship an unsignalled incompatibility. The clause is also load-bearing in the other direction: it exists to record, rather than smooth over, that a MAJOR-class change shipped in the PATCH release v0.54.12. That record MUST survive the rewrite; only its justification changes from "pre-1.0 permits it" to "it was a deviation under the regime then in force".

### Proposed Changes

In §"Default layout fallback", the sentence explaining why a MAJOR-class change could ship in a PATCH release MUST be rewritten. The spec MUST NOT continue to assert that the library is pre-1.0 or that the MAJOR component is pinned at `0`.

The replacement MUST state all of the following:

- The v0.54.12 retirement WAS a MAJOR-class change by §"Semver discipline"'s own definition, and it shipped in a PATCH release. This record MUST be preserved verbatim in substance — it is the point of the paragraph.
- That deviation occurred under the PRE-1.0 regime then in force, in which the MAJOR component was pinned at `0`. The statement MUST be scoped to that period (past tense, naming v0.54.12) rather than describing the library's current state.
- The library is now POST-1.0: `v1.0.0` is released and consumed by every fleet consumer. From `v1.0.0` onward a MAJOR-class change — one that incompatibly reinterprets recognized `[tool.livespec_dev_tooling]` keys, removes a recognized key, or changes a documented exit code — MUST land via a MAJOR version bump, and MUST NOT be shipped in a MINOR or PATCH release.
- The mitigating sequencing SHOULD remain recorded (every consumer's declaration backfill landed BEFORE the enforcing release, so no repo reddened on the flip), because it is what makes the deviation defensible rather than merely disclosed.
- The closing observation MUST be retained: a spec that indicts a smaller undocumented change in the same release while passing over this one in silence would be applying its own discipline selectively.

The editor MUST NOT weaken §"Semver discipline" itself to accommodate the historical deviation, and MUST NOT delete the deviation record in the course of correcting its justification.

## Proposal: Retire the transitional accepting-loader regime that Phase 4 ended

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Revision v033 ratified a TRANSITIONAL regime in which a bare `[]` / `""` on a union role key is accepted, parsed to a legacy variant, and logged at WARN. Phase 4 (`b36e0b8`, released as `v1.0.0`) ended that regime hours later: `LegacyAmbiguousEmpty` was deleted and the spelling is now a hard `ConfigParseError` at load. The contracts.md clause and its scenarios.md acceptance scenario MUST be rewritten to describe the rejecting loader, and the scenario MUST be REWRITTEN rather than deleted, because the behavior it governs still exists and only its outcome changed.

### Motivation

Filed as livespec-dev-tooling-clkf. Ratifying the transitional clause was CORRECT — it is precisely what authorized Phase 4, and the harden-first ordering it encodes is what made the flip safe. The defect is therefore the standing DESCRIPTION, not the decision, and the amendment MUST NOT read as a repudiation of v033. Leaving it stands the spec in active contradiction of the shipped loader: the spec says the loader MUST accept and warn; the loader rejects. A future implementer building to the ratified text would rebuild the regime Phase 4 removed. Note one out-of-target consequence, surfaced here rather than emitted as a malformed target path: `tests/heading-coverage.json` links the affected scenario to `tests.livespec_dev_tooling.checks.test_role_key_variants.test_legacy_empty_target_dirs_is_announced_at_warn`, a test Phase 4 DELETED. Its live replacement is `test_legacy_empty_target_dirs_is_now_rejected_at_load` in the same module. That registry is outside the spec target and MUST be corrected as implementation work accompanying the ratified revision, not by this proposal.

### Proposed Changes

**contracts.md.** The paragraph beginning "A bare `[]` / `\"\"` on a UNION key is TRANSITIONAL" MUST be replaced. The spec MUST NOT continue to state that the loader accepts the spelling, parses it to a legacy variant, or logs at WARN.

The replacement MUST state:

- A bare `[]` / `""` on a key in `UNION_ROLE_KEYS` MUST be REJECTED at load as a hard `ConfigParseError`, and the diagnostic MUST name the offending key and every legal spelling.
- The transitional accept-and-WARN regime is RETIRED, having served its purpose: it existed so consumers could migrate before the rejecting loader landed.
- The harden-first ordering constraint MUST be retained as a standing rule for FUTURE required-key schema changes — a rejecting loader MUST NOT land before every consumer has migrated. This clause MUST NOT be deleted along with the transitional regime it once governed; it is the general rule, and the transition was one application of it.
- The record SHOULD note that the ordering was honored in practice: every consumer had migrated to a blessed spelling before the rejecting loader shipped, so no consumer reddened on the flip.

The adjacent §"Clean role keys retain `[]`" MUST be left intact. A bare `[]` remains a LEGITIMATE declared value for `source_trees`, `io_trees`, `commands_trees`, `supervisor_entry_files` and `covered_trees`, because emptiness there removes exemptions rather than files and so makes the consuming check stricter rather than blinder. The editor MUST NOT generalize this amendment into a blanket retirement of `[]`.

**scenarios.md.** The scenario `## Scenario: the legacy empty spelling on a union key warns and does not silently pass` MUST be REWRITTEN, not deleted — the behavior it governs (a consumer declaring a union role key as a bare `[]` or `""`) still exists and is still load-bearing; only its outcome changed from a WARN to a hard failure. No other scenario covers it: the neighbouring `## Scenario: a declared-absent variant with an empty payload is rejected at load` governs a BLESSED VARIANT NAME carrying an empty payload, which is a different input.

The rewritten scenario MUST take the shape:

```
## Scenario: the legacy empty spelling on a union key is rejected at load

Given a consumer declares a union role key as a bare `[]` or `""`

When the loader reads that block

Then loading MUST fail with a `ConfigParseError` naming the key

And the diagnostic MUST name every legal spelling for that key

And the emptiness MUST NOT be reported as a sanctioned opt-out
```

The final `And` MUST be retained from the superseded scenario: it is the invariant the union exists to enforce, and it survives the change from WARN to rejection.
