---
proposal: exit-contract-skip-outcome.md
decision: modify
revised_at: 2026-10-30T20:12:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Lifts the PASS / FAIL / SKIP-with-a-stated-reason outcome set into spec.md §"Two consumption surfaces", reconciling the binary exit contract with the ratified work-item-liveness honest-degradation SKIP and with the three-outcome per-check contracts already in contracts.md, and states that the stated reason is the only carrier distinguishing a SKIP from a PASS. Decided under delegated revise_decision_mode by the delegated-gate-fleet-rollout seat, under the maintainer's 2026-10-30 direction relayed by coordinator gitops-fleet-capacity-monitoring. No new scenario: no shipped check's behaviour changes, and each per-check SKIP and FAIL path is governed by its own per-check contract.

## Modifications

Applied inside the existing Python-package bullet as continuation paragraphs, keeping the bullet's remaining sentences. The first independent review found that the as-written PASS definition ("emitting no finding") made the shipped ci_workflow_alignment contract non-conforming (its warning-only matrix-leg exit 0 and its absent-ci.yml exit 0). PASS is therefore defined as emitting no fail-severity finding, with warning and info records allowed on a verdict-reaching path, and a sentence states that an input absence a per-check contract defines as a pass is a PASS, not a silent SKIP. Re-review: NO BLOCKERS.

## Resulting Changes

- spec.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-30T20:06:50Z
verdict: NO BLOCKERS
proposal_stem: exit-contract-skip-outcome
content_digest: 5517685b6db19cf92e32ad5285bc4b8374a3a872a10429a45cd8d07236954f1a
