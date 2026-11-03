---
topic: expedited-incident-response-contract
author: codex
created_at: 2026-11-03T17:23:14Z
---

## Proposal: Expedited incident execution and recovery realization

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Add explicit incident-only local/PR selection, honest focused evidence, independent first-failure inverse recovery and installed-fleet adoption, while preserving normal master/factory policy.

### Motivation

Maintainer made expedited-incident-response-flag fleet priority 1 and authorized implementation from the published charter and 37-surface audit; current unconditional gate and reconciler contracts conflict with the requested recovery path.

### Proposed Changes

Add `## Expedited incident execution` to contracts.md and link it from spec.md as an optional explicitly authorized incident capability. Add the corresponding scenarios below and atomic heading-coverage registry/debt co-edits when ratifying. Ordinary invocation MUST retain its complete existing behavior. This proposal changes dev-tooling realization only; core owns inherited policy and the orchestrator owns item lifecycle.

The execution resolver MUST produce a typed normal, expedited-repair or emergency-revert context before prechecks, autofix, source/test pairing, cache lookup, delegation, replay or fallback. It MUST bind incident item, attempt, phase, repository, base/head and immutable operation identity. EXPEDITED_INCIDENT_RESPONSE=1 selects repair; EXPEDITED_INCIDENT_RESPONSE_REVERT=1 takes precedence and MUST resolve a recorded incident merge. Document one shared truth-value parser; malformed ordinary incident values MUST produce a named configuration refusal. Trusted normal-master and normal-factory contexts MUST force both flags absent BEFORE parsing ambient values, including malformed ones. Flags MUST remain invocation-scoped; explicit inner-boundary transport through credential wrappers MUST be measured, and normal children MUST clear inherited flags.

Expedited local commit and push MUST choose host-local fast applicable work before any cluster probe, mirror push or Job submission through all independent entrances. Known slow and unclassified gates MUST be recorded as deferred rather than launched; a selected unknown gate reaching sixty seconds MUST stop its owned process group and record deferred-timeout. A fast failure MUST remain a refusal. A slow suite MUST NOT be split into nominally fast wrappers, and any fallback MUST preserve the selected mode and scope. Generic unsafe mutation prohibitions and the detached transport policy remain. Gate libraries MUST preserve their real fixture-tested behavior instead of returning unconditional success under an inherited flag.

Focused verification MUST run changed/directly related tests, existing per-file coverage thresholds only on cumulative touched executable paths with isolated evidence, and one recorded manual reproduction with expected/actual outcome. Generated, deleted and non-executable paths MUST receive explicit disposition. Incomplete focused evidence MUST remain recorded risk with an operator disposition; a failing assertion requires repair. Expedited evidence MUST NOT mint normal green tokens, TDD proof or reusable full coverage. Evidence readers AND writers MUST distinguish mode, scope and exact tree. The full-suite coverage producer is not the focused primitive.

Repair output MUST contain a legal adjacent code/test comment `EXPEDITED_INCIDENT_RESPONSE flag: <incident-item>`, including a comment carrier for deletion-only or strict-format changes. The audited Factory-Override and incident commit receipt MUST represent deferred replay, not invented TDD success. Normal range readers MUST verify historical PR/head/landed provenance after the environment and label disappear. Revert validates the original receipt and may remove the marker; normal factory cleanup removes it. A workflow incident MUST have scoped host authorization; the flag grants no credential and factory workers gain no workflow write scope.

A trusted PR-specific label plus structured receipt MUST project mode only into the exact repair PR/head before initial CI. Head and mode changes MUST invalidate stale verdicts. Expedited PR jobs MUST omit coverage and spec-enforcement producers, consumers, artifacts and indirect dependencies, retain declared fast checks in mixed batches/direct Actions, and expose executed/pass, failed and intentionally deferred results in the stable protected aggregate. CI parity and completeness MUST recognize the exact authorized incident form. Every master push MUST run its complete normal job graph with flags disabled; deferring spec debt confers no master exemption. Workflow reductions require explicit maintainer authority, not a logically additive exemption.

