---
topic: rule-26-pruning-tool-remove
author: codex:fleet-mutation-testing-rule-26
created_at: 2026-11-13T20:01:26Z
---

## Proposal: A separate pruning tool enforces one-at-a-time removal, preserved kills and spec coverage

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add the S1-S5 pruning safeguards as a separate tool contract before any test removal; retain the mutation engine and recipe as advisory only.

### Motivation

The maintainer required all pruning safeguards before anything is deleted, recorded on livespec-dev-tooling-oi2two at 2026-11-10T05:32:43Z. Existing child livespec-dev-tooling-46y4en owns the tool but is held as spec-change tier until this contract is ratified. A candidate list alone cannot establish that a sequence of removals preserves kills, spec coverage or test intent.

### Proposed Changes

Add the following separate contract to contracts.md, without changing the kill-matrix engine and recipe's advisory-only rule.

## Rule-26 pruning safeguards

livespec-dev-tooling MUST provide a separate pruning tool that proposes one test removal and verifies its result. A redundancy candidate is evidence for review, not permission to remove a group of tests.

- **Evidence prerequisite.** The tool MUST accept only a complete exhaustive kill-matrix report for the target's current test collection, first-party source, configuration, dependencies and executing engine. A report's provenance MUST be established by a record captured with its run that binds the report's content digest to those inputs' content digests, the executing engine's source identity and the invocation's successful completion. The tool MUST refuse missing, stale, interrupted, diagnostic or provenance-unknown evidence with a finding naming the invalid input; it MUST NOT create a retrospective run record from the current tree for an unbound old report. The tool MUST NOT use a diagnostic report to propose or validate a removal. It MUST leave the kill-matrix engine and recipe's prohibition on deleting, skipping or rewriting tests intact.
- **One candidate.** Given at least one eligible candidate with a supplied review reason, the tool MUST propose exactly one node id from the report's redundancy candidates; when none is eligible it MUST emit a no-removal result naming the disqualifying inputs. It MUST NOT propose a test listed under baseline failures or unapplied-coverage tests. Before proposing another removal, it MUST require a complete incremental kill-matrix report taken after the previous removal. Relative to that removal's before report, the after collection MUST remove exactly the proposed node id; changing other test bodies, first-party source, configuration, dependencies or the executing engine makes the evidence non-comparable and MUST be refused rather than credited as a safe removal. Repointing the coverage registry as specified below is allowed in the same change.
- **Preserved kills.** For each mutant killed in the before report, the tool MUST require the same mutant, with the same enclosing-function digest, to remain applied and killed in the after report. A missing, surviving, unapplied or incomparable formerly killed mutant MUST make verification exit nonzero, name that mutant and prohibit a subsequent proposal. Incremental verification MUST use the engine's normal cache-validity rules; it MUST NOT merely subtract the removed test from the old matrix.
- **Spec coverage.** The tool MUST read tests/heading-coverage.json, or an explicitly supplied equivalent registry. It MUST refuse a candidate cited by a row and name that row unless the same change repoints the row to another real collected test. An absent or unreadable required registry MUST be refused. A TODO or nonexistent replacement MUST NOT satisfy this exception.
- **Intent review.** Before a proposed removal is accepted, its reviewer MUST record a per-test reason explaining why ordering, concurrency, messages, formatting, performance, tool integration and regression intent remain covered where relevant. The tool MUST require that reason to accompany the proposal and its verification record; it MUST NOT infer intent equivalence solely from the matrix. The removal PR MUST carry that reason.
- **Recorded result.** The tool MUST emit a machine-readable proposal or refusal naming the candidate, the before report, any citing registry rows and the review reason. Verification MUST name the before and after report identities and every failed preservation check. Only a successful verification permits another proposal. Invoking the tool MUST NOT add a mutation run to just check, a commit or push hook, or a required per-PR job.

Append these scenarios to scenarios.md.

## Scenario: pruning proposes one measured redundancy candidate at a time

Given a complete exhaustive kill-matrix report for the current target where tests A and B are redundancy candidates and neither is cited by the coverage registry or listed under baseline failures or unapplied-coverage tests

And the reviewer supplies a per-test intent reason for A

When the pruning tool proposes a removal

Then it MUST propose exactly A and MUST NOT propose both A and B

And it MUST refuse another proposal until a complete post-removal incremental report verifies A's removal

## Scenario: pruning refuses unmeasured or spec-cited candidates

Given a report with candidates A, B and C where A is listed under unapplied-coverage tests, B is a baseline failure and a coverage-registry row cites C

When the pruning tool considers those candidates

Then it MUST propose no removal and MUST name the disqualifying entries and citing row

And replacing the citing row with TODO or a nonexistent test MUST NOT permit C

## Scenario: a real replacement preserves a removed test's spec coverage

Given a complete exhaustive report whose candidate A is cited by a coverage-registry row and a real collected test B remains

When the same change removes only A and repoints that row to B

And the reviewer supplies A's intent reason and the complete incremental after report preserves every formerly killed mutant

Then the pruning tool MUST accept the registry replacement and verify that removal

## Scenario: pruning stops when a formerly killed mutant loses its proof

Given the before report kills M1 and M2 and the proposed removal is A

When the complete incremental after report lists M1 as surviving and omits M2

Then verification MUST exit nonzero, name M1 and M2 and refuse a subsequent proposal

And a formerly killed mutant becoming unapplied or changing its function digest MUST also refuse verification

## Scenario: pruning refuses incomplete or incomparable evidence

Given a diagnostic, interrupted, stale or provenance-unknown report, or a required coverage registry that is absent or unreadable

When the pruning tool is invoked

Then it MUST exit nonzero with a finding naming the invalid input and MUST propose no removal

And it MUST refuse to bind an old report retrospectively to the current tree

And after a proposed removal of A, removing B as well or changing another test body, first-party source, configuration, dependencies or the executing engine MUST make verification refuse incomparable evidence

## Scenario: pruning requires the reviewed intent reason and preserves on-demand execution

Given a measured redundancy candidate A and no recorded per-test intent reason

When the pruning tool is asked to accept A's removal

Then it MUST refuse and name the missing reason

And an invocation with a reason MUST preserve that reason in the proposal and verification record for A's removal PR

And invoking the tool MUST NOT add mutation execution to just check, commit or push hooks, or a required per-PR job

