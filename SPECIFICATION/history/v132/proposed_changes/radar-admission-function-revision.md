---
proposal: radar-admission-function.md
decision: modify
revised_at: 2026-11-04T21:22:26Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:radar-and-deterministic-admission
---

## Decision and Rationale

Decided in delegated mode by claude:radar-and-deterministic-admission. legacy-coordinator-agent accepted this proposal under ruling R301 (2026-11-04) on the maintainer's behalf. It gives slice 3 of plan radar-and-deterministic-admission (epic livespec-dev-tooling-w7ley3, plan assertions 13-15) its governing heading. One pure function decides every READY radar target from five inputs and records the rule and the numbers behind each decision. It applies the two placement rules and takes hysteresis from the Honeycomb snapshot's own series. Every cap names the throughput figure it comes from, and a new host needs only an inventory entry. The function runs in shadow mode only. The implementation children are livespec-dev-tooling-7exa37 (inventory and thresholds files) and livespec-dev-tooling-hvfc6c (the function, blocked by 7exa37 and mauiu5).

## Modifications

Two wording repairs from the independent review's first pass, which itself found no blockers. First, the shadow-mode paragraph now makes the function's CALLER append each decision to the decision log and stamp it with the tick's UTC time, which the caller reads. The function itself performs no I/O and reads no clock, so the original 'every decision the function makes MUST be appended' could not be satisfied by the function as written. Second, the non-standard negated 'No launcher MAY start, hold or cancel' becomes 'A launcher MUST NOT start, hold or cancel'. The clause is appended at the end of non-functional-requirements.md, and the five scenarios follow the radar-family scenarios in scenarios.md. Heading-coverage TODO rows for the new H2 and the five scenarios (integration tier, owned by livespec-dev-tooling-hvfc6c) and their debt-register entries are co-edited in the revise commit. The independent re-review of the final bytes found NO BLOCKERS.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T21:21:47Z
verdict: NO BLOCKERS
proposal_stem: radar-admission-function
content_digest: 95c2fbe4ba4a6a1875a95819f90634cc6a8d4fec0abf7c6051841fb4c5d588da
