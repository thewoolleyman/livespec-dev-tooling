# dev_host_memory_bounds — host variables

Keeps the dev host's memory from being exhausted by its RAM-backed `/tmp` and
by uncapped fleet Python. Answers the 2026-11-13 overload of the dev VPS
(rebooted 15:53Z; RAM-backed `/tmp` at 35-38 GiB, Python at 19-26 GiB, Dolt
OOM-killed at 15:32:41Z). The numbers and where each came from are in
`defaults/main.yml`.

## What it installs

| Piece | Where | Takes effect |
| --- | --- | --- |
| `/tmp` cap, `size=8G,nr_inodes=2m` | `/etc/systemd/system/tmp.mount.d/zz-livespec-memory-bounds.conf` | next boot, or the live `tmp_cap` step |
| Session scratchpads on disk: `/tmp/claude-<uid>` bind-mounts `/var/tmp/claude-<uid>` | `/etc/systemd/system/tmp-claude\x2d<uid>.mount`, enabled | next planned reboot, or the live `cutover` step |
| `factory-dispatch.slice`, derived from the fleet cap (on the VPS: MemoryHigh 19296M / MemoryMax 21440M) | `/etc/systemd/user/` | the next launch into it |
| the per-loop scope bound, `3500M` | `/etc/livespec/factory-dispatch-loop-memory-max` | the next launch that reads it |
| `local-gate.slice`, MemoryHigh 9G / MemoryMax 10G | `/etc/systemd/user/` | the next launch into it |
| reconcile-runs MemoryHigh 5G / MemoryMax 6G, OOMScoreAdjust 500 | `/etc/systemd/system/reconcile-runs.service.d/50-livespec-memory-bounds.conf` | the next timer pass |

A slice bounds only what is launched into it. A session puts a command there
with:

```bash
systemd-run --user --scope --slice=factory-dispatch.slice -- <command>
systemd-run --user --scope --slice=local-gate.slice -- <command>
```

For the dispatcher, each launcher also bounds ITSELF, so one runaway loop
cannot take the whole slice:

```bash
systemd-run --user --scope --slice=factory-dispatch.slice \
  -p OOMPolicy=continue \
  -p MemoryMax="$(cat /etc/livespec/factory-dispatch-loop-memory-max)" \
  -- <launcher>
```

The figure is the largest measured loop peak (VmHWM 2532M, 2026-11-13) plus
room for the loop's drive and preflight children. `OOMPolicy=continue` is
REQUIRED: systemd 257 defaults both managers to `DefaultOOMPolicy=stop`, so
without it one OOM-killed child (a preflight, a `bd` call) would stop the whole
scope and kill the loop with it, stranding its run.

When a cap is reached, the kernel OOM-kills the largest process inside that
scope or slice, and nothing outside it. A dispatcher loop killed that way
leaves the factory run and its publication intact: the run executes on the
factory server, and its draft publication is a node inside that run. What the
LOOP owns after that is stranded:

- the post-run merge wait and acceptance;
- the item's ledger disposition, which needs a `reconcile-merged --pr <n>` or a
  reconcile-runs pass;
- the long-run preserve request for a run past 330 minutes, which has to be
  taken by hand.

The reconcile-runs timer covers only the orchestrator tenant, and it holds a
succeeded run rather than closing it. The 15:53Z reboot of 2026-11-13 killed
every loop at once and showed exactly this: seven runs finished and published,
and their items sat active with merged PRs until each was reconciled by hand
(legacy-dispatcher-agent, 2026-11-13). That cost is why the per-launcher cap
sits well above the measured peak, not at it.

The launch paths that do so are owned by the code that launches. The dispatcher
loops are launched by the orchestrator's drive path, and the gates by this
repository's gate recipes. This role installs only the slices.

Dolt's protection (`OOMScoreAdjust=-900`, `MemoryMin=4G` on `doltdb.service`)
is NOT here. That unit, and `dolt-backup.service` beside it, belong to the
dolt-server repository, which installs them only on the host that runs the
ledger. So the protection reaches that host and no other.

