---
proposal: the-suite-green-replay-leg.md
decision: modify
revised_at: 2026-11-02T07:57:55Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:implement-test-performance
---

## Decision and Rationale

The leg has no governing contract; the proposal supplies one. Modified so the Scope bullet's shared-test-support definition matches the shipped has_shared_test_support after livespec-dev-tooling-sehj55 (PR #3105), which also excludes Markdown files, and the non-functional-requirements.md TDD bullet's narrower definition is reconciled to the same rule.

## Modifications

contracts.md Scope bullet: shared test support is any staged path under tests/ that is neither a test_*.py test module nor a Markdown file (.md/.markdown, case-insensitive); added a sentence that a staged Markdown file under tests/ does not widen a test-only cleanup to the full suite. non-functional-requirements.md: the TDD bullet's shared test-support definition (previously conftest.py or an imported module) rewritten to the same rule, pointing at contracts.md §"Suite-green replay leg".

## Resulting Changes

- contracts.md
- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T07:57:22Z
verdict: NO BLOCKERS
proposal_stem: the-suite-green-replay-leg
content_digest: d76a57bccb5a6e62769e52ecfff6510fcdbd2bf95c8a3aca3ddd158b914b3204
