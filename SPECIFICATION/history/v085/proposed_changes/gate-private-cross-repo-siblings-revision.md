---
proposal: gate-private-cross-repo-siblings.md
decision: accept
revised_at: 2026-10-22T01:48:32Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted on the merits per coordinator R543: a consumer naming a private cross_repo_targets sibling cannot use the delegated venue at all today. The pushing-host-minted, sibling-scoped, contents:read, sub-hour App installation token keeps long-lived authority on the host that holds it, consistent with the v082 principle, and closes the gate's three evidence channels to the token. Decided by the delegated-gate-fleet-rollout plan owner under R202 with independent fable ratification review NO BLOCKERS. The reviewer's trade-off note (per-run Secret delivery needs a gates RBAC widening; publishing sibling trees to the gate mirror would avoid any pod credential) is recorded on work-item livespec-dev-tooling-7kvh2d for the implementer, not taken into the clause, because the coordinator directed the App-token design.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-22T01:48:31Z
verdict: NO BLOCKERS
proposal_stem: gate-private-cross-repo-siblings
content_digest: 0711cc0b16a98721c9d90c7756e546952f4786743abd60821151b9f9d1dc9efa
