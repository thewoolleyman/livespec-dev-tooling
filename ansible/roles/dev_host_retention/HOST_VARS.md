# `dev_host_retention` — per-host values for the inventory's `host_vars`

The dev host's standing disk retention: a oneshot unit that removes dangling
docker images, prunes the uv cache and removes aged TERMINAL gate runs under
each governed checkout's `tmp/gate-runs`, armed by a daily systemd timer.

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
- the uv cache is pruned, and a path the prune cannot remove is LOGGED and the
  run continues — it never aborts;
- a gate run under a governed checkout's `tmp/gate-runs` is removed only when
  it is TERMINAL and older than the retention period; a run whose recorded
  process is alive stays, whatever its age;
- each run logs what it removed and the filesystem's free space before and
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
| `dev_host_retention_days` | `7` | **THE RETENTION PERIOD**, in whole days: how long a terminal gate run's evidence survives, anchored on the run's own `started_at` |
| `dev_host_retention_user` | `root` | the login the retention runs as; see below, it is the one value the dev host must set |
| `dev_host_retention_checkout_roots` | `[/data/projects]` | the directories the governed checkouts sit directly inside; the sweep descends one level and takes every entry carrying a `.git` |
| `dev_host_retention_filesystem` | `/` | the filesystem whose free space each run reports before and after |
| `dev_host_retention_bin` | `/usr/local/sbin/livespec-dev-host-retention` | where the retention script is installed |
| `dev_host_retention_unit_dir` | `/etc/systemd/system` | where the two units are installed |
| `dev_host_retention_service` | `livespec-dev-host-retention.service` | the oneshot unit the timer triggers |
| `dev_host_retention_timer` | `livespec-dev-host-retention.timer` | the timer the converge enables and starts |
| `dev_host_retention_on_calendar` | `daily` | the cadence; the ratified section states a daily floor |
| `dev_host_retention_randomized_delay_sec` | `30m` | jitter, so the reclaim does not land in the same second as every other daily unit |
| `dev_host_retention_timeout_start_sec` | `30min` | bounds ONE run; the first run after this role lands walks the whole gate-run backlog |

**Why `dev_host_retention_user` is the one value a host must set.** Two of the
three legs are per-user: `uv cache prune` prunes the cache of the user it runs
as, and the docker leg needs that user's access to the daemon socket. A root
run on the dev host would prune root's empty cache and leave the 52G one that
was actually measured. The default is `root` because it is the only value that
is right for a host nobody has set this on.

Linked worktrees need no entry of their own: a worktree's gate runs are written
to its PRIMARY checkout's store, which is why a run outlives the worktree that
started it.

```yaml
# vps — the maintainer's dev host, where the checkouts and the uv cache are the
# `ubuntu` login's (the same login `codex_config_user` and `fabro_server_host_user`
# name).
dev_host_retention_user: ubuntu
```

## Operator procedure

The converge is the whole procedure, and it restarts nothing on the host:

```bash
just ansible-drift ansible/dev-host.yml --tags dev_host_retention
just ansible-apply ansible/dev-host.yml --tags dev_host_retention
```

To read what the retention has reclaimed, and when it next fires:

```bash
systemctl list-timers livespec-dev-host-retention.timer
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
