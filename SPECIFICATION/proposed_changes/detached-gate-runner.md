---
topic: detached-gate-runner
author: claude-fable-5-1
created_at: 2026-10-14T04:41:08Z
---

## Proposal: Specify this repository's detached gate runner — launch, durable run record, verdict exit codes, the shared-config write-watch, and idle cost

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Adds one new section, `## Detached gate runner`, to `SPECIFICATION/contracts.md`, placed immediately after §"Delegated pre-push gate", plus four scenarios in `SPECIFICATION/scenarios.md`. The section states the operator-facing contract of the detached gate runner this repository already ships as a worktree-pack member (`livespec_dev_tooling/worktree_pack/gate-run.sh`, materialized as `dev-tooling/gate-run.sh`, driven by the pack's `gate-start` / `gate-wait` / `gate-status` / `gate-list` recipes): detached launch, the durable run record under the primary checkout's `tmp/gate-runs/`, the five derived terminal states, the exit-code contract (the gate's own code passed through; `75` for `DIED_WITHOUT_VERDICT`), the restartable waiter and its five-second return bound, the shared `.git/config` write-watch (`config-writes.log` with writer attribution, `core_before` / `core_after`, the `CORE_BARE_FLIP` marker surfaced by `gate-status`), and an idle-cost requirement that leaves the observation mechanism unprescribed. Every bullet but one documents behaviour the shipped runner already has and its tests already prove; the Idle cost bullet (and the fourth scenario) is spec-first and is owed by work-item `livespec-dev-tooling-ycahud`.

### Motivation

Work-item `livespec-dev-tooling-ycahud` (the gate runner's 0.2 s config-write watcher and 5 s wait loop fork on every tick, measured at several hundred forks per second across 25 live detached runs on the dev host on 2026-10-14) was refused by the factory's Definition-of-Done gate (Fabro run `01M4W9ZWR4G9S26WNDWFZD75P4`): its `References: CLI surface` heading does not state the gate-runner behaviour its four Definition-of-Done bullets name, and a full search of `SPECIFICATION/` finds no H2, and no `## Scenario` in `scenarios.md`, that does. The gate's remedy was to add an H2 to the governed spec specifying that surface and re-point the item's `References:` line at it. The runner has shipped since work-item `livespec-dev-tooling-yilyxr.7`, with the durable run store from `livespec-dev-tooling-trfzkw` and the write-watch from `livespec-p32m6d`, and its behaviour is documented today only in the script header and `.ai/gate-runtime-vs-harness-patience.md` — agent-facing guidance, not the ratified spec. This proposal states that behaviour normatively so the item can be graded against it. It follows the route the maintainer chose on 2026-10-11 for the delegated pre-push gate (`delegated-pre-push-gate`, ratified v070): state what this repository's own shipped tooling does, at the level an operator and the factory's grader need. The clause is written so that ycahud's four assertions are derivable from it without prescribing the polling implementation: the tamper-detection guarantee (a config write during a live gate is recorded with writer attribution and the marker is surfaced) and the exit-code contract are required outright, while the mechanism is left to the implementer so the idle wait may cost about zero forks.

### Proposed Changes

Insert the following section into `SPECIFICATION/contracts.md` immediately before the line `## Composite Actions wire contract`, so it follows §"Delegated pre-push gate" and the two gate contracts sit together:

> ## Detached gate runner
>
> The worktree-discipline pack ships a detached gate runner, `gate-run.sh` (the wheel-carried `CANONICAL_GATE_RUN_BODY`, materialized beside the pack's other members at `dev-tooling/gate-run.sh`), driven by the pack's `gate-start`, `gate-wait`, `gate-status` and `gate-list` recipes. It exists because a gate command — the commit or push aggregate, `just check` — can outlast the patience of the harness that invoked it, and a harness kill leaves no exit code, no output and no verdict, which is indistinguishable from a refusal. The runner decouples the gate's runtime from the caller's patience without weakening the gate: the same command runs with the same hooks over the same targets, the gate's own exit code is the verdict, and the runner only transports it. This section is the operator-facing contract of that runner as this repository ships it.
>
> - **Launch.** `gate-start -- <command> [<arg>...]` runs the command in its own session, detached from the caller's process group so that a kill of the caller cannot reach the gate, mints a run id, prints that id on stdout, and returns promptly. It MUST NOT return success for a gate whose process never started. Before launching, it MUST materialize the worktree-discipline pack through `just install-worktree-pack` when the checkout lacks it, so a forgotten bootstrap fails fast rather than deep inside the aggregate.
> - **Run record.** Every run has a directory under the PRIMARY checkout's `tmp/gate-runs/<run-id>/`, resolved from the shared git directory so that every worktree of a repository resolves the same store and a run's record outlives the worktree that started it. The record MUST carry at minimum the command line, the worktree the gate ran in, `started_at`, the gate's `pid` (written by the gate's own process as its first act), its streamed `output.log`, and `exit_code`. `exit_code` MUST be written only when the gate has run to completion, atomically, and last; its presence is the sole marker that a verdict exists. `tmp/` is gitignored: run records are host-local evidence and MUST NOT be committed.
> - **Terminal states.** A run's state is derived from its record alone. An `exit_code` of `0` is `PASSED`; an `exit_code` from `1` to `127` is `FAILED`, a real verdict carrying the gate's own exit code; an `exit_code` of `128` or above is `DIED_WITHOUT_VERDICT`, a death by signal; no `exit_code` with a live `pid` is `RUNNING`; no `exit_code` and no live `pid` is `DIED_WITHOUT_VERDICT`. A run that did not finish MUST NOT read as a pass on any surface.
> - **Verdict exit codes.** `gate-wait <run-id>` blocks until the run leaves `RUNNING`, prints the run's status, and MUST exit with the gate's own exit code for a run that finished — `0` for `PASSED`, the gate's code for `FAILED` — and with `75` (`EX_TEMPFAIL`) for `DIED_WITHOUT_VERDICT`. `75` is distinct from both a pass and every gate failure code, so a run that did not finish can be mistaken for neither. `gate-status [<run-id>]` reports the same state with the same exit code without blocking, defaulting to the latest run; it also reports how many check targets the captured output evidences and warns when a completed run evidences none. An unknown run id exits `64`; a runner that cannot launch the gate exits `70`.
> - **Waiter independence.** The waiter is separate from the gate and restartable: killing a `gate-wait` does not touch the gate, and re-issuing `gate-wait` for the same run id yields the same verdict. `gate-wait` MUST return within five seconds of the run's `exit_code` appearing.
> - **Shared-config write-watch.** Around every gate the runner digests the primary checkout's shared `.git/config` `[core]` section before the gate starts (`core_before`) and after it finishes (`core_after`). While the gate is alive the runner observes that config and its lockfile, with the observation baseline sampled before the gate is launched so a writer scheduled ahead of the observer cannot escape detection. A write that changes the config or makes its lockfile appear MUST be recorded in the run's `config-writes.log` with the time, the current `core.bare` value, and writer attribution as far as `/proc` allows: the gate's descendant process tree and every process holding the config or its lock open. When `core_before` and `core_after` differ the runner MUST write a `CORE_BARE_FLIP` marker into the run record, carrying both digests and the attribution window, and `gate-status` MUST print that marker beside the verdict under every state. The watch is an observer only: it MUST NOT alter the gate's exit code or block the gate, a flip is not a verdict, and a failure of the watch MUST NOT be the reason a gate does not report.
> - **Idle cost.** How the runner observes the config and how the waiter waits are not prescribed — file events, a back-off, or a periodic probe are all conforming — but the cost of doing nothing is: while a gate is alive and neither the shared config nor its lockfile changes, and while a `gate-wait` is blocked on a run whose state is not changing, the runner MUST spawn no process per observation, so that an idle multi-hour run costs about zero forks per second. Writer attribution, the marker, and the exit-code contract above hold unchanged under any conforming mechanism.

Append the following scenarios to `SPECIFICATION/scenarios.md`:

> ## Scenario: a detached gate outlives the caller that launched it and reports its own exit code
>
> Given a checkout carrying the worktree-discipline pack
>
> When `gate-start` launches a gate command that exits non-zero after the launching shell has returned
>
> And `gate-wait` is issued for the printed run id
>
> Then the run record MUST carry an `exit_code` equal to the gate command's exit code
>
> And `gate-wait` MUST exit with that same code
>
> ## Scenario: a detached gate whose process dies without a verdict reports DIED_WITHOUT_VERDICT and exits 75
>
> Given a detached gate run whose record carries a `pid` and no `exit_code`
>
> And the process named by that `pid` is no longer alive
>
> When `gate-wait` or `gate-status` is issued for that run
>
> Then the reported state MUST be `DIED_WITHOUT_VERDICT`
>
> And the exit code MUST be `75`
>
> And the run MUST NOT be reported as passed
>
> ## Scenario: a shared-config write during a detached gate is recorded with writer attribution and marks the run
>
> Given a detached gate run launched from a linked worktree
>
> When a process descended from the gate rewrites the primary checkout's shared `.git/config` `[core]` section while the gate is alive
>
> Then the run's `config-writes.log` MUST record the write and name the writing process
>
> And the run record MUST carry a `CORE_BARE_FLIP` marker
>
> And `gate-status` MUST print the marker while still exiting with the gate's own exit code
>
> ## Scenario: an idle detached gate run and an idle waiter spawn no per-tick process
>
> Given a detached gate run whose command is alive
>
> And neither the shared `.git/config` nor its lockfile changes
>
> And a `gate-wait` blocked on that run
>
> When the run stays in that state across an observation window
>
> Then the runner MUST spawn no child process on any observation of the config
>
> And the waiter MUST spawn no child process on any poll of the run's state
>
> And `gate-wait` MUST still return within five seconds of the run's `exit_code` appearing

Co-edit `tests/heading-coverage.json` in the revise pass: add one entry for the new `contracts.md` heading `## Detached gate runner` and one per new `scenarios.md` heading. The Launch, Run record, Terminal states, Verdict exit codes, Waiter independence and Shared-config write-watch bullets, and the first three scenarios, are already proven by `tests/livespec_dev_tooling/worktree_pack/test_gate_run.py`; the Idle cost bullet and the fourth scenario are spec-first and their rows MUST be `TODO` entries whose `reason` names work-item `livespec-dev-tooling-ycahud` as the implementing item (with the debt register regenerated, never hand-edited).

