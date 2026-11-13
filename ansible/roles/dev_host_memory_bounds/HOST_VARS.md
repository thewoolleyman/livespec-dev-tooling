# dev_host_memory_bounds — host variables

Keeps the dev host's memory from being exhausted by its RAM-backed `/tmp` and
by uncapped fleet Python. Answers the 2026-11-13 overload of the dev VPS
(rebooted 15:53Z; RAM-backed `/tmp` at 35-38 GiB, Python at 19-26 GiB, Dolt
OOM-killed at 15:32:41Z). The numbers and where each came from are in
`defaults/main.yml`.

## What it installs

| Piece | Where | Takes effect |
| --- | --- | --- |
| `/tmp` cap, `size=8G,nr_inodes=2m` | `/etc/systemd/system/tmp.mount.d/zz-livespec-memory-bounds.conf` | next boot, or the cutover |
| Session scratchpads on disk: `/tmp/claude-<uid>` bind-mounts `/var/tmp/claude-<uid>` | `/etc/systemd/system/tmp-claude\x2d<uid>.mount`, enabled | next boot, or the cutover |
| `TMPDIR=/var/tmp` for every zsh of the login (unless already set) | a marked block in `~<user>/.zshenv` | each new session |
| `factory-dispatch.slice`, MemoryHigh 18G / MemoryMax 20G | `/etc/systemd/user/` | the next launch into it |
| `local-gate.slice`, MemoryHigh 9G / MemoryMax 10G | `/etc/systemd/user/` | the next launch into it |
| reconcile-runs MemoryHigh 4G / MemoryMax 6G, OOMScoreAdjust 500 | `/etc/systemd/system/reconcile-runs.service.d/50-livespec-memory-bounds.conf` | the next timer pass |

A slice bounds only what is launched into it. A session puts a command there
with:

```bash
systemd-run --user --scope --slice=factory-dispatch.slice -- <command>
systemd-run --user --scope --slice=local-gate.slice -- <command>
```

For the dispatcher, each launcher also bounds ITSELF, so one runaway loop
cannot take the whole slice: `systemd-run --user --scope
--slice=factory-dispatch.slice -p MemoryMax=3500M -- <launcher>`. The figure
is the largest measured loop peak (VmHWM 2532M, 2026-11-13) plus room for the
loop's drive and preflight children.

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
is NOT here. That unit belongs to the dolt-server repository and is bounded
there.

## The one setting

| Variable | Default | Meaning |
| --- | --- | --- |
| `dev_host_memory_bounds_state` | `absent` | `present` installs everything above; `absent` removes every file this role wrote. |

The dev hosts group sets `present` in `inventory/group_vars/dev_hosts.yml`.
Every other variable is documented at its default in `defaults/main.yml`.

## Procedure

Run the load guard first. If it reads HOLD, do not apply:

```bash
/var/tmp/vps-load-guard.sh || echo HOLD
```

Then converge. The converge changes nothing that is already running:

```bash
cd ansible
ansible-playbook dev-host.yml --tags dev_host_memory_bounds --check --diff
ansible-playbook dev-host.yml --tags dev_host_memory_bounds
```

## The live cutover

The cutover moves the scratchpads to disk on the running host and caps the
mounted `/tmp`. It is a separate invocation because it mounts over a directory
that live sessions write to:

```bash
ansible-playbook dev-host.yml --tags dev_host_memory_bounds_cutover
```

It runs in this order:

1. It copies `/tmp/claude-<uid>` into `/var/tmp/claude-<uid>`.
2. It starts the bind mount.
3. It deletes the hidden RAM copy, reaching it through a non-recursive bind of
   `/tmp`.
4. It refuses if `/tmp` still holds more than three quarters of the cap.
5. It remounts `/tmp` at the cap and reads both mounts back.

A file that a running process holds OPEN at the moment of the cutover, such as
a background command's output, keeps its RAM inode until that process closes
it. Its later writes are not visible at the path. Take the cutover when no
long background command is running, and tell the seats first. A cutover on a
host where the bind is already live skips steps 1 to 3 and only re-applies the
cap.

## Rollback

Set `dev_host_memory_bounds_state: absent` (or delete the group's line, since
the default is `absent`) and converge. That removes the `/tmp` drop-in, so the
host's earlier `override.conf` applies again at the next mount of `/tmp`. It
also disables and removes the bind mount unit, removes both slices and the
reconcile drop-in, and removes the zshenv block.

A bind that is already mounted stays mounted until the next boot, because
unmounting it would hide the on-disk scratchpads from every running session. To
undo it live, run `sudo umount /tmp/claude-<uid>` at a quiet moment. To undo
the live `/tmp` cap, run
`sudo mount -o remount,size=50%,nr_inodes=100000000 /tmp`.
