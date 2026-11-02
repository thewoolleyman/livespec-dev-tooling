# `dev_host_retention` — per-host values for the inventory's `host_vars`

The dev host's standing disk retention: a root-run oneshot that removes
dangling docker images, restores the retention user's uv-cache ownership before
pruning as that user, and reclaims aged gate-run, Claude Code and pytest
scratch. A second timer checks root and `/tmp` every 15 minutes and alerts the
host's `claude_ntfy_topic` before either fills.

**Why it exists.** Measured 2026-10-21 for coordinator R510: `/` at 94% — 637G
of 678G, 39.4G free — with no standing retention of any kind. The reclaimable
consumers were `~/.cache/uv` at 52G, the docker store at 21G (7.8G of it
dangling sandbox images), and `tmp/gate-runs` at 1.1G over 4935 run directories
in four governed checkouts, with no retention period defined anywhere. The only
control was a human noticing (work-item `livespec-dev-tooling-fj6dm5`).

**What one run reclaims, and what it leaves.** Governed by
`SPECIFICATION/non-functional-requirements.md` §"Dev host disk retention":

- dangling docker images go; every tagged image and every image a container
  uses stays;
- root restores every path in the retention user's uv cache to that user's
  ownership, then the retention user prunes it; a path the prune cannot remove
  is LOGGED and the run continues — it never aborts;
- a gate run under a governed checkout's `tmp/gate-runs` is removed only when
  it is TERMINAL and older than the retention period; a run whose recorded
  process is alive stays, whatever its age;
- old `/tmp/claude-<uid>/<project>/<session-id>` directories go only when no
  process carries their session id in `CLAUDE_CODE_SESSION_ID`; old pytest base
  temp entries go; a live session always stays;
- bulk dumps are capped oldest-first, but only under a root-filesystem
  directory: the role refuses a tmpfs location;
- each run logs what it removed and the free space of `/` and `/tmp` before and
  after.

**Cargo build targets are deliberately out of scope.** The two large ones
measured on 2026-10-21 (`/data/projects/fabro/target` at 129G and the shared
`~/.worktrees/fabro/factory-wave-c/target` at 122G) belong to the fabro
repository's owner, whose retention rule governs them. A sweep here would
delete a live shared `CARGO_TARGET_DIR` out from under a running build.

**Why the terminal-state predicate is borrowed and not re-derived.**
`gate-run.sh`'s `derive_state` is documented as "the single source of truth for
every verdict word", and `RUNNING` is its only non-terminal state: no
`exit_code`, a `pid` file, and `kill -0` against it succeeding. A run that
never published a pid is terminal, because no verdict is coming. So the script
asks each checkout's own installed `dev-tooling/gate-run.sh list` once per
checkout rather than carrying a second copy of that rule, whose drift would
show up as deleting the evidence of a gate that is still running. A checkout
with no installed runner is SKIPPED and says so.

## The variables

| variable | default | what it is |
| --- | --- | --- |
| `dev_host_retention_gate_run_days` | `7` | **THE GATE-RUN RETENTION PERIOD**, in whole days: how long a terminal gate run's evidence survives, anchored on the run's own `started_at` |
| `dev_host_retention_scratch_retention_hours` | `6` | how long Claude Code and pytest scratch must be untouched before removal |
| `dev_host_retention_root_threshold_percent` | `85` | root-filesystem used-share alert threshold |
| `dev_host_retention_tmp_threshold_percent` | `75` | `/tmp` used-share alert threshold |
| `dev_host_retention_bulk_dump_dir` | `/var/tmp/livespec-dumps` | dump directory, required to resolve onto the root filesystem and never tmpfs |
| `dev_host_retention_bulk_dump_cap_bytes` | `21474836480` | 20 G (20 GiB) bulk-dump cap; the oldest files go first |
| `dev_host_retention_capacity_repeat_interval_seconds` | `3600` | one-hour minimum interval between repeated capacity notifications per filesystem |
| `dev_host_retention_user` | `root` | the login the retention runs as; see below, it is the one value the dev host must set |
| `dev_host_retention_uv_bin` | `/usr/bin/uv` | absolute path to the uv executable the retention invokes while pruning that user's cache |
| `dev_host_retention_uv_installs_dir` | `/home/<user>/.local/share/mise/installs/uv` | read only to list the installed mise uv versions when the converge refuses a missing `dev_host_retention_uv_bin` |
| `dev_host_retention_checkout_roots` | `[/data/projects]` | the directories the governed checkouts sit directly inside; the sweep descends one level and takes every entry carrying a `.git` |
| `dev_host_retention_filesystem` | `/` | the filesystem whose free space each run reports before and after |
| `dev_host_retention_bin` | `/usr/local/sbin/livespec-dev-host-retention` | where the retention script is installed |
| `dev_host_retention_unit_dir` | `/etc/systemd/system` | where the two units are installed |
| `dev_host_retention_service` | `livespec-dev-host-retention.service` | the oneshot unit the timer triggers |
| `dev_host_retention_timer` | `livespec-dev-host-retention.timer` | the timer the converge enables and starts |
| `dev_host_retention_on_calendar` | `daily` | the cadence; the ratified section states a daily floor |
| `dev_host_retention_randomized_delay_sec` | `30m` | jitter, so the reclaim does not land in the same second as every other daily unit |
| `dev_host_retention_timeout_start_sec` | `30min` | bounds ONE run; the first run after this role lands walks the whole gate-run backlog |

