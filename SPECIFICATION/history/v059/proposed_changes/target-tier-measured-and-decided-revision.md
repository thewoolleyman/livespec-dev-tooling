---
proposal: target-tier-measured-and-decided.md
decision: accept
revised_at: 2026-09-06T16:13:21Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: fable
---

## Decision and Rationale

Accepted as filed. The proposal replaces one sentence of the Tiers paragraph with the standing rule the measured decision produced (plan/ci-runner-cache-tiers/research/012, merged 18d54cc4; D5 RESOLVED on epic livespec-dev-tooling-efqeip): the target-directory tier is a SEEDED tree under Storage placement's reflink rule, key-scoped to compile shapes that measurably stay cold with the compilation cache warm, populator-built under Populator guardrails, every key measured and recorded with its cost before it ships, and no general dev/test key. The array gate and the measure-first obligation it discharges were satisfied by fact (ci-workvols is XFS reflink on the NVMe; the measurement is in the plan store), so carrying them forward would state obligations already met. Placement is correct (contributor-facing pool infrastructure in non-functional-requirements.md); no scenario is added because this paragraph and its siblings carry none and the clause is verified by the plan store and the host-side acceptance recipes, consistent with the section. No design record is contradicted: the v054 record asked for exactly this decision to be taken by measurement once the medium allowed it. The pre-filing doctor post-step's two warnings (an undefined variance test; eligibility stated as cause rather than measurement) were applied in the proposal itself. The maintainer directed this revise explicitly on 2026-09-06 ("Proceed with the revise"); the one other pending proposal, pin-uses-ref-template-scan-set, is another thread's and is left in place.

## Resulting Changes

- non-functional-requirements.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-06T16:11:52Z
verdict: NO BLOCKERS
proposal_stem: target-tier-measured-and-decided
content_digest: b46bb54f1d93e596bac16b6054bbc18167aba2fe1553ddd4d7a6180ba0a8cd44