Add an incident-specific subsection to `Master-health reconciler` that takes precedence ONLY for recorded incident attempts. An independently hosted known-good released controller MUST have a durable observer receipt before an incident merge. The first required leaf-job failure MUST trigger recovery without waiting for workflow completion, reruns, classification, fix-forward or a green revert PR. Trusted early completion delivery or a CI failure callback MUST be available; the existing completed-workflow/five-minute triggers alone are insufficient. Controller and ordinary reconciler MUST share atomic repository action ownership, per-incident generation/phase fences immediately before side effects, immutable intent and post-timeout receipt recovery. The recovery receipt/fence MUST remain available when tenant, credential projection, factory, gates or self-hosted runners are broken; reconcile receipts back afterwards without a shadow lifecycle.

The complete landed incident patch, all commits/trees and exact PR identity MUST define rollback. The recovery principal MUST construct its inverse against current master using expected-head compare-and-swap, preserving later unrelated edits, recomputing on head movement and recording an owned overlap conflict rather than overwriting files. The normally provisioned narrow recovery capability MUST merge that validated inverse with no local tests, factory or pre-merge CI waits. It MUST NOT toggle ordinary protection off or simulate readiness with a skipped-green CI stub. Forge policy, overlapping classic/ruleset alignment and conformance MUST be normally changed and proven before activation; a signed commit alone does not prove no-check merge authority. Ordinary non-incident reconciler policy remains unchanged.

Original failed master CI MUST be retained through all terminal results across revert/replacement pushes. Record expected jobs and distinguish failures, skipped dependencies, cancellation and never-created work; missing original-tree proof MUST be collected through an identified continuation where feasible or remain debt. After collection classify failures and correct all revealed problems; another attempt MUST use the same incident item and require new repair/resolution evidence instead of unchanged reland. A normal successful master run leads to same-item unexpedited factory repayment with cumulative original scope; orchestrator lifecycle is governed by its owning spec. A deferred-proof-only defect in that follow-up MUST be fixed there without reverting otherwise healthy master solely for that finding. An attributable regression on master, other PRs or consumers MUST trigger recovery and fence stale cleanup, including after closure.

Source-to-release-tag, image, pin-carrier and installed-consumer attribution MUST survive rollback. Recovery MUST fence queued stale adoption and assign already-adopted consumers corrective rollout. Irreversible-state changes require a recorded existing safe compensation for unattended rollback eligibility. Source green alone does not prove deployed recovery.

The fleet audit MUST expand core's committed manifest and inventory all 37 published surface rows, custom workflows, alternate stores, templates and runtime drivers with explicit implemented, deliberately-normal or not-applicable dispositions and serving-version evidence. Core owns inherited guidance; owning repos carry their implementations. Ship contract/readers normally, release, adopt, prove recovery capability and only then enable use. Plan completion requires released installed-fleet proof, captured/replayed scenario evidence, independent completeness review and existing archive gates; this feature rollout itself MUST remain normal and unexpedited.


Append the following clause-linked scenarios to scenarios.md:

## Scenario: an incident invocation resolves mode before ordinary gate selection

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises resolve trusted incident mode and operation identity
Then an expedited invocation resolves its incident item, attempt, phase, repository and base/head into one typed execution context before selecting any gate.
And an emergency revert resolves only against a recorded incident merge and takes precedence over an expedited repair flag.
And normal master and normal factory follow-up force normal mode before interpreting inherited incident flags, including malformed values.
And ordinary invocation preserves existing gate behavior while invalid incident identity produces a named configuration refusal.
```

## Scenario: an expedited local gate skips slow work and preserves fast failures

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises select and bound expedited local gates before delegation
Then expedited commit and push select applicable local gates before staging prechecks, autofix, normal evidence lookup, cluster probes or remote submission.
And a known slow or unclassified gate is reported as deferred with its reason instead of launching the normal full aggregate.
And an unknown selected gate that reaches sixty seconds terminates its owned process group and records deferred-timeout.
And a selected fast gate failure refuses the repair with the actual failure while ordinary work retains normal gate selection.
```