## Settings

`dev_host_memory_bounds_state` is the switch: `present` installs everything
above, and `absent` (the default) removes every file this role wrote. The dev
hosts group sets `present` in `inventory/group_vars/dev_hosts.yml`.

Every size is a variable, and none of the defaults assumes the dev VPS's RAM,
its lack of swap, or its fleet cap. A host whose numbers differ sets these in
its own `host_vars`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `dev_host_memory_bounds_tmp_size` | `8G` | The `/tmp` tmpfs cap. |
| `dev_host_memory_bounds_tmp_nr_inodes` | `2m` | The `/tmp` inode cap. |
| `dev_host_memory_bounds_dispatch_loop_cap` | `18` | The fleet cap on dispatcher loops on this host. |
| `dev_host_memory_bounds_dispatch_loop_steady_mib` | `800` | One loop's steady RSS, in MiB. |
| `dev_host_memory_bounds_dispatch_loop_peak_mib` | `2560` | One loop's peak RSS (VmHWM), in MiB. |
| `dev_host_memory_bounds_dispatch_concurrent_peaks` | `4` | How many loops may peak at once. |
| `dev_host_memory_bounds_dispatch_memory_max` | derived | `loop_cap x steady + concurrent_peaks x (peak - steady)`, in MiB. |
| `dev_host_memory_bounds_dispatch_memory_high` | derived | 90% of the dispatch MemoryMax. |
| `dev_host_memory_bounds_dispatch_loop_memory_max` | `3500M` | Each launcher's own scope bound: the measured peak plus its children. |
| `dev_host_memory_bounds_gate_memory_high` / `_max` | `9G` / `10G` | The local-gate slice; one full suite at a time. |
| `dev_host_memory_bounds_reconcile_memory_high` / `_max` | `5G` / `6G` | The reconcile-runs bound; the measured peak is 3.7G, and High sits above it because a stalled oneshot blocks later ticks. |
| `dev_host_memory_bounds_memory_swap_max` | `0` | MemorySwapMax for both slices and reconcile-runs. |

The per-loop figures were measured on the dev VPS on 2026-11-13. A new host
should re-measure them (VmRSS and VmHWM of each running `dispatcher.py loop`)
once dispatch runs there.

### Swap

On a host without swap (the dev VPS), MemorySwapMax has no effect. Above a
slice's MemoryHigh, its anonymous memory cannot be reclaimed, so the slice
STALLS; MemoryMax is where processes are killed. On a host WITH swap,
MemoryHigh reclaims to swap first. The default of `0` keeps the slices and
reconcile-runs out of swap, so they behave exactly as they do on the VPS, and a
runaway cannot push the live ledger or the seats into swap. Set it to a size,
or to `infinity`, only as a deliberate choice for that host.

## Procedure

Run the load guard first. If it reads HOLD, do not apply:

```bash
/var/tmp/vps-load-guard.sh || echo HOLD
```

Then converge. The converge changes nothing that is already running: it
writes units and drop-ins, publishes one file and reloads the managers. No
session's environment changes.

```bash
just ansible-drift ansible/dev-host.yml --tags dev_host_memory_bounds,local_gate_slots
just ansible-apply ansible/dev-host.yml --tags dev_host_memory_bounds,local_gate_slots
```

## The two live steps

Each live step is its own invocation, taken at a moment the operator chose.

**Cap the running `/tmp`.** This is safe whenever `/tmp` holds less than three
quarters of the cap. A tmpfs remount changes only its limits: no file moves and
no open file is disturbed.

```bash
just ansible-apply ansible/dev-host.yml --tags dev_host_memory_bounds_tmp_cap
```

**Move the scratchpads to disk on the running host.** The ordinary route is
the next planned reboot: the enabled mount unit takes effect before any session
starts, and nothing has to move. To do it live instead:

