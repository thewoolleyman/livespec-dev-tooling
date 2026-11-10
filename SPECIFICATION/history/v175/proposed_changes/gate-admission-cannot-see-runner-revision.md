---
proposal: gate-admission-cannot-see-runner.md
decision: modify
revised_at: 2026-11-10T01:05:33Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified and accepted under delegated decision mode. It implements the maintainer's 2026-11-08 ruling '3b - go with recommended c' (design C, a pressure reconciler steering gate admission from measured readings, recorded as a scope event on epic livespec-dev-tooling-6vuiwe). It is spec-first, and livespec-dev-tooling-gvo7fa owns the change. No design record is contradicted, and it aligns with the in-flight homelab-worker-live-load proposal. Independent sonnet ratification review: NO BLOCKERS on the final bytes.

## Modifications

Formatting: the three new scenarios put a blank line between steps, matching every other scenario in scenarios.md. Pre-merge doctor LLM findings applied. The CPU idle reading gets a 60-second window. The quota lever is dropped, because the pool's lane-size derivation owns quota. The static lane order is defined as the converge-composed order: enrolled container-worker flavors first, as converge-worker-queues.sh places them, then the committed cluster-queue-gates.yaml order. The reconciler writes nothing into those committed files, a converge run restores the static order, and the next pass re-applies. A lane whose node cannot run the gate Job's architecture counts neither as unsaturated nor as having room. The unreadable-reading fallback covers the whole gates queue. Scenario 1 gains 'And both lanes have quota room for the gate Job'.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T01:03:51Z
verdict: NO BLOCKERS
proposal_stem: gate-admission-cannot-see-runner
content_digest: 68e445227f46ee79a58b2fe27e958caf807cb5ce3394d9639439c5cdab997a0a