## Scenario: focused incident verification cannot satisfy normal validation

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises capture focused incident tests and touched-file coverage without normal cache reuse
Then incident verification executes changed or directly related tests and reports coverage under existing thresholds only for the cumulative touched executable paths.
And incident proof records one manual reproduction with expected and observed outcome alongside the focused test and coverage evidence.
And focused collection uses isolated evidence keyed by mode, scope and exact tree while normal consumers reject partial incident evidence.
And fixture tests of enforcement implementations retain their real positive and negative behavior when incident context is inherited.
```

## Scenario: incident commit provenance remains verifiable on normal master

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises validate incident commit receipts and scoped host authorization
Then an expedited repair publishes the exact EXPEDITED_INCIDENT_RESPONSE flag marker beside changed code or tests and binds its commit receipt to the recorded incident attempt.
And normal range and replay readers validate historical incident provenance against the recorded PR, head and landed commits after the label or environment has disappeared.
And an expedited receipt records deferred replay honestly and remains distinct from normal TDD proof.
And a workflow incident requires its scoped host authorization receipt through the credential boundary while the factory retains its existing workflow credential scope.
```

## Scenario: an expedited PR defers coverage and spec work while master runs normally

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises select expedited pr checks while forcing complete normal master ci
Then a trusted expedited PR signal selects the declared fast checks while recording coverage and spec enforcement producers and consumers as intentionally deferred.
And mixed CI batches and direct actions execute retained fast targets and publish a required aggregate that distinguishes actual passes, failures and deferred work.
And a new PR head invalidates earlier incident verdicts and label events reconcile mode before permitting merge.
And every normal master push disables both incident flags and selects its complete normal job graph regardless of PR labels, markers or ambient configuration.
```

## Scenario: the first required master leaf failure fences incident recovery

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises fence incident recovery actions on an independent first-failure observer
Then an incident merge is admitted only with a durable observer receipt from a known-good released controller independent of the candidate incident tree.
And the first failing required master leaf job emits a trusted recovery action while other jobs in the same original run can continue.
And atomic per-repository action ownership and incident generation validation prevent delayed events or duplicate delivery from mutating a corrected attempt.
And recovery reads its trusted operation receipt and action fence during tenant or credential-wrapper failure and reconciles exact receipts back when service returns.
```

## Scenario: an incident revert preserves later changes without waiting for CI

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises apply and merge the complete incident inverse without quality gates
Then the incident recovery controller constructs the inverse of the complete landed multi-commit incident patch against current master and preserves unrelated later edits.
And a changed expected head causes inverse recomputation while a genuine overlap enters an owned rollback-conflict phase.
And the authorized revert merges through the scoped recovery principal without local tests, factory work or pre-merge CI waits.
And recovery records exact action and merge receipts across timeout or restart while ordinary actors retain their existing branch protection obligations.
```

## Scenario: a reverted incident retains its original CI evidence before another attempt

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises preserve failed incident ci and corrected attempt evidence
Then revert and replacement events preserve the original master run and its expected job graph through terminal results.
And evidence distinguishes completed, failed, prerequisite-blocked, cancelled and never-created checks and retains missing original-tree work as owned debt.
And a corrected expedited attempt reuses the incident item while preserving its previous PR, merge, revert and evidence identities.
And a new attempt after classification requires a repair or measured resolution rather than relanding unchanged code onto the same unresolved failure.
```

## Scenario: an incident rollback follows released artifacts into consuming repositories

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises recover incident releases and adopted fleet consumers
Then an incident release records source-to-tag, image, pin-carrier and installed-consumer attribution before adoption is acknowledged.
And an incident revert fences stale queued adoption and assigns corrective release or rollback work to consumers that already adopted the affected artifact.
And related master or other-PR regressions reopen the same incident attempt chain with stale cleanup actions fenced.
And an irreversible-state change becomes eligible for unattended rollback only when its existing safe compensation is recorded.
```

## Scenario: incident enablement follows complete installed-fleet capability proof

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises reconcile the incident surface inventory across installed fleet consumers
Then the fleet audit expands the committed manifest and reports an explicit implemented, deliberately-normal or not-applicable disposition for every incident surface and consumer.
And enablement requires serving-version evidence for gate readers, templates, driver hooks, recovery authorization and independent controller in each applicable consumer.
And consumer closure retains normal factory proof over the cumulative incident scope and all deferred spec and verification obligations.
And the operator can inspect attempts, skip reasons, focused evidence, CI runs, rollback and final factory proof through the incident item identity.
```
