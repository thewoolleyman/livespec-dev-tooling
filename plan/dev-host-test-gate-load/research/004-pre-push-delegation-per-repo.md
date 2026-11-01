# 004 — Pre-push delegation per repository (assertion 5)

Recorded 2026-11-02 by seat dev-host-test-gate-load. Note 002 §6 left the console and runtime verification owed, because
neither repository had a gate-runner push on record then. This note closes that gap and names, per repository, the pre-push
members that still run on the dev host. It is evidence for the plan-level proof of assertion 5. It is not that proof: the
proof replays against the released build when the plan's carriers have shipped.

## Method

- **Source.** Each repository's `tmp/gate-runs/*/` on the dev host (vmi3006760), read 2026-11-01 ~23:40Z. A run is a push
  when its `command` file contains `git push`. Its venue is read from `output.log`.
- **Delegation evidence.** A run's `output.log` carries `delegated gate passed`, or a delegated refusal, from the gate client.
- **Host-run members.** When the Job skips a member that reads an authorization held outside the tree, the gate client
  prints `:: gate: NOT running <members> here - each reads an authorization held outside the tree and this Job is handed
  none; the pushing host runs it against this same tree`. The counts below are of that line, across every recorded run.
- **Blind spot.** As in note 002, only pushes started through the gate runner leave a record. A bare `git push` from a shell
  does not. Factory runs push from their cluster sandbox, so they are not dev-host load and are not counted here.

## Console and runtime

| repo | `delegated_gate` on origin | gate-runner pushes on record | venue |
|---|---|---|---|
| livespec-console-beads-fabro | `true` (pyproject.toml line 66) | 1 finished push, 2026-10-30 | `delegated gate passed` at 21:25:46Z |
| livespec-runtime | `true` (pyproject.toml line 186) | 1 finished push, 2026-10-28 | `delegated gate passed` at 11:59:39Z |

- Neither repository has a gate-runner push after 2026-10-31.
- The other console runs whose `command` names `git push` are commits. Two are 10-30 revise commits that never wrote an exit code.
- Neither repository shows a push whose aggregate ran on the dev host.

## Members that still run on the dev host, per repository

| repo | `check-branch-protection-alignment` | `check-no-workflow-edits` | runs seen skipping them in the Job |
|---|---|---|---|
| livespec-dev-tooling | dev host | dev host | 98 (both) |
| livespec-orchestrator-beads-fabro | dev host | dev host | 90 (both), 63 (alignment only) |
| livespec | dev host | dev host | 9 (both), 5 (alignment only) |
| livespec-overseer | dev host | dev host | 19 (both) |
| livespec-runtime | dev host | dev host | 8 (both), 1 (alignment only) |
| livespec-console-beads-fabro | not seen | dev host | 2 (workflow edits only) |

Why they stay on the dev host: each reads an authorization held outside the tree. Alignment reads branch protection through
the forge credential. Workflow edits reads the workflow-edit exemption and its label. The gates Job is handed neither
credential. This is the placement §"Delegated pre-push gate" ratifies, and v108's §"Delegated pre-commit aggregate" and
§"Delegated gate-runner runs" apply it again. Why some runs skipped alignment only was not investigated. Both members run
on the dev host either way.

Both members read state rather than run a test suite. Note 003 measured the whole pre-push class at 0.11 cores, so they are a
small part of the dev-host test and gate load.

## What remains for assertion 5

- Console and runtime are each verified by one delegated push. A post-carrier window should confirm at least one more push
  per repository. The plan-level proof replays that confirmation against the released build.
- Pre-push delegation in any other repository with `delegated_gate = true` is not covered by this note. The proof takes the
  repository set from the fleet manifest at capture time.
