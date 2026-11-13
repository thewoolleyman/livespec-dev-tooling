---
topic: rule-26-bounded-diagnostic-sampling
author: codex
created_at: 2026-11-13T06:15:39Z
---

## Proposal: Explicit partial diagnostic sampling preserves full-matrix and pruning requirements

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a separate, manifest-selected, explicitly partial diagnostic mode and bounded cluster execution, with immutable engine-source cache provenance; retain exhaustive defaults and prohibit sample-based pruning claims.

### Motivation

The full orchestrator run measured 4.784 mutants/hour across 12 workers and was stopped on coordinator ruling with its PVC preserved; whole-tree completion extrapolated to roughly two years. The adopted six-mutant/two-worker experiment estimates 12.3 hours, or 19.8 hours with doubled execution time, under a 22-hour cap.

### Proposed Changes

Amend contracts.md under the existing "Rule-26 mutation kill matrix" heading. Preserve the default exhaustive recipe and every existing full-report/pruning requirement. Add an explicitly requested DIAGNOSTIC mode, never selected implicitly by time, worker count, cache contents or errors.

The engine MAY accept --mutant-manifest PATH to select a frozen nonempty subset for diagnosis. The manifest MUST name schema rule-26-diagnostic-manifest/1, the exact target source revision, the executing engine source digest, the catalogue digest, a seed, a selection method and unique mutant identifiers with an area and source-module mapping, plus budget.max_mutants and budget.max_elapsed_seconds as positive integers. Omission of the manifest MUST retain exhaustive mode; an omitted or malformed budget in diagnostic mode MUST be refused. A diagnostic MUST refuse duplicate or unknown identifiers, a mismatched revision/digest, an empty set, or more identifiers than its explicit budget before mutant execution. Selection MUST be independent of kill outcomes and runtime: for each declared high-risk area, choose the lowest SHA-256 of UTF-8 seed + identifier within the frozen module mapping, with deterministic identifier tie-breaking, and reject an ambiguous mapping. For the first plan experiment the manifest names six distinct modules, one mutant in each of dispatch authorization, claim-token ownership, lifecycle transitions, acceptance/reconciliation, plan result/budget advancement and proof identity/verification, using seed rule26-day-probe-v1:b26c3dc2. Other callers MAY supply a different explicitly frozen scope; six is this plan's execution budget, not an engine-wide limit. An unapplied selection stays reported unapplied and MUST NOT be silently replaced.

All collected tests MUST still receive their unmutated baseline verdict; selected-mutant attribution MUST preserve the existing conservative coverage rules, including execution of unmeasured tests against every selected mutant. Diagnostic sampling MUST NOT delete, skip or rewrite tests. A selected mutant's lack of killers MUST describe only that selected mutant. Every unexecuted catalogue identifier MUST be explicitly excluded/unexecuted and MUST NOT be classified as surviving, killed or unapplied. Diagnostic output MUST carry scope=partial-diagnostic, complete=false (the full-catalogue claim), sample_complete as a boolean, catalogue/selected/executed counts, selected and excluded identifiers, source revision, actual source-engine digest, manifest digest, seed/method/module mapping, baseline failures, selected mutant outcomes and any execution failures. It MUST write to reports/mutation-kill-matrix-diagnostic.json, separate from the exhaustive reports/mutation-kill-matrix.json. It MUST NOT publish a pruning-eligible redundancy_candidates list or overwrite a full report. A diagnostic MUST exit zero only after every selected mutant has a final applied or unapplied verdict and sample_complete is true. An interrupted or budget-expired diagnostic MUST set sample_complete=false and exit nonzero and retain checkpoints without claiming a completed sample.

Both mutant-outcome and baseline-measurement cache identity MUST include a digest of the executing engine's source bytes independently of installed distribution metadata; identical source relocated on disk MUST retain that identity. An unreadable or incomplete source identity MUST fail closed. Cache reuse MUST bind target/source, interpreter/dependencies, timeout, selected tests and this source-engine identity under the existing input-dependency rules. Diagnostic runs MUST use their own cache/measurement namespace; old caches whose source-engine provenance is unestablished MUST remain evidence only and MUST NOT seed the diagnostic. Reports MUST distinguish source-engine identity from the mutation tool's version.

The committed cluster launch surface MUST accept a diagnostic manifest and an absolute elapsed-time budget, account for its workers and keep the PVC on a job-only stop. For the plan's first experiment it MUST request/limit two workers and enforce a 22-hour Job deadline including setup, with no automatic continuation or full-tree fallback. Its supervisor MUST project the remaining runtime after the first pair completes and stop through the committed job-absent route when that projection exceeds the remaining budget. A completion estimate is advisory, not permission to exceed the absolute cap. No execution is part of this specification change.

Add scenarios.md scenarios co-edited with the clause (and the heading registry/debt entries owed by the chosen proof tier):

## Scenario: an explicit diagnostic manifest produces a partial matrix without pruning evidence

Given a frozen catalogue of mutants M1, M2, M3 and a matching diagnostic manifest selecting M1 and M3

And a baseline containing an unmeasured test and a baseline-failing test

When diagnostic execution completes

Then only M1 and M3 MUST execute under the existing conservative attribution rules

And M2 MUST be explicitly unexecuted and absent from the survivor/killed lists

And the separate diagnostic report MUST be marked complete=false and carry the manifest/source/engine provenance

And it MUST contain no pruning-eligible redundancy-candidate list or changes to the exhaustive report.

## Scenario: a diagnostic refuses a stale or invalid mutant manifest before execution

Given a diagnostic manifest with an unknown or duplicate identifier, an empty selection, a selection exceeding budget, or a mismatched source, engine or catalogue digest

When the diagnostic is invoked

Then it MUST exit nonzero with a finding naming the invalid input before any mutant executes

And it MUST NOT emit a success report or silently widen the selection.

## Scenario: engine source changes invalidate mutation evidence despite unchanged installed metadata

Given a stored mutant outcome and baseline measurement

And the executing engine source changes while installed distribution metadata, Python and mutation-tool versions remain unchanged

When a later run considers reuse

Then it MUST reject both old identities and measure/retest under the new engine source

And identical source copied to another installation path MUST retain its source identity.

## Scenario: a diagnostic exhausts its cluster budget and retains only partial evidence

Given a two-worker diagnostic Job with a 22-hour deadline and saved checkpoint evidence on its PVC

When its budget expires or its supervisor rules a job-only stop

Then the Job MUST cease execution and retain its PVC evidence

And its result MUST remain incomplete, without automatic continuation, a full-matrix verdict or pruning authorization.

Implementation must land only after this amendment is ratified. The cache source-identity repair is independently a conformance fix under the existing Incremental runs clause; this proposal makes its provenance observable but does not delay that repair. Plan A1/A3/A4 full evidence, A7 pruning and A8 improvement claims remain unmet by a diagnostic. Do not revise the maintainer's plan DoD or declare a full report through a smaller denominator.
