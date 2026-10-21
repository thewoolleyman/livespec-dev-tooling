---
topic: fleet-manifest-adopter-profiles
author: claude-opus-5-5 (petri-factory-on-gmktec)
created_at: 2026-10-21T11:31:37Z
---

## Proposal: Fleet manifest adopter profiles, including instruction-only

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a non-functional-requirements.md section, '## Fleet manifest adopter profiles', stating the reader contract that livespec-dev-tooling's manifest parser and fleet-conformance sweep implement for the `adopters` array of `.livespec-fleet-manifest.jsonc`. The contract accepts the adopter-only `instruction-only` profile that livespec core ratified in its v227, and it adds one scenario that pins the parse and sweep behaviour.

### Motivation

livespec core v227 (livespec SPECIFICATION/non-functional-requirements.md, "Profiles and the declarative manifest"; scenarios 'A released adopter is registered only after its wiring satisfies the sweep' and 'An instruction-only adopter is held to plugin currency and to no other baseline concern') ratified the `instruction-only` profile for toolchain-less repositories. livespec-dev-tooling owns the only reader of that manifest field. Its `_parse_adopter` (livespec_dev_tooling/fleet/contract.py) accepts only the layers baseline, fleet-infra, orchestrator-plugin and app, so a manifest declaring `instruction-only` fails the whole parse as `malformed-adopter`. That makes registering the seven toolchain-less host and deploy repositories (livespec-zyh7uo) a fleet-wide red: coordinator ruling R409 measured exactly that red when a registration landed before its reader accepted it. The reader must change first. livespec-dev-tooling's specification has no section governing the manifest's adopter entries, so the implementing work-item has no heading its Definition-of-Done References line can name. Coordinator rulings R320 and R449 route that gap through a ratified heading in the implementing repository.

### Proposed Changes

Append to SPECIFICATION/non-functional-requirements.md a new section:

## Fleet manifest adopter profiles

livespec-dev-tooling's manifest parser and its fleet-conformance sweep are the reader of the `adopters` array of livespec core's `.livespec-fleet-manifest.jsonc`, whose meaning livespec core's specification owns (its non-functional-requirements.md, "Profiles and the declarative manifest"). This section states only what that reader accepts and evaluates.

- An adopter entry's `profile` MUST be either a non-empty list whose every element is one of the layers `baseline`, `fleet-infra`, `orchestrator-plugin` and `app`, or exactly the one-element list `["instruction-only"]`. `instruction-only` replaces the `baseline` floor and MUST NOT be combined with any layer.
- An adopter entry's `posture` MUST be one of `released`, `pinned` and `none`.
- The parser MUST reject the whole manifest with the `malformed-adopter` reason when any adopter entry violates either rule above. That includes a profile list naming `instruction-only` beside another value.
- The sweep MUST hold a `released` adopter whose profile is `["instruction-only"]` to the adopter plugin-currency row and to no other row. A committed `.claude/settings.json` declaring `livespecPluginCurrencySuccessor` with a non-empty `mechanism` and `documentedIn` satisfies that row.
- The sweep MUST report an adopter whose `posture` is not `released` as posture-excluded and MUST NOT fail on it.
- The member parser MUST read a `fleet` member entry by its `repo` and `class` alone and MUST NOT read a profile from it, so a `profile` written on a `fleet` member entry has no effect.

Append to SPECIFICATION/scenarios.md:

## Scenario: the manifest reader accepts an instruction-only adopter and holds it to plugin currency only

Given a `.livespec-fleet-manifest.jsonc` whose `adopters` array holds an entry with `profile` `["instruction-only"]` and `posture` `released`, and another with `profile` `["instruction-only"]` and `posture` `none`

And the released adopter's repository carries no justfile, mise configuration or `.livespec.jsonc`, and its committed `.claude/settings.json` declares `livespecPluginCurrencySuccessor` with a non-empty `mechanism` and `documentedIn`

When the manifest is parsed and the fleet-conformance sweep evaluates its adopters

Then the parse MUST succeed, and the released adopter's adopter plugin-currency row MUST pass with no other row evaluated for it

And the adopter with posture `none` MUST be reported posture-excluded without failing the sweep

Given an adopter entry whose `profile` is <invalid>

When the manifest is parsed

Then the parse MUST fail with the `malformed-adopter` reason

Examples of <invalid>: `["instruction-only", "baseline"]`; `["instruction-only", "orchestrator-plugin"]`; `["instructions-only"]`; the empty list

In the same pass, `tests/heading-coverage.json` MUST gain one `TODO` row for each of the two new headings, owned by work-item livespec-dev-tooling-4ldzr5, and the scenario row's reason MUST acknowledge the integration tier or above. `tests/heading-coverage-debt.json` MUST be regenerated with `just generate-heading-coverage-debt-register`, and both files are included in the revise payload's `resulting_files[]`.
