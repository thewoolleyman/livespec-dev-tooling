---
proposal: no-gate-runs-actionlint-over.md
decision: accept
revised_at: 2026-11-08T19:12:53Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

livespec-dev-tooling#3317 merged a release-please.yml GitHub could not parse, past the commit gate, push gate and PR CI. Only actionlint reports that shape, so it runs at all three gates as a shared check. Carries livespec-dev-tooling-f3q7r7 and livespec-dev-tooling-hhflha.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T19:12:04Z
verdict: NO BLOCKERS
proposal_stem: no-gate-runs-actionlint-over
content_digest: d8debbe89817b43f0a2cebd0d8df8b112338676dcac53026f700e73b552388f1
