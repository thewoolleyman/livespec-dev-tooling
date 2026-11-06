---
proposal: rule-26-mutation-kill-matrix.md
decision: modify
revised_at: 2026-11-06T06:25:11Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn). Delegated decider: the plan session for fleet-mutation-testing-rule-26 (epic livespec-dev-tooling-oi2two), working under the maintainer's 2026-11-06 direction to drive that plan autonomously. Why: livespec-dev-tooling-wou75w, the plan's shared kill-matrix engine, was held at pending-approval as definition-of-done-held because no ratified clause governs a per-test rule-26 kill matrix; the spec covers only check_mutation's kill-rate ratchet. The decision is modify rather than accept because two sentences of the filed text were corrected on the independent reviewer's notes. The Advisory-only bullet's 'Neither ... MUST delete' misused BCP14 and now reads MUST NOT. The keep-out guard's 'SHOULD run' contradicted §"Shared check inventory", under which a shared check's canonical slug MUST be wired, so the guard is now stated to be a shared check under that section. No design record is cited or contradicted. An independent read-only sonnet reviewer found NO BLOCKERS on these exact bytes. Its non-blocking notes go to the implementing item: name the guard's slug, and expect the canonical-slug completeness rows to report it unwired in each consumer until it is wired or waived.

## Modifications

Two sentences in contracts.md §"Rule-26 mutation kill matrix" differ from the filed text. The Keep-out guard bullet's last sentence now states that the guard is a shared check under §"Shared check inventory", instead of 'Adopting repositories SHOULD run that guard'. The Advisory-only sentence now reads 'The engine and the recipe MUST NOT delete, skip or rewrite any test.' scenarios.md is applied as filed.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-06T06:24:43Z
verdict: NO BLOCKERS
proposal_stem: rule-26-mutation-kill-matrix
content_digest: 5cbdd9bd23061f32cd533cb6fcd578f2a7e5554a754baabbc4a4081aa798f0dc
