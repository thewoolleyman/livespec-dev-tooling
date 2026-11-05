---
proposal: delegated-gate-admission-wait-and-abandoned-job-cleanup.md
decision: modify
revised_at: 2026-11-05T00:31:55Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:dev-host-test-gate-load
---

## Decision and Rationale

Accepted in delegated mode by seat dev-host-test-gate-load (plan dev-host-test-gate-load, epic livespec-dev-tooling-6vuiwe). legacy-coordinator-agent ruled under R301 on 2026-11-04 that the fix items livespec-dev-tooling-t5ct2q, -dtaiyu and -f2dgn6 add behaviour no ratified clause states, so they wait on this proposal. The bullets give a submitted gate Job's admission wait its own bound outside the poll budget, and delete a Job the client abandons, ending the double load measured on 2026-11-03 (13 Suspended Jobs; the pre-commit gated locally while the abandoned Job later ran). An independent read-only sonnet reviewer found NO BLOCKERS on the exact bytes.

## Modifications

Wording only. In each bullet, the proposal's sentences were merged into fewer sentences. The proposal's separate paragraph saying these bullets bind every gate-client delegation became the last sentence of the Abandoned Job bullet. The scenarios use this repository's blank-line-separated Given/When/Then style. No rule was added or dropped.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T00:31:14Z
verdict: NO BLOCKERS
proposal_stem: delegated-gate-admission-wait-and-abandoned-job-cleanup
content_digest: 57e4ca7339e14abbbbd04aa800eddb8a19962cf41d9ac2029539cbbb5c2505d3
