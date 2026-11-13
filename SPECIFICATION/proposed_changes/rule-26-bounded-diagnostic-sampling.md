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

The full orchestrator run measured 4.784 mutants/hour across 12 workers and was stopped on coordinator ruling with its PVC preserved; whole-tree completion extrapolated to roughly two years. The bounded experiment and its measured estimates are recorded in plan/fleet-mutation-testing-rule-26/research/003-bounded-diagnostic-experiment-2026-11-13.md; its settings are plan inputs, not contract constants.

### Proposed Changes

Amend contracts.md under the existing "Rule-26 mutation kill matrix" heading. Preserve the default exhaustive recipe and every existing full-report/pruning requirement. Add an explicitly requested DIAGNOSTIC mode, never selected implicitly by time, worker count, cache contents or errors.

Co-edit the existing attribution and report-format bullets to make their mode scope explicit. In "Mutants and attribution", the "For every generated mutant" obligation and the unmeasured-test obligation against "every generated mutant" MUST apply to exhaustive mode; in diagnostic mode those same attribution rules MUST apply to every selected mutant. Baseline failures remain excluded from attribution in both modes. In "Report format", the generated/applied/unapplied counts with "generated equals applied plus unapplied", the per-mutant entries over the entire catalogue, and the REDUNDANCY-CANDIDATE and unapplied-coverage lists MUST be exhaustive-mode requirements only; the diagnostic fields and prohibition on pruning candidates below replace those exhaustive-report requirements for diagnostic mode. The zero-generated and zero-applied nonzero-exit rules MUST continue to apply in both modes: a diagnostic with zero selected mutants applied MUST exit nonzero, even if every selection has a final unapplied verdict. Preserve all other shared baseline, attribution, provenance and advisory-only requirements.

The engine MAY accept --mutant-manifest PATH to select a frozen nonempty subset for diagnosis. The manifest MUST name schema rule-26-diagnostic-manifest/1, the exact target source revision, the executing engine source digest, the catalogue digest, a seed, a selection method and unique mutant identifiers with an area and source-module mapping, plus budget.max_mutants, budget.max_workers and budget.max_elapsed_seconds as positive integers. Omission of the manifest MUST retain exhaustive mode; an omitted or malformed budget in diagnostic mode MUST be refused. A diagnostic MUST refuse duplicate or unknown identifiers, a mismatched revision/digest, an empty set, or more identifiers than its explicit budget before mutant execution. Selection MUST be independent of kill outcomes and runtime: the declared method chooses, for each declared high-risk area, the lowest SHA-256 of UTF-8 seed + identifier within the frozen source-module mapping, with deterministic identifier tie-breaking. The engine MUST reject an unsupported method or an ambiguous mapping, MUST recompute the selection from the seed, declared method, mapping and frozen catalogue, and MUST refuse a manifest whose selected identifiers differ from that recomputed set before mutant execution. The contract enforces the scope and budgets declared by the manifest; experiment-specific settings belong in plan research. An unapplied selection stays reported unapplied and MUST NOT be silently replaced.

All collected tests MUST still receive their unmutated baseline verdict; selected-mutant attribution MUST preserve the existing conservative coverage rules, including execution of unmeasured tests against every selected mutant. Diagnostic sampling MUST NOT delete, skip or rewrite tests. A selected mutant's lack of killers MUST describe only that selected mutant. Every catalogue identifier outside the manifest selection MUST be explicitly excluded/unexecuted and MUST NOT be classified as surviving, killed or unapplied. Diagnostic output MUST carry scope=partial-diagnostic, complete=false (the full-catalogue claim), sample_complete as a boolean, catalogue/selected/executed counts, selected and excluded identifiers, source revision, actual source-engine digest, manifest digest, seed/method/module mapping, baseline failures, selected mutant outcomes and any execution failures. It MUST write to a documented path distinct from the exhaustive report's. It MUST NOT publish a pruning-eligible redundancy_candidates list or overwrite a full report. A diagnostic MUST exit zero only after every selected mutant has a final applied or unapplied verdict, at least one selected mutant was applied, and sample_complete is true. An interrupted or budget-expired diagnostic MUST retain completed checkpoints and have a non-success terminal disposition; any report it writes MUST set sample_complete=false, or no diagnostic report is written if a hard kill prevents finalization. Neither an absent report nor an older report constitutes a completed sample for the interrupted invocation.

Both mutant-outcome and baseline-measurement cache identity MUST include a digest of the executing engine's source bytes independently of installed distribution metadata; identical source relocated on disk MUST retain that identity. An unreadable or incomplete source identity MUST fail closed. Cache reuse MUST bind target/source, interpreter/dependencies, timeout, selected tests and this source-engine identity under the existing input-dependency rules. Diagnostic runs MUST use their own cache/measurement namespace; old caches whose source-engine provenance is unestablished MUST remain evidence only and MUST NOT seed the diagnostic. Reports MUST distinguish source-engine identity from the mutation tool's version.

