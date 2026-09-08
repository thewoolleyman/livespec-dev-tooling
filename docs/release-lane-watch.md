# Release-lane watch — the shared detector and its shim contract

Work-item `livespec-dev-tooling-37p0`, plan `fleet-delivery-lane-visibility`
(owning carrier `livespec-n33rwg.5` in the livespec tenant).

## The gap this closes

Signal 9 answers "how did the LATEST release's gate conclude?" from a one-call
GraphQL screen over the latest release's tag commit. It structurally cannot
answer lane HISTORY — streak length, last-green timestamp, whether the window it
read was truncated — and it cannot see a lane with NO RELEASE OBJECT at all. A
daily readiness canary failing for two weeks is invisible to every other fleet
signal: Signal 1 reads only the workflow named `CI`.

The detector here answers the history question, on a cadence, per lane.

## What ships

- `livespec_dev_tooling/cross_repo/release_lane_watch.py` — `lane_state()` and
  `notice_text()`, LIFTED from `livespec-overseer` (its work-item
  `overseer-hgq4wi.15`), not re-derived. `lane_state` is a pure function of a
  run list: no network, no filesystem. It reports STATE rather than edges,
  carries the absolute last-green timestamp, and reports a failure block that is
  flush against the oldest supplied run as a LOWER BOUND rather than as a count.
  Each of those three properties was earned by a measured failure; the module
  docstring records which.
- `livespec_dev_tooling/cross_repo/release_lane_watch_runner.py` — the caller.
  Talks to the forge through stdlib `urllib` (never `gh`, which is absent on the
  self-hosted runners), uses the WORKFLOW-SCOPED runs endpoint
  (`/repos/{slug}/actions/workflows/{workflow}/runs` — the unscoped form
  silently ignores the workflow and returns every workflow's runs), and exits
  three-valued:

  | exit | meaning |
  | ---- | ------- |
  | `0`  | healthy, or failing below the transient threshold — and SILENT |
  | `1`  | the lane is FAILING — this is the finding |
  | `2`  | CANNOT MEASURE — forge unreachable, unauthorized, or unparsable |

  A watcher that cannot measure must never report healthy, so `2` is never
  collapsed into `0`. Both `1` and `2` red the job; the calling workflow renders
  `::error::` for one and `::warning::` for the other from the exit code, because
  an Actions annotation is a presentation concern of the venue — `print` is
  banned in this tree (T20) and direct writes by `check-no-write-direct`, so the
  module's own diagnostics go to stderr through structlog.

Replay tests drive the detector over RECORDED `thewoolleyman/livespec`
`release-tag.yml` history from 2026-08-09 through 2026-08-21 — a known-red
interval with a known-green boundary on each side, asserted in both directions.

## The shim contract — NO App secrets

A consumer watches its own lanes with a shim that supplies the watched workflow
set. The set is an INPUT and is never hardcoded upstream: the fleet is
non-uniform. Measured across all 14 manifest repos on 2026-09-08, only `livespec`
and `livespec-overseer` ship `release-tag.yml`, `livespec-console-beads-fabro`
ships `release-binary.yml` and no `release-dispatch.yml`, and the four adopters
ship no release workflow at all.

```yaml
# release-lane-watch.yml — consumer shim.
name: Release lane watch

on:
  schedule:
    - cron: '23 6 * * *'   # off the hour; do not share a minute with other canaries
  workflow_dispatch: {}

jobs:
  watch:
    uses: thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-release-lane-watch.yml@vX.Y.Z
    with:
      watched_workflows: '["release-tag.yml", "release-readiness.yml"]'
```

⛔ **The shim does NOT carry `secrets: inherit`.** The watcher reads run history
with the caller's own `github.token` under `actions: read`, so there is no App
token to inherit. Copying the `secrets: inherit` line from the `pin-freshness.yml`
shim is cargo-culting: that surface needs `APP_ID` / `APP_PRIVATE_KEY` because it
OPENS PULL REQUESTS. This one mutates nothing.

The reusable workflow `.github/workflows/reusable-release-lane-watch.yml` is
landed MAINTAINER-SIDE, separately from this branch: a factory branch never
writes under `.github/workflows/`, and `check-no-workflow-edits` refuses such a
branch without a human-set `approval:workflow-edit` label. The branch that added
this document carries the detector, the runner and their tests, and reports the
workflow's unified diff for that landing.

`watched_workflows` is a JSON-array string of workflow FILE NAMES as they appear
under the caller's `.github/workflows/`. Each is watched in its own matrix leg
with `fail-fast: false`, so one failing lane never hides another's verdict.

## Reading the watcher

A red watcher run is the signal, and something must READ it. That reader is
tracked on the owning carrier and is deliberately NOT part of this slice: a
watcher that only reds its own cron job reproduces the very defect this plan
exists to remove, because Signal 1 reads only the workflow named `CI` and Signal
9 reads release lanes, so neither would see it.