```bash
just ansible-apply ansible/dev-host.yml --tags dev_host_memory_bounds_cutover
```

The live step REFUSES while `lsof +D /tmp/claude-<uid>` shows any process
holding a file open there. A writer would keep its RAM inode while readers met
the disk copy, so gate verdicts and background-command output would come back
wrong. On 2026-11-13 there were about 147 such handles, so the live step needs
quiesced seats. When it runs, it mounts the bind first, so every new file lands
on disk. It then copies what the RAM directory held, reaching it through a
non-recursive bind of `/tmp`, and deletes that RAM copy. On a host where the
bind is already live it does nothing.

## No TMPDIR

The role exports no `TMPDIR`. Long-lived daemons that no session shell starts
include the codex daemon (a user service) and the browser bridge. They meet
their clients through sockets in the default temporary directory, so a
seat-only `TMPDIR` would split those rendezvous permanently. The bind moves the
measured consumer, the Claude Code scratchpads, without changing any path.

## Rollback

Set `dev_host_memory_bounds_state: absent` (or delete the group's line, since
the default is `absent`) and converge. That removes the `/tmp` drop-in, so the
host's earlier `override.conf` applies again at the next mount of `/tmp`. It
also disables and removes the bind mount unit, removes both slices and the
reconcile drop-in, and the published per-loop bound.

A bind that is already mounted stays mounted until the next boot, because
unmounting it would hide the on-disk scratchpads from every running session. To
undo it live, run `sudo umount /tmp/claude-<uid>` at a quiet moment. To undo
the live `/tmp` cap, run
`sudo mount -o remount,size=50%,nr_inodes=100000000 /tmp`.

## Claude scratch mover (stopgap until the bind)

Until the next reboot brings up the `/tmp/claude-1000` bind, Claude Code
session scratch stays in the 8G `/tmp` tmpfs. The `livespec-claude-scratch-mover`
timer runs `files/claude_scratch_mover.py` as root every
`dev_host_memory_bounds_scratch_mover_interval` (15min) after the previous pass
ends, at Nice 19 and idle IO. Each pass MOVES, and never deletes, every session
directory that is dead and idle to the same relative path under
`/var/tmp/claude-1000/`, which is exactly where the bind will show it.

- **Dead:** no running process carries the session id in
  `CLAUDE_CODE_SESSION_ID`, and no process references the directory through its
  cwd, an open file, a memory map, its command line or its environment. The
  pass reads `/proc` again just before each move.
- **Idle:** nothing under it was modified within
  `dev_host_memory_bounds_scratch_mover_min_age_seconds` (2h).
- **Session id anywhere:** a session is held when its id appears anywhere in
  a process's cwd, fds, maps, command line or environment.
- **Staged, then copied:** the directory is first renamed to `.<id>.moving`
  in the same `/tmp` directory (atomic), `/proc` is read again, and it is put
  back if anything references it. Only then is it copied to disk. A failed copy
  puts it back, and a staging directory a crashed pass left is restored first.
- **Never follows a symlink (it runs as root):** the RAM root, the disk root and
  the source project directory must be real directories owned by the RAM root's
  owner, and the destination project directory a real directory, or the move or
  pass is refused. A destination project directory takes the source's owner
  and mode. The role also gives any project directory already on disk to the
  scratchpad login (mode 0700).
- **Never overwrites:** an existing destination fails that move, leaves the
  source, and marks the pass failed.
- **Log:** every decision is one JSON line in
  `journalctl -u livespec-claude-scratch-mover.service`.
- **Kill switch:** `sudo touch /etc/livespec/claude-scratch-mover.disabled`
  stops every pass at once without a converge; delete the file to resume. To
  withdraw the timer, set `dev_host_memory_bounds_scratch_mover_enabled: false`
  and converge.
- **Retires itself:** once `/tmp/claude-1000` is a mount point the pass moves
  nothing. Remove the mover from the role after the bind lands.
