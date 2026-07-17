# Fleet Plan Lifecycle Enforcement Handoff

**Thread:** `plan/fleet-plan-lifecycle-enforcement/`
**Ledger anchor:** epic `livespec-dev-tooling-scsj5e`

## Why This Thread Exists

The `rop-sweep-library-checks` work was treated as complete after the
implementation PR merged, but the planning lifecycle was not completed until a
later correction archived the plan thread. A repo-local lint would only prevent
that mistake in `livespec-dev-tooling`; the correct prevention is a
fleet-wide rollout through the shared enforcement package and the existing
release/pin-bump machinery.

This thread owns the fleet rollout. Do not close `livespec-dev-tooling-scsj5e`
until the shared check is released, every manifest fleet member is bumped or has
a filed blocker, and this directory is archived with the epic.

## Ledger Map

Parent epic:

- `livespec-dev-tooling-scsj5e` - `[epic] Fleet-wide plan lifecycle enforcement and rollout`

Child slices:

- `livespec-dev-tooling-i5barz` - Implement canonical plan-lifecycle enforcement in livespec-dev-tooling
- `livespec-dev-tooling-w2elyx` - Dogfood and repair current livespec-dev-tooling plan-thread drift
- `livespec-dev-tooling-qt44u2` - Release dev-tooling and fan out the plan-lifecycle check to the fleet
- `livespec-dev-tooling-zkh4pk` - Verify fleet-wide plan-lifecycle enforcement after rollout

## Current Evidence

- `plan/archive/rop-sweep-library-checks/handoff.md` now records the original
  incident and closure evidence.
- The shared canonical check set is derived from
  `livespec_dev_tooling/checks/*.py`, so a new module here becomes a fleet
  canonical slug once released and consumed.
- `plan/work-item-state-machine/handoff.md` is still active and cites
  `livespec-dev-tooling-l2sm`, but `list-work-items` reports that epic as
  `done`. That is an active/archive parity violation and must be repaired as
  part of `livespec-dev-tooling-w2elyx`.
- The aborted code-first attempt was removed from this branch. The next
  implementation must happen under `livespec-dev-tooling-i5barz`.

## Required Rollout Shape

1. Implement shared canonical enforcement in `livespec-dev-tooling`.
   The design must cover static lifecycle facts and ledger-backed parity:
   active handoffs need concrete `Ledger anchor:` lines, placeholder anchors
   fail, archived handoffs are ignored, and active threads must not point at
   closed epics. If fleet CI cannot always access ledger credentials, split the
   design into a hard static canonical check plus a credential-aware companion
   or conformance row. Do not weaken the invariant silently.
2. Dogfood the check in this repo and repair current drift.
   At minimum, resolve the active `plan/work-item-state-machine/` versus
   closed `livespec-dev-tooling-l2sm` mismatch.
3. Release the dev-tooling version that carries the check and fan out pin bumps
   to every fleet member declared in the manifest.
4. Verify every fleet member either runs/gates the new canonical slug green or
   has a specific blocker filed under this epic's rollout evidence.

## Next Action

Dispatch the first child through the factory path:

```text
livespec-orchestrator-beads-fabro:drive impl:livespec-dev-tooling-i5barz
```

Do not use the in-session implementation operation for this work. The
implementation slice is ledger-backed and factory-eligible; the Dispatcher or
`drive impl:livespec-dev-tooling-i5barz` is the execution path.

## Closure Rule

When the rollout is complete, close `livespec-dev-tooling-scsj5e` in the ledger
and move this directory with:

```text
git mv plan/fleet-plan-lifecycle-enforcement plan/archive/fleet-plan-lifecycle-enforcement
```
