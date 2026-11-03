---
proposal: a-ci-job-that-fails.md
decision: accept
revised_at: 2026-11-03T17:25:51Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:ci-runtime-and-cost
---

## Decision and Rationale

Accepted under the delegated decision mode. legacy-coordinator-agent decided ACCEPT under R301 (2026-11-03), ratifying the release-spec-tier it pressed for livespec-dev-tooling-cetyrq on the maintainer's ruling (recorded on livespec-dev-tooling-6tgd2z, 2026-11-03 14:06:47Z: 'Retrying on a 429 (and multiple times after a incremental backoff wait ...) should be a no brainer'). Measured: 10 of 4,359 fleet job attempts over 6 h failed at Set up job on the runner's codeload action download, all on k3s ARC runners in one burst. The rule is confined to the pre-code action-download signature; a later-step failure is never re-run, so it is not a test or build retry. Independent ratification review (sonnet, read-only): NO BLOCKERS.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T17:25:00Z
verdict: NO BLOCKERS
proposal_stem: a-ci-job-that-fails
content_digest: 85ffc965a8f31d46db8533ca0a4917d6e6da8e0dad72a2e60d2ac1af24227984