**Why `dev_host_retention_user` is the one value a host must set.** It is the
cache owner: root restores this user's ownership below `~/.cache/uv`, then runs
`uv cache prune` as this user. A root prune would leave the measured user's
cache behind. The default is `root` because it is the only value that is right
for a host nobody has set this on.

**Why `dev_host_retention_uv_bin` is an absolute path.** The systemd unit runs
as root, whose PATH does not include a login's mise shims. The unit passes this
configured executable to the script, which sets the retention user's HOME when
it invokes a non-root user's uv. Point it at a concrete, version-pinned binary,
never a mise shim: run from the unit, with cwd `/` and no project configuration,
the shim fails with `No version is set for shim: uv`, so the prune never runs
(measured on the dev host 2026-11-02).

The converge FAILS when the configured path is missing or not executable, and
the failure names the installed mise uv versions. A version-pinned install is
removed by an uninstall, and the script on its own would only log that and
carry on, which on an unattended timer nobody reads.

Linked worktrees need no entry of their own: a worktree's gate runs are written
to its PRIMARY checkout's store, which is why a run outlives the worktree that
started it.

```yaml
# vps — the maintainer's dev host, where the checkouts and the uv cache are the
# `ubuntu` login's (the same login `codex_config_user` and `fabro_server_host_user`
# name).
dev_host_retention_user: ubuntu
dev_host_retention_uv_bin: /home/ubuntu/.local/share/mise/installs/uv/0.11.10/uv-x86_64-unknown-linux-musl/uv
```

## Operator procedure

The converge is the whole procedure, and it restarts nothing on the host:

```bash
just ansible-drift ansible/dev-host.yml --tags dev_host_retention
just ansible-apply ansible/dev-host.yml --tags dev_host_retention
```

To read what the retention has reclaimed, and when it next fires:

```bash
systemctl list-timers livespec-dev-host-retention.timer livespec-dev-host-capacity-check.timer
journalctl -u livespec-dev-host-retention.service --since -2d
```

Silence is not success: one run logs its retention period, the free space
before and after, one line per leg, and one summary line per governed checkout.
A run that reports `removed 0 gate runs` on every checkout and no change in
free space has nothing left to reclaim; a run that logs `uv cache prune could
not remove <path>` has reclaimed everything else and named what it could not.

To run one retention by hand — the same thing the timer does:

```bash
sudo -u ubuntu /usr/local/sbin/livespec-dev-host-retention
```

## Rollback

```bash
sudo systemctl disable --now livespec-dev-host-retention.timer
sudo rm -f /etc/systemd/system/livespec-dev-host-retention.{service,timer} \
           /usr/local/sbin/livespec-dev-host-retention
sudo systemctl daemon-reload
```

Nothing else on the host changes: the retention holds no state of its own.

## Expiry

This control is retired when the consumers it sweeps stop accumulating without
bound — when `gate-run.sh` reaps its own store, and when the sandbox image
lifecycle leaves no dangling layers behind. Until then the dev host has no
other standing reclamation: the `disk_guard` role is `hp-xubuntu`'s low-water
backstop and is not included by `ansible/dev-host.yml`.
