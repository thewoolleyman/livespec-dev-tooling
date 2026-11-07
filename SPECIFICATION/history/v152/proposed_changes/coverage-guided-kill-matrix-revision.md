---
proposal: coverage-guided-kill-matrix.md
decision: accept
revised_at: 2026-11-07T17:29:18Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn). The delegated decider is the plan session for fleet-mutation-testing-rule-26 (epic livespec-dev-tooling-oi2two). The change implements the maintainer's attended ruling of 2026-11-07, recorded as a scope event on the epic, that the rule-26 kill matrix is coverage-guided: the shipped every-test-against-every-mutant engine cannot finish at fleet scale. The proposal is applied as filed. No design record is cited or contradicted. An independent read-only sonnet reviewer found NO BLOCKERS on these exact bytes. Its non-blocking notes go to the implementing item livespec-dev-tooling-tcmw34: module-level and import-time mutants that no test context executes should fall back to all tests or be disclosed; measured-but-partial coverage (subprocess or native code) shares that fidelity gap; the report could distinguish never-covered mutants from covered survivors; 'mutated location' granularity and the selection-method vocabulary are left to the implementation.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-07T17:28:44Z
verdict: NO BLOCKERS
proposal_stem: coverage-guided-kill-matrix
content_digest: 15278946cb6d1fbed626c4e5eff0779d297b26e21867eef4a273bcd39193be99
