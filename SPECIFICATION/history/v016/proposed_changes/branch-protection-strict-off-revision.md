---
proposal: branch-protection-strict-off.md
decision: accept
revised_at: 2026-06-22T18:33:10Z
author_human: Test <test@example.com>
author_llm: strict-off
---

## Decision and Rationale

Brings dev-tooling's branch_protection_alignment contract in line with livespec core NFR §"CI as a merge gate (branch protection)" (core PR #521): strict (require-branches-up-to-date) MUST be OFF, and the check now enforces it via a strict_enabled fail finding.

## Resulting Changes

- contracts.md
