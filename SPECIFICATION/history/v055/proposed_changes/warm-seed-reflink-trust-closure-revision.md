---
proposal: warm-seed-reflink-trust-closure.md
decision: accept
revised_at: 2026-09-06T03:27:34Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-fable-5-1 (plan ci-runner-cache-tiers session)
---

## Decision and Rationale

Accepted as filed. The maintainer chose option (a) of livespec plan ci-runner-pod-lifecycle-reliability research/006 (reflink seed on an XFS ci-workvols tier), the host half landed on 2026-09-06 under livespec-dev-tooling-hmv2bo, and the maintainer directed the plan session to continue; this proposal makes the ratified text say what the pool now enforces. It re-bases four clauses onto the private-per-volume seed, leaves the six-simultaneous-starts sentence to the pending livespec-1qpt re-base, keeps the no-reflink rule for every other cache, keeps the fail-soft rule (no seed rather than a byte copy), changes no H2 heading, and matches what cache-negative-tests.sh case 1 asserts. An independent read-only reviewer compared the resulting bytes (both files) against the re-filed proposal and the design record and returned NO BLOCKERS; the first review's two blockers (the scenarios.md omission and the mounted-by-nothing over-claim) were corrected before re-filing.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-06T03:26:15Z
verdict: NO BLOCKERS
proposal_stem: warm-seed-reflink-trust-closure
content_digest: 92e21ce155d7815c1b1cfd28dd422836023e58020922d6197669c5eb766e739a
