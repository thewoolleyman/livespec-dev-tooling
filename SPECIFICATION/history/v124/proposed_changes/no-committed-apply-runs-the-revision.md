---
proposal: no-committed-apply-runs-the.md
decision: accept
revised_at: 2026-11-03T17:25:51Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:ci-runtime-and-cost
---

## Decision and Rationale

Accepted under the delegated decision mode. legacy-coordinator-agent decided ACCEPT under R301 (2026-11-03). The ci_converge_unit role enables but deliberately does not start converge-ci-stack.service, and the fleet host guard correctly refuses a by-hand start, so no committed path applied a merged runner-pool change (livespec-dev-tooling-lzkzwb's #3266) to the live cluster short of a reboot. Carrier: livespec-dev-tooling-un3zhi. Independent ratification review (sonnet, read-only): NO BLOCKERS.

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
proposal_stem: no-committed-apply-runs-the
content_digest: a793f1bdb7f9c2ccc0e1b6a348dba1ffda1b3b83a02957ac1114339cdf93d430
