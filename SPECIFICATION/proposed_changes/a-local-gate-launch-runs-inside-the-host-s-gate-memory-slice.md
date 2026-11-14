---
topic: a-local-gate-launch-runs-inside-the-host-s-gate-memory-slice
author: claude-opus-5-5
created_at: 2026-11-14T00:25:57Z
---

## Proposal: A local gate launch runs inside the host's gate memory slice when the host provides one

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Add a Gate memory slice paragraph to §"Local gate concurrency limit": where the launching user's service manager loads local-gate.slice, gate-start and every just check run on the host run inside a scope in that slice with OOMPolicy=continue and an OOM score adjustment of 500; elsewhere they launch exactly as before.

### Motivation

On 2026-11-13 the dev VPS vmi3006760 (94 GiB RAM, no swap) ran out of memory and was rebooted at 15:53Z. Concurrent full-suite local gates were among the uncapped consumers. livespec-dev-tooling#4543 and #4575 (role dev_host_memory_bounds, coordinator-graded) provision a user-manager local-gate.slice at MemoryHigh 9G / MemoryMax 10G with MemorySwapMax=0, and the slot limit is now 1. A slice bounds only what is launched into it, and the gate launch path is this repository's code (the worktree pack's gate-start and this repository's check recipe). OOMPolicy=continue is required because systemd 257 defaults to DefaultOOMPolicy=stop, under which one OOM-killed child stops the scope and ends the gate without a verdict. The maintainer's direction for the incident asks that gates carry a high OOM score; raising oom_score_adj needs no privilege. Coordinator ruling (legacy-coordinator-agent, 2026-11-14): land the wrap as its own PR outside gate-run.sh.

### Proposed Changes

In `non-functional-requirements.md` §"Local gate concurrency limit", insert this paragraph immediately before the paragraph beginning "A host's limit MUST be provisioned through a committed converge":

**Gate memory slice.** On a Linux host whose launching user's service manager loads the slice `local-gate.slice`, where a scope launcher (`systemd-run`) is present and a probe scope can be created in that slice, a gate started through the detached gate runner's `gate-start` and every `just check` run on the host MUST run, together with every process the launch starts, inside a transient service-manager scope placed in `local-gate.slice`, with out-of-memory policy `continue`. When `choom` is present, the launched command's out-of-memory score adjustment MUST be raised to 500, so that under host memory pressure the kernel ends a gate before the ledger server or an agent session. A launch that already runs inside `local-gate.slice` MUST NOT create a second scope. When any of those conditions does not hold, the launch MUST proceed with the same command and environment it uses without this paragraph, and MUST NOT fail because the slice is absent, which keeps macOS hosts, factory sandboxes and gate Jobs unchanged. The slice and its memory bounds are host provisioning (`ansible/roles/dev_host_memory_bounds`); this paragraph governs only how a launch uses them, and it is a stopgap on the same terms as the slot limit.
