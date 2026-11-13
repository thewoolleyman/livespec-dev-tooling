---
proposal: every-workflow-editing-pr-rewrites.md
decision: accept
revised_at: 2026-11-13T17:56:57Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as written, at the dev-tooling revise slot v213, which this seat claimed and named to legacy-coordinator-agent (handoff 85, 2026-11-13). The proposal specifies the guard every workflow-editing pull request passes, and the exemption layout it reads. That is a contributor-side CI guard, so the clause lands in non-functional-requirements.md under Hooks and CI, after the workflow-parse rule. Its ten Given/When/Then scenarios land in scenarios.md beside the existing workflow-parse scenario. The text is the proposal's own, unmodified. The independent sonnet ratification reviewer read both diffs against today's files, found two pure insertions and nothing else changed, and returned NO BLOCKERS for these exact bytes. The ten scenario headings get consumer-tier TODO rows in tests/heading-coverage.json, owned by livespec-dev-tooling-oim422, in the same commit.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T17:55:48Z
verdict: NO BLOCKERS
proposal_stem: every-workflow-editing-pr-rewrites
content_digest: d40502761d31cef566c65eaee0b1d8103a73c5cd5b610688c18118f178f1d910
