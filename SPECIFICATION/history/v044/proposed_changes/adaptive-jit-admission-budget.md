---
topic: adaptive-jit-admission-budget
author: gpt-5.6
created_at: 2026-08-14T05:25:46Z
---

## Proposal: Adaptive installation-wide JIT admission budget

### Target specification files

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json

### Summary

Replace the rejected fixed positive inter-request spacing model with an adaptive, installation-wide, budget-accounted admission controller that permits immediate deduplicated steady-state replacement while bounding restart bursts and fleet capacity.

### Motivation

The observed fixed-delay proposal would unnecessarily serialize healthy slot replacement. Live hotfix evidence instead shows that an immediate rescan admitted 43 runners, held the physical cap at 482, produced no failed units or GitHub throttles, and completed run 31769707940. The durable contract must retain rate-limit protection without converting routine recovery into a per-runner sleep.

### Proposed Changes

Add a JIT-runner admission requirement that supersedes the fixed-positive-spacing portion of PR #1398. It MUST use one installation-wide, durable single-writer controller and deduplicated event-driven (or immediate-rescan equivalent) demand. It MUST NOT impose unconditional per-runner delay. The controller MAY take an initial tight batch against no more than 450 of GitHub's 900 REST points/minute secondary budget (about 45 two-POST mint pairs: approximately 5 points per content-generating POST and 10 points per pair) and then MUST refill from budget accounting. Only actual 403/429 results or authoritative Retry-After/reset guidance open a shared circuit/backoff; malformed or absent guidance uses a finite conservative fallback. Per-repo logical ceilings double for two concurrent matrices, but fleet physical occupancy remains exactly 482; desired admission is min(queued jobs, doubled repo ceiling, fair share of remaining cap), with fair borrowing. Add integration scenarios and heading coverage for immediate steady-state replacement, bounded restart admission, shared circuit recovery, restart durability, fair borrowing, and the 482-cap/never-964 invariant.
