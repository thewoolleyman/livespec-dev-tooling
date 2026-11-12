---
topic: the-stall-bound-snapshots-the-run
author: claude-opus-5-5
created_at: 2026-11-12T13:30:28Z
---

## Proposal: A gate command the stall bound ends leaves a process snapshot that its verdict names

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When the detached gate runner's **Stall bound** ends a gate command, the runner first writes a `stall-snapshot` file into the run directory, before it sends any signal. The file lists every process attributed to the run, with its pid, parent pid, session id, elapsed time, kernel wait channel and command line, in forest order. The run's stall-bound line in `output.log`, and the `FAILED` state that `gate-wait` and `gate-status` print, name that file. A snapshot that cannot be taken records its reason and never delays or prevents the kill. Writing the snapshot does not renew the stall window. Work item livespec-dev-tooling-q4ahay carries the implementation.

### Motivation

A silent stall cannot be localized once the runner has killed it, because the runner records only the stall-bound line and the processes are gone. Measured case: livespec-dev-tooling#4322's first push gate, run 20261112T123324Z-2194210, ran from 12:33:24Z to 12:49:34Z and exited 124. It printed no output at all, not even lefthook's banner. The journal holds no credential-helper or sudo call from that worktree, so the stall came before git reached the remote and before any hook ran. Bare re-probes passed, and after the kill nothing could say which process had hung. A snapshot of the attributed process tree, taken before the first signal, turns the next such stall from unlocalizable into a named process with its wait channel. legacy-coordinator-agent agreed (2026-11-12) to take this diagnosability fix instead of filing an item for the unlocalized hang. Plan dev-host-test-gate-load (epic livespec-dev-tooling-6vuiwe) recorded the carrier in its 13:21:20Z scope event. The carrier serves the plan's gate surfaces but carries no plan assertion.

### Proposed Changes

### SPECIFICATION/contracts.md §"Detached gate runner"

Insert this new bullet directly after the existing "**Stall bound.**" bullet and before "**Stop.**":

- **Stall snapshot.** When the **Stall bound** ends a gate command, the runner MUST first write a `stall-snapshot` file into the run's directory, BEFORE it sends any signal. It holds a header line with the UTC time it was taken, then one line per process attributed to the run under **Stall bound**'s attribution: the command's own process group and every descendant that entered a new OS session. Each line carries the pid, parent pid, session id, elapsed time, kernel wait channel and full command line, in parent-before-child (forest) order. The stall-bound line the runner appends to `output.log`, and the `FAILED` state that `gate-wait` and `gate-status` print for that run, MUST name the `stall-snapshot` path. When the snapshot cannot be taken, the runner MUST write the reason into that file and still end the command on schedule, so a failed snapshot never delays or prevents the kill. Writing the snapshot MUST NOT count as progress and MUST NOT renew the stall window. Fleet scope: every repository whose gate runner is the wheel-carried `CANONICAL_GATE_RUN_BODY`. This bullet is spec-first: the shipped runner records only the stall-bound line, and work item livespec-dev-tooling-q4ahay owns the change.

### SPECIFICATION/scenarios.md

Add this scenario directly after "## Scenario: a detached gate whose process dies without a verdict reports DIED_WITHOUT_VERDICT and exits 75":

## Scenario: a gate command the stall bound ends leaves a process snapshot that its verdict names

Given a detached gate run whose command, and a descendant that entered its own OS session, produce no output and no progress-stamp renewal for the stall window

When the runner ends the command

Then the run directory MUST hold a `stall-snapshot` written before the first signal, listing each attributed process with its pid, parent pid, session id, elapsed time, wait channel and command line

And the run's `output.log` stall-bound line and its `FAILED` state from `gate-status` MUST name that file

And the verdict MUST be `FAILED`, never a pass

### Revise co-edit (outside the spec target)

The revise commit that accepts this proposal MUST add a `tests/heading-coverage.json` row for the new scenario heading: `"test": "TODO"`, a `reason` naming the integration tier as the tier the owed test runs at and naming livespec-dev-tooling-q4ahay as its owner, and `"work_item": "livespec-dev-tooling-q4ahay"`. It MUST also stage the regenerated `tests/heading-coverage-debt.json` from `just generate-heading-coverage-debt-register`. The new contracts bullet adds no `## ` heading, so it owes no new row.
