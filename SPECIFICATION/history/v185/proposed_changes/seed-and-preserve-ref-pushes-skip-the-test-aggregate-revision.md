---
proposal: seed-and-preserve-ref-pushes-skip-the-test-aggregate.md
decision: modify
revised_at: 2026-11-10T11:39:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in substance: a push whose non-deleting ref updates all name refs/heads/needs-human/ or refs/heads/preserve/ refs runs only the authorization-reading members and no test aggregate. Such refs are never merge candidates: the factory re-gates every run's own tree, and any pull request opened from one is still gated by CI's required ci-green, so no gate is reduced on a mergeable ref (ruled in-seat by dev-host-test-gate-load, confirmed by legacy-coordinator-agent). The authorization members stay because the gate Job never runs them. Measured cost: one hand-pushed seed ref ran a 43-minute delegated gates Job (gate-livespec-orchestrator-beads-fabro-gxlsw, 2026-11-10).

## Modifications

Against the filed text: (1) the push is classified by its NON-DELETING ref updates and must have at least one, and a deletion publishes no tree, runs no member and neither makes a push ordinary nor counts as a seed or preserve update (the filed 'deletions count as updates of the deleted name' would have required running members against a tree a deletion does not have, and would vacuously match an all-deletion push); (2) the authorization members run against the tree of the commit each update pushes, which need not be HEAD; (3) the ref an update names is the remote ref on the pre-push gate's standard input; (4) for a covered push the bullet takes precedence over the Explicit local route and Token memoization bullets; (5) the conventional spec-first sentence names livespec-dev-tooling-2zb3gk. The scenario is adjusted to the at-least-one-non-deleting-update wording. Notes (2)-(4) came from the independent ratification reviewer's first pass.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T11:38:13Z
verdict: NO BLOCKERS
proposal_stem: seed-and-preserve-ref-pushes-skip-the-test-aggregate
content_digest: 8f94582091874457b7dc7117eec3537ebed2d7c444952450c774024923d03d69
