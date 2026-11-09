---
proposal: codex-marketplace-backup-retention.md
decision: accept
revised_at: 2026-11-09T20:57:18Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:dev-host-disk-retention
---

## Decision and Rationale

Accepted as written. The dev-host-disk-retention plan (livespec-dev-tooling-qgwxo4) measured on 2026-11-07 that Codex CLI 0.166.0 leaves one `marketplace-backup-*` directory per marketplace upgrade under the retention user's `~/.codex/.tmp/marketplaces` and never removes it (29 directories, about 2.5 G on vmi3006760). No retention leg reclaims that path. The coordinator routed the decision to this plan, which ruled that the existing dev_host_retention role covers it. Placement follows the boundary litmus: host retention is contributor-only infrastructure, so the bullet sits beside the other retention bullets in non-functional-requirements.md, and the behaviour carries a BCP14 clause plus its own scenario. The bullet reuses the already-defined scratch retention period. That satisfies the proposal's instruction not to introduce a separate period, so the instruction adds no spec text of its own. The lock the clause names is confirmed in the Codex CLI 0.166.0 binary: core-plugins/src/marketplace_staging.rs uses `.staging.lock`. That Codex takes it as an flock(2) exclusive lock is inferred from how Rust file locks work on Linux, not traced. livespec-dev-tooling-aaveom's implementation proves the interlock. The upstream root cause, Codex CLI not removing its own upgrade backups, belongs to the owner of the dev host's Codex CLI install and pin (acfs). The independent sonnet review of these exact bytes found no blockers. livespec-dev-tooling-aaveom implements the change and owns the scenario's owed test.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T20:55:36Z
verdict: NO BLOCKERS
proposal_stem: codex-marketplace-backup-retention
content_digest: f32cd0dc1d47142fc25b0b7f9d30ed035bc0301759cc9ba4d4799cce2b22ad11
