---
proposal: dev-host-disk-retention.md
decision: accept
revised_at: 2026-10-22T00:58:33Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted on the merits: the dev host had no standing retention (measured 2026-10-21 at 94% full, work-item livespec-dev-tooling-fj6dm5), the hp factory host already carries the analogous disk_guard control, and terminal-only, age-gated gate-run removal keyed on gate-run.sh's own state markers can never remove a run a waiter may still report. Decided by the delegated-gate-fleet-rollout plan owner under R202 with independent fable ratification review NO BLOCKERS. The resulting files co-edit the two new headings' heading-coverage TODO rows (work_item fj6dm5, integration-tier) and the regenerated debt register, as the proposal stated.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-22T00:58:32Z
verdict: NO BLOCKERS
proposal_stem: dev-host-disk-retention
content_digest: 50e29553afa1c99f72929c7a27f0062e76ad483b21b8464259123f348c8dbdec
