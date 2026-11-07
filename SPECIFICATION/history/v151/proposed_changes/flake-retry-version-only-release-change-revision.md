---
proposal: flake-retry-version-only-release-change.md
decision: accept
revised_at: 2026-11-07T16:15:06Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn), decided by the dev-host-test-gate-load plan seat, which owns the flake-retry plugin. Measured 2026-11-07: release commit c48dfc52 changes only a version value in pyproject.toml and uv.lock among build files, and the whole-session rule then ran CI run 42384603843 with zero retries and no notice, so one flake turned master red and refused every livespec-dev-tooling commit through check-master-ci-green. The narrowed rule keeps the conservative disable for every other change to those files and treats anything it cannot compare as not version-only, and a test whose closure names the file stays touched. A version bump a test reads only at runtime, not by file name, is not touched; a deterministic failure of that kind still fails every attempt, so a retry does not mask it. The independent reviewer returned NO BLOCKERS and recomputed the digest. Implementation is owned by livespec-dev-tooling-lbinx7. No design record is contradicted.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-07T16:13:50Z
verdict: NO BLOCKERS
proposal_stem: flake-retry-version-only-release-change
content_digest: b8e2b5cd09730347b0529836e88a17e70e14ea2b19245e47c52a30eb56e9aaa6
