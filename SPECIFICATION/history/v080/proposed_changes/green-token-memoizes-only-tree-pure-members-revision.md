---
proposal: green-token-memoizes-only-tree-pure-members.md
decision: accept
revised_at: 2026-10-19T04:47:36Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under this repository's delegated revise_decision_mode, as the spec prerequisite for work-item livespec-dev-tooling-aape (plan delegated-gate-fleet-rollout, epic livespec-dev-tooling-mvalxq). The green token keyed a memoized verdict on the tree hash, which is sound only for checks whose verdict depends on the tree alone. The old 'Explicit local route' and 'Verdict' wording let a token match skip members that read state outside the tree, such as master CI status and live branch protection. The token now memoizes only tree-pure members. World-reading and undeclared members run on every push and refuse it on failure, and this repository's aggregate refuses a member with no purity declaration. Its two new scenarios carry heading-coverage TODO rows owned by livespec-dev-tooling-aape, with reasons that name the integration tier. This decision is applied first. Its resulting files carry this proposal's edits alone; the next decision's resulting files carry both. Independent ratification review: Fable 5.1 (claude-fable-5-1), a separately spawned read-only reviewer, returned NO BLOCKERS on both proposals' text, with five non-blocking nits. The nits were folded into the proposals before acceptance (commit 'fold independent review nits'). A second separately spawned read-only Fable 5.1 review, under this repository's auto-spawn ratification_review, then reviewed these exact resulting-file bytes. It reproduced both content digests with its own implementation, verified that each change is exactly what the proposal specifies and nothing else, checked that the nits were folded and nothing else changed, swept the spec for drift, and checked the heading-coverage rows. It returned NO BLOCKERS at 2026-10-18T19:51:45Z. The revise was first cut as v079. That number was then taken on master by host-provisioning-tree (eff9f1e9), so the revise was redone as v080 against the new base. The only change to the resulting bytes is master's own new heading-coverage row. A third separately spawned read-only Fable 5.1 (claude-fable-5-1) review of these exact v080 resulting bytes reproduced both content digests and found no difference beyond that row. It found no drift against the new base and confirmed master holds no v080. It returned NO BLOCKERS at 2026-10-19T04:46:05Z.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-19T04:46:05Z
verdict: NO BLOCKERS
proposal_stem: green-token-memoizes-only-tree-pure-members
content_digest: 7e7e08d30732db303276fa5415d04149e50c29a27d178e567bcb8324c52b2fe7