The committed cluster launch surface MUST accept a diagnostic manifest, enforce its declared mutant, worker and elapsed-time budgets, and keep the PVC on a job-only stop. budget.max_elapsed_seconds MUST bound the complete invocation from before its first setup action, including setup, catalogue generation, baseline measurement and mutant execution. The Job deadline MUST expire no later than that same absolute end time; when Job creation follows invocation start, its deadline MUST use only the remaining budget. The engine MUST also receive only the remaining budget after setup, rather than starting a second full elapsed budget. Expiry or a job-only stop MUST terminate execution without automatic continuation or full-tree fallback, preserve the PVC and completed checkpoints, and retain the incomplete disposition even if a hard Job-deadline kill prevents writing a diagnostic report. No execution is part of this specification change.

Add scenarios.md scenarios co-edited with the clause (and the heading registry/debt entries owed by the chosen proof tier):

## Scenario: an explicit diagnostic manifest produces a partial matrix without pruning evidence

Given a frozen catalogue of mutants M1, M2, M3 and a matching diagnostic manifest selecting M1 and M3

And a baseline containing an unmeasured test and a baseline-failing test

When diagnostic execution completes

Then only M1 and M3 MUST execute under the existing conservative attribution rules

And the unmeasured test MUST run against both M1 and M3

And the baseline-failing test MUST be excluded from mutant attribution and listed only under baseline failures

And M2 MUST be explicitly unexecuted and absent from the surviving, killed and unapplied lists

And the separate diagnostic report MUST be marked complete=false and carry the manifest/source/engine provenance

And it MUST contain no pruning-eligible redundancy-candidate list or changes to the exhaustive report.

## Scenario: a diagnostic refuses a stale or invalid mutant manifest before execution

Given a diagnostic manifest with an unknown or duplicate identifier, an empty selection, a selection exceeding budget, a mismatched source, engine or catalogue digest, an unsupported method, an ambiguous mapping, or selected identifiers differing from the engine-recomputed selection

When the diagnostic is invoked

Then the engine MUST recompute the selection from seed, method, mapping and catalogue when those inputs are valid

And it MUST exit nonzero with a finding naming the invalid input or recomputed-selection mismatch before any mutant executes

And it MUST NOT emit a success report or silently widen the selection.

## Scenario: engine source changes invalidate mutation evidence despite unchanged installed metadata

Given a stored mutant outcome and baseline measurement

And the executing engine source changes while installed distribution metadata, Python and mutation-tool versions remain unchanged

When a later run considers reuse

Then it MUST reject both old identities and measure/retest under the new engine source

And identical source copied to another installation path MUST retain its source identity.

## Scenario: a diagnostic exhausts its cluster budget and retains only partial evidence

Given a diagnostic Job with manifest-declared worker and elapsed-time budgets, a deadline accounting for setup from the same invocation start, and saved checkpoint evidence on its PVC

When its budget expires, including a hard Job-deadline kill, or the operator invokes the committed job-only stop surface

Then the Job MUST cease execution and retain its PVC evidence

And any report it can finalize MUST mark sample_complete=false, or no diagnostic report is written if the hard kill prevents finalization

And its terminal disposition MUST be non-success and remain incomplete, without automatic continuation, a full-matrix verdict or pruning authorization.

Implementation must land only after this amendment is ratified. The cache source-identity repair is independently a conformance fix under the existing Incremental runs clause; this proposal makes its provenance observable but does not delay that repair. Plan A1/A3/A4 full evidence, A7 pruning and A8 improvement claims remain unmet by a diagnostic. Do not revise the maintainer's plan DoD or declare a full report through a smaller denominator.


### Owed at revise

Co-edit SPECIFICATION/contracts.md and SPECIFICATION/scenarios.md atomically with tests/heading-coverage.json. The four new scenario headings above require these registry entries at revise (copy each heading verbatim):

| Scenario heading | Registry entry owed at revise |
| --- | --- |
| Scenario: an explicit diagnostic manifest produces a partial matrix without pruning evidence | `test: "TODO"`; `work_item: "livespec-dev-tooling-rl6tqt"`; reason: "A real test at the integration tier or above is owed for diagnostic partial-matrix attribution and report isolation; livespec-dev-tooling-rl6tqt owns it." |
| Scenario: a diagnostic refuses a stale or invalid mutant manifest before execution | `test: "TODO"`; `work_item: "livespec-dev-tooling-rl6tqt"`; reason: "A real test at the integration tier or above is owed for manifest validation and engine-recomputed selection refusal; livespec-dev-tooling-rl6tqt owns it." |
| Scenario: engine source changes invalidate mutation evidence despite unchanged installed metadata | Use the real test path `tests/livespec_dev_tooling/test_mutation_kill_matrix_engine_identity.py`, delivered by livespec-dev-tooling-he7huy in merged livespec-dev-tooling#4486 (master b02208847); this row needs no TODO debt. |
| Scenario: a diagnostic exhausts its cluster budget and retains only partial evidence | `test: "TODO"`; `work_item: "livespec-dev-tooling-dya4ta"`; reason: "A real test at the integration tier or above is owed for elapsed-budget enforcement and durable stop evidence, including hard-kill report absence; livespec-dev-tooling-dya4ta owns it." |

Run `just generate-heading-coverage-debt-register` after editing the registry and stage tests/heading-coverage-debt.json in the same revise commit; never hand-edit the generated register. These are owed co-edits, not live scenario rows in this proposal-only PR. The two implementation owners use manual admission and must have their scenario References updated after ratification and before approval. Filing them authorizes neither implementation nor execution.
