---
proposal: a-flake-retry-record-carries.md
decision: accept
revised_at: 2026-11-08T05:09:44Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as proposed. A re-run that passes leaves no trace of why its first attempt failed, so every root-fix item filed from a retry reached its owner without a cause (vzfxlg, gokm2v, wacdfl). The record now carries each failed attempt's failure text, cut to 4000 characters and marked when cut, and the FLAKE-RETRIED block shows its first line. The change is additive to the Untouched-test retry reporting sentence. The sibling Flake-retry record delivery bullet publishes the records unchanged, so they simply carry the new field. The independent read-only sonnet review found no contradiction with the existing scenario, which does not enumerate the record's fields. Implementation carrier: livespec-dev-tooling-b7l6it.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T05:09:03Z
verdict: NO BLOCKERS
proposal_stem: a-flake-retry-record-carries
content_digest: d8f01af46a27aa4ea9734c9a8141b4aec362e124f5a31868f4f5a49341ecd616
