---
proposal: pressure-telemetry-also-export-the.md
decision: accept
revised_at: 2026-11-09T09:37:17Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as written. §"Execution-target pressure telemetry" states host-level pressure only, so the k3s server's CPU pressure during a node saturation window is unexported and cannot be read after the window, which livespec-dev-tooling-cetudy's host-captured assertion needs. The clause extends the existing emitter with an empty-by-default per-host cgroup list, keeps the all-or-nothing request the live emitter (ansible/roles/pressure_telemetry/files/pressure-telemetry.sh, one curl after every read) already uses, applies the existing no-zeros rule to a missing cgroup file, and states its precedence over the 15-minute coverage rule instead of silently contradicting it. Each MUST is stated by one of the three new scenarios. livespec-dev-tooling-3gm5rb carries the implementation.

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
proposal_stem: pressure-telemetry-also-export-the
content_digest: f9dffb077e5901820e4f2b34d98421e3d21039744a9408ab18d69c3e250b1d26
