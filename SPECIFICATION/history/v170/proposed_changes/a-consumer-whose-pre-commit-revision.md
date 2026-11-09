---
proposal: a-consumer-whose-pre-commit.md
decision: modify
revised_at: 2026-11-09T18:37:11Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:implement-test-performance
---

## Decision and Rationale

Modified under delegated mode. The Same-tree reuse bullet (z5fwwn) states when evidence is reused but not who writes it; every consumer fork's local pre-commit fallback writes none, so a factory sandbox runs the whole suite twice for each behaviour-preserving commit (orchestrator run 01M6W3C2BBME, bd-ib-2eyiwy: 3728 s aggregate, then a re-run killed at 900 s). One library entry point owns the evidence write and its guards; a consumer that does not adopt it keeps the Scope bullet's full run. Outcome telemetry makes the reused-or-ran class countable in Honeycomb, which today cannot see it. Carries plan implement-test-performance (livespec-dev-tooling-sv6m5p) assertion 2; implementation item livespec-dev-tooling-4scqti. Revise order set by legacy-coordinator-agent (09:40Z, 2026-11-09). The independent read-only reviewer (sonnet) found no blockers on the exact bytes.

## Modifications

Reconciled with v166's Behaviour-preserving claim bullet, which merged after this proposal was filed, and with the affected-tests scope ratified in the same pass. In the Outcome telemetry bullet the scope attribute is the TDD-Suite-Green-Scope value the leg recorded, or would have recorded on a green outcome (such as full-suite or staged-tests), instead of the closed list (full-suite or staged-tests). The outcome `red` is defined to cover every refusal other than `ended`, including a refusal by the Behaviour-preserving claim's parent-tree replay. Three further fixes come from the pre-merge doctor LLM pass, which walked the text through the live code. First, telemetry names its sandbox discriminator: a checkout with livespec.sandboxExempt set to true sends to $LIVESPEC_SANDBOX_OTEL_ENDPOINT, and every other checkout sends to the loopback endpoint and override gate_outcome_telemetry uses. Second, "the evidence write exists in one place" became "the local-aggregate evidence write", because pre_commit_delegate also writes evidence after a cluster verdict. Third, both local-aggregate scenarios are restricted to a behaviour-preserving commit; a test-only cleanup runs its staged tests under the Scope bullet. The headings are as proposed. Placement: the entry-point bullet follows Same-tree reuse; Outcome telemetry follows the affected-tests bullet that the same pass adds after the entry point.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T18:36:42Z
verdict: NO BLOCKERS
proposal_stem: a-consumer-whose-pre-commit
content_digest: 4abaa0305909c7ba233352132e08e8d4255a5a0a2bd2da426b754a3601b8153b
