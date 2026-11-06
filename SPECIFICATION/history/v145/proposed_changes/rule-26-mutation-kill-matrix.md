---
topic: rule-26-mutation-kill-matrix
author: claude-opus-5-5
created_at: 2026-11-06T06:22:39Z
---

## Proposal: Rule-26 mutation kill matrix: shared engine, report format and on-demand recipe

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a contract section `## Rule-26 mutation kill matrix` to contracts.md, plus two scenarios to scenarios.md. Together they govern a shared engine that runs every test against every generated mutant of a repository's first-party code and records per-test kill attribution. They define the report format: the killing tests per mutant, the surviving mutants and the redundancy-candidate tests. They require an on-demand `just mutation-kill-matrix` recipe in each adopting repository, and a guard that keeps the recipe out of the `just check` aggregate. Today the spec governs only `check_mutation`, a kill-RATE ratchet, so no ratified clause covers the per-test matrix that rule 26 prescribes.

### Motivation

Plan fleet-mutation-testing-rule-26 (epic livespec-dev-tooling-oi2two) adopts impatientprogramming.org rule 26, 'Every test must prove it's worth keeping': keep a test only if it catches something no other test catches. The 2026-10-28 survey (plan/fleet-mutation-testing-rule-26/research/001-rule-26-survey-and-baseline-2026-10-28.md) found no repository producing a per-test kill matrix. The one shared mutation check reports a kill rate only, and nine repositories' instances are no-ops. The consuming work item livespec-dev-tooling-wou75w was held at pending-approval with definition-of-done-held because no ratified heading governs this engine, so the behaviour has to be specified before the factory may build it. The recipe is deliberately not a `check-*` slug: the canonical-slug enforcement would pull such a slug into the `just check` aggregate, and the maintainer requires the kill matrix to run on demand only.

### Proposed Changes

Add the following section to `SPECIFICATION/contracts.md`, immediately after §"Delegated gate-runner runs":

## Rule-26 mutation kill matrix

livespec-dev-tooling ships a shared rule-26 mutation kill-matrix engine and report format that every fleet repository adopts through a thin per-repository recipe. Rule 26 (impatientprogramming.org/rules/#rule-26) keeps a test only if it catches something no other test catches. This contract governs the artefact that makes that judgement visible. It is distinct from `check_mutation`, which reports a kill rate and is unchanged by this section.

- **Mutants and attribution.** The engine MUST generate mutants of the adopting repository's first-party code and MUST run every test of that repository's suite against every generated mutant. It MUST record, for each mutant, the identity of every test that killed it. A run that generates zero mutants MUST exit non-zero with a finding naming the empty mutant set, and MUST NOT write a report that reads as a clean result. On the Python path the engine MUST use the fleet-pinned mutmut. Other ecosystems MAY use a language-appropriate engine, such as cargo-mutants for Rust, provided they produce the report format below.
- **Report format.** The report MUST be one machine-readable document at a path the adopting repository documents. It MUST carry: the engine and its version; the source revision mutated; the count of mutants generated; for every mutant, its identifier, its location and the list of tests that killed it; the list of SURVIVING mutants, those that no test killed; and the list of REDUNDANCY-CANDIDATE tests. A redundancy-candidate test is one that killed at least one mutant and all of whose kills were also made by at least one other test. A test that killed no mutant MUST also be listed as a redundancy candidate. The report format MUST NOT depend on any one engine's internal data layout, so that every engine's adapter emits the same document.
- **Recipe.** Each adopting repository MUST expose a `just mutation-kill-matrix` recipe that runs the engine over that repository's first-party code and writes the report to its documented path. The recipe MUST be on demand only: it MUST NOT be a member of the `just check` aggregate, MUST NOT run from any commit-time or push-time hook, and MUST NOT be a required per-PR CI job.
- **Keep-out guard.** livespec-dev-tooling MUST ship a guard check that fails with a named finding when `mutation-kill-matrix` is reachable from the `just check` aggregate. Adopting repositories SHOULD run that guard as part of their aggregate.
- **Advisory only.** The report is evidence for a human or agent deciding which tests to remove. Neither the engine nor the recipe MUST delete, skip or rewrite any test.

Add the following two scenarios to the end of `SPECIFICATION/scenarios.md`:

## Scenario: a rule-26 kill-matrix run reports survivors and redundancy candidates

Given a Python package whose suite has three tests, where tests A and B both kill mutant M1, only test A kills mutant M2, and no test kills mutant M3

When `just mutation-kill-matrix` runs over that package

Then the report MUST list A and B as the killers of M1 and A as the only killer of M2

And the report MUST list M3 as a surviving mutant

And the report MUST list B as a redundancy candidate and MUST NOT list A as one

## Scenario: wiring the kill-matrix recipe into the check aggregate is refused

Given a repository whose `just check` aggregate does not reach `mutation-kill-matrix`

When a change adds `mutation-kill-matrix` to the `just check` aggregate

Then the keep-out guard check MUST fail with a finding naming `mutation-kill-matrix` and the `just check` aggregate
