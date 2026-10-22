---
topic: dev-host-disk-retention
author: claude-opus-5-5
created_at: 2026-10-22T00:29:32Z
---

## Proposal: dev host disk retention

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a non-functional-requirements.md H2 "Dev host disk retention" requiring a daily, Ansible-provisioned retention on the dev host that removes dangling docker images (leaving tagged and in-use ones), prunes the uv cache and continues past unremovable paths, removes only terminal gate runs older than a committed retention period (never a live one), and logs what it removed with free space before and after. Add one scenario for the gate-run leg.

### Motivation

Measured 2026-10-21 for coordinator R510 (work-item livespec-dev-tooling-fj6dm5): the dev host's root filesystem was at 94% (39.4G free). The reclaimable consumers had no standing control. `~/.cache/uv` was 52G, and `uv cache prune` reclaimed ~6G then ABORTED on a path under `archive-v0` it could not remove, so an unattended prune does not complete today. Docker held 7.8G of dangling sandbox images. `tmp/gate-runs` held 4935 run directories across four repositories with no retention period at all. The hp factory host already has this class of control (the `disk_guard` role in `ansible/fabro-hosts.yml`), but the dev host play includes none. No clause covers dev host retention, so the item's Definition of Done has no governing heading (dod-preflight refused it on exactly that, 2026-10-22). Placement: this is the repository's own infrastructure, so it belongs in non-functional-requirements.md beside §"Host provisioning tree", whose rule that an inventory host converges only through a committed play this clause reuses instead of a hand-installed user timer. A gate run counts as terminal by the same two markers `gate-run.sh` already uses for its verdict states (a recorded exit code, or a dead recorded process), so retention can never remove a run that a waiter may still report.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, insert this new section immediately after §"Host provisioning tree":

## Dev host disk retention

**Scope.** This section states the standing disk retention on the maintainer's dev host, the host the `ansible/dev-host.yml` play selects through `dev_hosts`. That host is also the Ansible control node, and its root filesystem holds every governed checkout, their `tmp/gate-runs` directories, the uv cache and the docker store its factory and gate work leave behind.

**Provisioned, not hand-installed.** The retention MUST run at least daily from a systemd timer that a role included by `ansible/dev-host.yml` installs, as §"Host provisioning tree" requires for every service on an inventory host. Its script MUST be committed in that role, and its retention period MUST be a role variable documented in the role's `HOST_VARS.md`.

**What one run reclaims, and what it leaves.**

- It MUST remove dangling docker images and MUST leave every tagged image and every image a container uses in place.
- It MUST prune the uv cache. When the prune cannot remove a path, the run MUST log that path and continue with its remaining steps, never abort.
- It MUST remove a gate-run directory under a governed checkout's `tmp/gate-runs` only when that run is TERMINAL — it carries a recorded exit code, or its recorded process is no longer alive — and is older than the retention period. It MUST leave a gate run whose recorded process is alive in place, whatever its age.
- Each run MUST log what it removed and the root filesystem's free space before and after.

Cargo build targets are deliberately outside this section: the large ones belong to the fabro repository's owner, whose retention rule governs them.

In `SPECIFICATION/scenarios.md`, append:

## Scenario: dev host retention leaves an in-flight gate run and removes an aged terminal one

Given a governed checkout on the dev host whose `tmp/gate-runs` holds a terminal gate run older than the retention period

And a gate run older than the retention period whose recorded process is still alive

When one run of the dev host retention script completes

Then the terminal gate run's directory MUST be removed

And the live gate run's directory MUST remain in place

And the run's log MUST name the removed directory and the root filesystem's free space before and after

The new `## Dev host disk retention` heading and the new scenario heading each need a `tests/heading-coverage.json` entry (test `TODO`, work_item livespec-dev-tooling-fj6dm5) and a regenerated `tests/heading-coverage-debt.json` row, co-edited in the revise.
