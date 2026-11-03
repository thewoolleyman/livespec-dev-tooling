---
proposal: fleet-arc-runners-set-up.md
decision: modify
revised_at: 2026-11-03T19:18:21Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:ci-cache-optimization
---

## Decision and Rationale

Modify, decided by legacy-coordinator-agent under ruling R301 (2026-11-03 ~15:4xZ), on the condition that the change adds only an action-archive cache tier to non-functional-requirements §"Runner-pool build cache tiers" with no other contract change. The clause names the tier the pool already permits in spirit: host-served, populator-written from default branches only, fail-soft, and under the kill switch. It gives livespec-dev-tooling-a35sa4 a governing clause. Measured need: 10 of 4,359 fleet job attempts in 6 h on 2026-11-03 failed at Set up job on codeload.github.com downloads, all on k3s ARC runners. Re-cut as v126 on 2026-11-03: the identical modification was first cut as v124 on PR #3295, and revise eadfad99 (v124) and PR #3312 (v125, priority 1) took those versions on master before it merged; legacy-coordinator-agent sequenced this cut behind v125. The spec delta is byte-identical, re-based onto the new master, and a fresh independent ratification review returned NO BLOCKERS on the new bytes.

## Modifications

The tier is realized as a SEEDED tree rather than the proposed host-side store under ci-cache. An independent ratification review found that a pool-wide store read in place by the job-side runner contradicts Trust by construction twice: its per-repository namespacing rule, and its rule that no job pod reaches a shared tree. Since the stock runner reads only a local directory, the tree is seeded into each work volume under the existing seed budgets and reflink rule, a runner-only node runs it cold, and the archives (public and addressed by owner, repository and commit) MAY be shared across repositories, as compilation-cache entries are. A second review found that the Trust by construction namespacing sentence exempted only the compilation cache. legacy-coordinator-agent then decided under R301 (2026-11-03) to allow ONE further clause change outside the tier: the same sentence now also exempts the action-archive cache, and states the safety terms inline. Entries are addressed by owner, repository and resolved commit SHA, never by a tag or branch. Only the populator writes the tree, never a job pod. The populator resolves each ref to its SHA from the forge and fetches the forge archive for that SHA. Adds the Given/When/Then scenario the authoring discipline requires ("a routed job sets up its actions from the pool's action-archive cache, and falls back to a download when an archive is missing"), placed after the canary scenario. Adds its spec-first heading-coverage TODO entry (host-captured end-to-end tier, owned by livespec-dev-tooling-a35sa4) and the regenerated coverage-debt register entry.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T19:17:38Z
verdict: NO BLOCKERS
proposal_stem: fleet-arc-runners-set-up
content_digest: 7a9bfc29786691bc382b7083e3ab0010f8fba4f4221325b52306bb29c73195db
