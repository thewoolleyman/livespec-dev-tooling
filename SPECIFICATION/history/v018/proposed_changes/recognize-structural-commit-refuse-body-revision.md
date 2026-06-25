---
proposal: recognize-structural-commit-refuse-body.md
decision: accept
revised_at: 2026-06-25T21:46:15Z
author_human: Test <test@example.com>
author_llm: thewoolleyman
---

## Decision and Rationale

Accept as filed: the verifier code (this PR) already broadens the fingerprint to recognize the structural git-common-dir detection alongside the legacy show-toplevel detection; the contract description must record both so it matches the landed mechanism and keeps the fleet green across the migration.

## Resulting Changes

- contracts.md
