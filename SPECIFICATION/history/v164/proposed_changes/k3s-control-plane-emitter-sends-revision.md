---
proposal: k3s-control-plane-emitter-sends.md
decision: accept
revised_at: 2026-11-09T09:37:17Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as written. The two 2026-11-05 leader-lease losses were invisible in Honeycomb because the control-plane emitter reads only readiness, datastore size and datastore latency. The clause adds the API server's request latency histogram aggregated to verb and resource (measured bounded: 302 series of 24 buckets) and its HTTP 504 count, read from the same /metrics response and identity the emitter already uses (ci-runner/observability/ci-k3s-control-plane-telemetry.sh) and stamped host.name like every other series it sends. It states the no-invented-zero rule for a counter with no events, which a fixture can prove without waiting for a natural 504. Each MUST is stated by one of the three new scenarios. livespec-dev-tooling-f5qjzn carries the implementation. This decision's resulting_files are cumulative: they also hold the pressure-telemetry-also-export-the insertions, because both decisions write the same two files and the later write wins.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T09:35:53Z
verdict: NO BLOCKERS
proposal_stem: k3s-control-plane-emitter-sends
content_digest: ae9e03ab8f84f996ae55e8df40c7ba39008cac76c0c15e43fd39774baa48fd84
