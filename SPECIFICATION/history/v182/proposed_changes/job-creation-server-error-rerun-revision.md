---
proposal: job-creation-server-error-rerun.md
decision: accept
revised_at: 2026-11-10T08:03:27Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as written, per the maintainer's 2026-11-09 ruling ("Yes, why wouldn't we? As long as it's an incremental backoff, so we don't spam it or waste tokens or unnecessarily hammer github"). The signature is pre-code by construction: no created job failed. A re-run can therefore never retry a test or build failure. It is bounded at three attempts with a 2, 5 and 10 minute backoff, and each occurrence is recorded in the reconciler's own summary. Its anchors (the v171 Initialize containers rule and the reconciler contract paragraph) are on master. livespec-dev-tooling-ybnep5 realizes it and owns the scenario's test. Independent sonnet review recorded NO BLOCKERS on these exact bytes.

## Resulting Changes

- non-functional-requirements.md
- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T08:01:36Z
verdict: NO BLOCKERS
proposal_stem: job-creation-server-error-rerun
content_digest: 28ce8c6024ed133ae9122e95706ec13123808f62089d9025cca3f9719997bd8f
