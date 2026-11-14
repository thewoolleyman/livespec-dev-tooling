---
proposal: a-local-gate-launch-runs-inside-the-host-s-gate-memory-slice.md
decision: modify
revised_at: 2026-11-14T03:22:34Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

VPS memory-overload prevention, priority 1, plan dev-host-disk-retention (livespec-dev-tooling-qgwxo4). Coordinator ruling (legacy-coordinator-agent, 2026-11-14): wrap gate-start and the check aggregate in the host's local-gate.slice as its own change, outside gate-run.sh. Concurrent full-suite local gates were among the uncapped consumers in the 2026-11-13 exhaustion of the dev VPS; livespec-dev-tooling#4543/#4575 provision local-gate.slice (9G/10G, MemorySwapMax=0) and a slice bounds only what is launched into it. OOMPolicy=continue keeps one OOM-killed child from stopping the scope, so a gate still ends with a verdict. No design record is contradicted; the paragraph governs only how a launch uses host provisioning.

## Modifications

The proposal's paragraph is replaced by a reworded one on the independent reviewer's two blockers and its notes. (1) The unscoped fallback is held to the same command and an environment differing at most by the marker LIVESPEC_LOCAL_GATE_SCOPE, which the implementation exports before deciding (the proposal promised an unchanged environment). (2) The covered launches are gate-start and the check AGGREGATE that just check runs, whose scope covers its member targets; setup steps before the aggregate MAY run outside it (the proposal said every just check run). (3) The conditions become an explicit list: Linux, systemd-run present, the per-user manager reports local-gate.slice loaded, the worktree pack's scope script installed, and an optional probe scope that succeeds; any unmet condition is the unscoped launch. (4) 'Already inside the slice' is defined as the launch's own control-group path having local-gate.slice as an ancestor, and a just check inside a gate-start scope is named as such a launch. (5) The slice is stated to live in the launching user's own (per-user) service manager. (6) The gate-verdict requirement of Developer host platforms is cited for OOMPolicy=continue. Independent read-only sonnet review of these exact bytes: NO BLOCKERS at 2026-11-14T03:22:10Z.

## Resulting Changes

- non-functional-requirements.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T03:22:10Z
verdict: NO BLOCKERS
proposal_stem: a-local-gate-launch-runs-inside-the-host-s-gate-memory-slice
content_digest: ccfc399035823b05fcebc85f420457fc1197d274cc515abb234a58e71fe1fc76
