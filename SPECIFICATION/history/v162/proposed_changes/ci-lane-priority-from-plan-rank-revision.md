---
proposal: ci-lane-priority-from-plan-rank.md
decision: modify
revised_at: 2026-11-08T19:58:06Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

livespec-dev-tooling#3796, the incident hook fix on the expedited track's critical path, waited 220 s behind first-in-first-out PR-lane admission on 2026-11-08, and priority was enforced only by hand-cancelling factory draft runs. The maintainer directed a generic, priority-driven fix with no hard-coded plan names; legacy-coordinator-agent ruled the mechanism (phase 1 of livespec-dev-tooling-5wewi2; preemption stays with livespec-dev-tooling-samgg2). Lane priority is derived from the maintainer radar through CI_PRIORITY_RECORD and chosen at runs-on behind an opt-in priority runner set, changing admission order only, with every unusable case on today's routing.

## Modifications

Accepted as proposed with one consistency edit in constraints.md §"CI matrix shape": the revert paragraph's closing clause 'so the two variables' settings together with the inline fallback are the entire routing contract' becomes 'so the variables' settings, the route job's band output and the inline fallback together are the entire routing contract', so it no longer contradicts the inserted paragraph that adds the priority variables and the band output to the routing contract. Second, in non-functional-requirements.md §"CI lane priority from the maintainer radar", the citation §"Runner placement follows admission capacity" names a bold paragraph rather than a heading, so it becomes 'the "Runner placement follows admission capacity" paragraph of §"Runner-pool node rebuild recipe"', which resolves under doctor-no-cross-spec-reference.

## Resulting Changes

- constraints.md
- contracts.md
- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T19:57:40Z
verdict: NO BLOCKERS
proposal_stem: ci-lane-priority-from-plan-rank
content_digest: 859066175ef58c82e974553dae7571774cf60fe0b090364d1e41fe8017ec91b3
