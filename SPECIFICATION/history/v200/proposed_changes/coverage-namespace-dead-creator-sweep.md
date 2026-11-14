---
topic: coverage-namespace-dead-creator-sweep
author: claude-opus-5-5
created_at: 2026-11-11T14:17:00Z
---

## Proposal: Check runners sweep coverage directories whose creator is gone

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend **Check runners leave no coverage directories behind.** in §"Enforcement-suite invocation". A runner that isolates coverage data records its creator in each coverage-namespace directory. Before it creates its own directories, it removes every leftover one whose creator is no longer running, and every unrecorded one older than 24 hours. This reclaims what a SIGKILLed runner leaves behind, which today no rule reclaims. A scenario states the observable behaviour.

### Motivation

Measured 2026-11-11 on the dev host vmi3006760. legacy-coordinator-agent routed the /tmp fill to the dev-host-disk-retention plan (livespec-dev-tooling-qgwxo4). The implementation item is livespec-dev-tooling-64ik6g, which waits on this proposal.

- /tmp, a 48G tmpfs, reached 86% at 13:27Z. Eleven `covns-full-tree-*` directories held 4.5G of it, 380-680M each, dated 2026-11-09 to 2026-11-11. No process referenced them by environ, cwd or fd.
- The paragraph today makes a runner remove its directories on exit and on SIGTERM or SIGHUP. It says 'A runner killed by SIGKILL is outside this rule, because no process can act on that signal.' That is true of the killed runner itself. But a stall kill escalated past TERM, an OOM kill, and a harness or session kill each leave a directory behind, and no rule makes anyone reclaim it.
- A later runner can reclaim it safely when it can tell the creator is gone. A recorded pid plus that process's start time distinguishes a dead creator from a reused pid. An aggregate still running keeps its directories.
- The runners that create these directories are all in this repository: the parallel check dispatcher behind `just check`, `check-changed` and `check-coverage`, and the expedited incident paths' local-gate runner and CI entry point. livespec-orchestrator-beads-fabro runs the same dispatcher through its pinned livespec-dev-tooling, so one rule here covers both.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Enforcement-suite invocation", in the paragraph beginning **Check runners leave no coverage directories behind.**, replace its last sentence:

> A runner killed by SIGKILL is outside this rule, because no process can act on that signal.

with:

> A runner killed by SIGKILL cannot remove its own directories, so the next runner reclaims them. Each runner MUST record, in every coverage-namespace directory it creates, the pid of its own process and that process's start time. Before it creates its own directories, a runner MUST remove every coverage-namespace directory under the system temp directory whose recorded creator is no longer running. A pid now held by a different process does not count as the creator. It MUST also remove every coverage-namespace directory that carries no creator record and was last modified more than 24 hours earlier. It MUST leave in place every directory whose recorded creator is still running. This removal is best-effort: a directory that cannot be removed is logged, and neither the runner's targets nor its verdict depend on it.

In `SPECIFICATION/scenarios.md`, add:

```
## Scenario: a check runner reclaims the coverage directory a killed runner left behind

Given a coverage-namespace directory under the system temp directory whose recorded creator process is no longer running

And a coverage-namespace directory whose recorded creator is a check runner still running

When another check runner starts and creates its own coverage-namespace directories

Then the directory whose creator is no longer running MUST be removed

And the directory whose creator is still running MUST remain in place

And the running runner's verdict MUST be unchanged
```

The revise commit that accepts this MUST register the new `## Scenario` heading in `tests/heading-coverage.json`. Its spec-first `"test": "TODO"` row names the integration tier and `"work_item": "livespec-dev-tooling-64ik6g"`, and the debt register is regenerated with it.
