---
topic: a-fast-incident-member-reads-no-host-state
author: claude-opus-5-5
created_at: 2026-11-14T21:50:00Z
---

## Proposal: A fast incident member reads no host-installed tool or home directory unless it declares and probes that precondition

### Target specification files

- SPECIFICATION/contracts.md

### Summary

An adopter's check aggregate classes each member for expedited execution, and a `fast` member runs on every expedited commit and push on the incident host. Its failure is a refusal. A fast member whose verdict depends on a tool installed on that host, or on the host's home directory, can therefore fail deterministically on the incident host and refuse every expedited commit in that repository, though nothing in the incident change caused it. This proposal states that a fast member does not read host state. A member that needs host state declares the precondition, and the expedited hook probes it and records the member deferred, naming the unmet precondition, rather than failing with an opaque exit.

### Motivation

Measured 2026-11-13 while timing livespec-orchestrator-beads-fabro's gate inventory (livespec-orchestrator-beads-fabro#5124). `check-codex-skill-picker`, classed `fast`, exits 1 on the vps incident host. Its test `test_skills_picker_finds_drive_by_short_name` (tests/e2e-cli/test_codex_skill_picker.py) needs the `codex` CLI on PATH and builds its CODEX_HOME under the host's `~/.codex`. That refuses every expedited orchestrator commit on that host, so the orchestrator cannot be incident-usable.

legacy-coordinator-agent ruled on 2026-11-14 that livespec-dev-tooling-7qb2bs blocks orchestrator usability, which is in scope for plan expedited-incident-response-flag (epic livespec-dev-tooling-bqnzcm, adopter item livespec-dev-tooling-s6jt4u). It also ruled that no ratified clause covers it, and gave the seed text this proposal states.

The existing paragraph already defers known-slow and unclassified gates and keeps a fast failure a refusal. This adds the precondition rule that keeps a fast refusal meaning "the change broke something", not "this host lacks a tool".

The companion requirement, that the orchestrator's full CI reports a skipped live acceptance as skipped and never as passed, concerns that repository's own aggregate. It is left to the orchestrator's specification rather than widened into this one.

Fleet scope: every adopter of the expedited hook. livespec-overseer and livespec-driver-codex carry the same picker script and each has its own item.

### Proposed Changes

In SPECIFICATION/contracts.md §"Expedited incident execution", in the paragraph that begins "Expedited local commit and push MUST choose host-local fast applicable work", insert immediately after the sentence "A fast failure MUST remain a refusal.":

```
A member an adopter classes fast for expedited execution MUST NOT read host-installed tools or the host's home directory. A member that needs one MUST declare that precondition, and the hook MUST probe it before running the member and, when it is unmet, record the member deferred naming the unmet precondition, never running it to an opaque failure.
```
