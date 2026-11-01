---
proposal: delegated-commit-time-replay-test-runs.md
decision: accept
revised_at: 2026-11-01T13:31:17Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

ACCEPT. Ratifies, in contracts.md "## Delegated commit-time replay test runs" plus four scenarios, the consumer-facing client side of livespec v234's commit-time delegation as modified there (livespec history/v234 delegated-commit-time-gate-revision.md, MODIFY): only the commit-msg replay gate's test runs delegate, the pre-commit aggregate does not; the staged tree is git write-tree of the index; judgement and trailers stay on the committing host and the trailers name the gate Job and the staged tree; an absent verdict falls back to a real local run and never refuses a commit (pre-push keeps its refusal); a host without the gates credential gates locally and says so; the opt-in key delegated_commit_tests is separate from delegated_gate. It cites livespec v234 as its design record and contradicts none. Spec-led, not drift-origin. It releases the spec hold on livespec-dev-tooling-sewnfp, which implements it, on maintainer direction 2026-11-01 ~13:5xZ (sewnfp is the priority: dev-host contention is on the critical path). Decided under delegated revise_decision_mode by plan session implement-test-performance (epic livespec-dev-tooling-sv6m5p); the maintainer ruled 2026-11-01 that this plan runs autonomously. Independent review: separately spawned read-only sonnet agent, NO BLOCKERS on these exact bytes, with five non-blocking nits left for follow-up: no scenario exercises the Green or suite-green leg; 'runs no pytest' is implied by the section intro, not a separate MUST NOT; trailer key names are not fixed; telemetry for commit-time runs is unstated; the 'gated locally' line is not specified per leg or per commit. The five new H2s get spec-first heading-coverage TODO rows owned by livespec-dev-tooling-sewnfp and debt-register entries, co-edited in the revise commit.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-01T13:29:46Z
verdict: NO BLOCKERS
proposal_stem: delegated-commit-time-replay-test-runs
content_digest: 2f9b9e0c7d9783cbfcfb3e721a81579322400f87abf1e827b96667929bfde028
