# `sandbox_storage` — per-host values for the inventory's `host_vars`

A Fabro factory host's SECOND disk: a swap partition the size of the host's
RAM and an ext4 filesystem carrying the docker and containerd stores, with the
two bind mounts that put those stores where the daemons look and the systemd
drop-ins that refuse to start either daemon on an empty target.

**Why it exists.** Measured on `hp-xubuntu` on 2026-10-12 under factory load
(work-item `livespec-dev-tooling-smrzsj`): one SATA SSD (`sda`) carried `/`,
the 8 GB `/swap.img` (100% full), `/data`, and — by two hand-written fstab bind
lines no role managed — `/var/lib/docker` and `/var/lib/containerd`. The
second SATA SSD (`sdc`, Fanxiang S101 4 TB) sat idle under a re-downloadable
Steam library. This role declares that disk's layout, gives the host swap equal
to its RAM, and brings the two bind lines under management.

**Copying a store by hand.** Any copy of these stores outside this role's
procedure — a manual migration, a recovery, a move to another disk or host —
follows [`.ai/bulk-data-copies.md`](../../../.ai/bulk-data-copies.md):
`fpsync` (installed by the `fpart` role), with the file count and layout
measured first and checksums only after the copy. The copy helper below is not
yet fpsync-based; that switch is a separate follow-up.

## The variables

| variable | default | what it is |
| --- | --- | --- |
| `sandbox_storage_enabled` | `true` | read by `ansible/fabro-hosts.yml`, not the role: `false` skips the role on a host with no second disk (gmktec-xubuntu, one NVMe disk), with the reason beside it in host_vars |
| `sandbox_storage_device` | `""` (**required**) | the disk, by its `/dev/disk/by-id/` path — model and serial, never `/dev/sdX` |
| `sandbox_storage_swap_label` | `sandbox-swap` | the swap partition's label (GPT partition 1); at most 16 bytes |
| `sandbox_storage_fs_label` | `sandbox-stores` | the filesystem's label (GPT partition 2, the rest of the disk); at most 16 bytes, ext4's limit |
| `sandbox_storage_swap_size` | `32GiB` | the swap partition's size, an sgdisk suffix; size it to the host's RAM |
| `sandbox_storage_swap_priority` | `10` | the swap's priority, above the swap file's default `-1`; passed to `swapon` explicitly and written to the fstab line |
| `sandbox_storage_mount` | `/srv/sandbox-storage` | where the filesystem is mounted |
| `sandbox_storage_containerd_src` | `<mount>/containerd` | the containerd store directory on the disk |
| `sandbox_storage_docker_src` | `<mount>/docker` | the docker root directory on the disk |
| `sandbox_storage_containerd_dir` | `/var/lib/containerd` | containerd's bind target |
| `sandbox_storage_docker_dir` | `/var/lib/docker` | docker's bind target |
| `sandbox_storage_dropin_name` | `10-requires-sandbox-storage.conf` | the `RequiresMountsFor=` drop-in each daemon gets |
| `sandbox_storage_preseed_bwlimit` | `40m` | the preseed's transfer cap (`rsync --bwlimit`; caps file-data throughput, not the metadata scan); `ionice -c3` is a no-op under `mq-deadline`, so this is the real control |
| `sandbox_storage_sources_record` | `.sandbox-storage-sources.json` | file on the new disk recording, per store, the verified old source, its filesystem UUID and subtree, and whether the copy completed; written before the cutover stops anything, updated per store, atomically and under the copy lock, as each cutover copy completes; an interrupted cutover resumes from it (it takes precedence over fstab) and never recopies a store it marks copied |
| `sandbox_storage_fstab_snapshot` | `/etc/fstab.pre-sandbox-storage` | the one named pre-cutover fstab copy the rollback restores |
| `sandbox_storage_lock` | `.sandbox-storage.lock` | the flock on the new disk that every copy onto it (preseed and cutover) takes |
| `sandbox_storage_copy_helper` | `/usr/local/libexec/sandbox-storage-copy` | the one program every copy runs through: holds the lock across the fail-closed record read, the copy and the cutover's `copied: true` publication |
| `sandbox_storage_allow_format` | `false` | **per-run opt-in**: partition and format an unprepared disk (stops nothing) |
| `sandbox_storage_allow_preseed` | `false` | **per-run opt-in**: copy the live stores onto the disk, bandwidth-capped, while the daemons run (stops nothing) |
| `sandbox_storage_allow_live_migration` | `false` | **per-run opt-in**: stop the daemons, checksum-copy the stores, move the binds; refuses while docker carries any container |
| `sandbox_storage_allow_run_loss` | `false` | **per-run opt-in**, with the above: accept ending the containers docker is carrying, including shims that outlive the daemon stop (TERM, then KILL) |

```yaml
# hp-xubuntu — the device, and a swap sized to the sandboxes' summed swap
# allowance (15 concurrent x 8 GB, plus headroom for the candidate instance's
# unlimited petri containers) rather than to RAM; every other value is the
# role default.
sandbox_storage_device: /dev/disk/by-id/ata-Fanxiang_S101_4TB_FX233090446
sandbox_storage_swap_size: 160GiB
```

## The procedure

A plain converge **never formats a disk and never stops a daemon**. Each of
those is one run, authorised by its own extra var, and the drift read says
which one is owed. Every mount the role makes is verified by `findmnt` against
the partition it resolved, never by presence alone.

1. Read the drift report: `just ansible-drift ansible/fabro-hosts.yml --limit
   hp-xubuntu --tags sandbox_storage`. On an unprepared disk it reports
   `DRIFT: … carries neither LABEL=…`; on a prepared disk whose stores have not
   moved it reports `DRIFT: /var/lib/containerd, /var/lib/docker are not yet
   served from …`.
2. **Format, swap, preseed — live, no run affected** (formatting destroys
   everything on the disk; it happens only when neither role label resolves
   anywhere on the host, so a prepared disk is never re-formatted):
   `just ansible-apply ansible/fabro-hosts.yml --limit hp-xubuntu --tags
   sandbox_storage -e sandbox_storage_allow_format=true -e
   sandbox_storage_allow_preseed=true`, dispatched detached (the preseed is
   ~80 minutes for hp's ~190 GB at the default cap). In order: partitions and
   formats the disk, writes the swap and filesystem fstab lines, **activates
   the swap at the declared priority first**, mounts and verifies the
   filesystem, then copies the live stores onto it from the directories the
   old fstab lines name (`/data/containerd`, `/data/docker`). The store move is
   DEFERRED by the role: it reports `DEFERRED: …` and touches no daemon, no
   bind and no drop-in. Re-running later with only `allow_preseed` refreshes
   the copy incrementally.
3. **Drain, then move.** Stopping docker and containerd ends every in-flight
   sandbox run on the host (the Dispatcher records them as failed), so stop
   dispatching to each instance in this host's `fabro_server_instances` and
   wait for its active runs (`HOME=<home_env> <binary_path> --json ps`). Do NOT
   restart the Fabro servers. Then, dispatched detached:
   `just ansible-apply ansible/fabro-hosts.yml --limit hp-xubuntu --tags
   sandbox_storage -e sandbox_storage_allow_live_migration=true`. In order,
   the run:
   - classifies each store from the HOST, not from fstab: *converged* (bind
     actually mounted from the new partition at the right subtree, store
     present), *copy+mount* (not yet served and the record on the new disk
     does not say it was copied), *mount-only* (not served but recorded as
     copied — a cutover that died between copy and bind, or a bind that went
     missing; it is **never recopied over**), or *refused* (mounted from the
     new disk over an empty directory);
   - verifies each old store it would copy from — the directory the old fstab
     line named (`/data/containerd`, `/data/docker`), or the one the record
     names on a retry — three ways: the bind target, where still mounted, is
     served from the same filesystem and subtree; the filesystem UUID matches
     the record where one exists; it holds a store. Nothing is copied from a
     source that fails any of these;
   - refuses while a preseed `rsync` is still writing under the mount, and
     takes the host-side flock every copy onto the new disk shares, so a
     preseed a still-running earlier play launches later finds the record
     marks the store copied and leaves it alone;
   - writes the record (source, UUID, subtree, `copied: false`) on the new
     disk;
   - lists the containers FIRST (`docker ps -q`), then reads the unit states:
     a successful non-empty listing requires `-e
     sandbox_storage_allow_run_loss=true`; a failed listing is accepted only
     when `docker.service` and `docker.socket` are both verifiably inactive;
   - stops `docker.socket`, `docker.service`, `containerd.service`, then
     **masks** all three — the durable inhibitor: a reboot before the new
     binds are in place must not start a daemon on the old stores after the
     record says they were copied;
   - proves quiescence: no `containerd-shim` process survives (with
     `allow_run_loss` the survivors are ended, TERM then KILL; without it they
     are a refusal), and no line of the mount table references either store's
     subtree — a container's overlay under `/run/containerd` would;
   - copies each uncopied store through the copy helper
     (`/usr/local/libexec/sandbox-storage-copy`: up to 8 parallel
     `rsync -aHAX --delete` over the depth-2 subtrees, then one full pass;
     size+mtime comparison, not `-c`, which ran at ~10 MB/s on hp) and publishes that store `copied: true`
     atomically INSIDE the same lock acquisition, so no preseed can write it
     afterwards;
   - unmounts the old binds, snapshots fstab, writes the two bind lines, mounts
     and verifies the new binds by device and subtree AND by content (a bound
     target that holds no store is a refusal, with the daemons left masked),
     installs the drop-ins, **unmasks** the three units and starts them.
   The old store copies are left in place. An interrupted cutover is resumed by
   re-running the same command: it reads its sources from the record (which
   takes precedence over fstab), never from an exposed target; a store already
   recorded as copied is only re-bound, never recopied; and a host found with
   the daemons masked is a host this role must finish — the mask is lifted
   only by the verified end of the cutover. A store recorded as copied whose
   directory holds nothing is a refusal, not a recopy.
4. If `/var/lib/docker-sandbox-slice/restart-pending` existed before step 3,
   the restart inside it loaded the sandbox envelope too; clear the marker by
   its own tag in the same window: `just ansible-apply ansible/fabro-hosts.yml
   --tags docker_sandbox_slice_drained_restart` (see that role's HOST_VARS.md).
5. Verify: `cat /proc/swaps` lists the partition at priority 10,
   `findmnt /var/lib/containerd` and `findmnt /var/lib/docker` each resolve
   to the partition with FSROOT `/containerd` / `/docker`, `docker images`
   lists what it did before, a dispatch runs to a terminal verdict, and the
   drift read is clean.
6. Reclaim the old copies only after that dispatch has passed. On
   `hp-xubuntu` they are `/data/containerd` and `/data/docker`, and
   `/swap.img` stays as the low-priority second swap. Reclaim is its own
   opt-in run, and stops nothing: `just ansible-apply ansible/fabro-hosts.yml
   --limit <host> --tags sandbox_storage -e sandbox_storage_allow_reclaim=true`.
   It re-checks the binds, the daemons and every mount namespace before it
   deletes, and it also deletes `/etc/fstab.pre-sandbox-storage` and any
   `sandbox_storage_reclaim_extra_paths`. After it, the rollback below is gone.

## Rollback

Rolling back returns the daemons to the OLD stores, which do not carry any
image pulled, container created or volume written after the cutover; reconcile
those first or accept their loss.

1. Inside a drained window, stop `docker.socket`, `docker.service` and
   `containerd.service`. If a cutover was interrupted after its mask step, the
   three units are MASKED (`systemctl is-enabled` prints `masked`); leave them
   so until step 3 has restored and verified the old binds.
2. Restore the pre-cutover fstab. If `/etc/fstab.pre-sandbox-storage` exists,
   `cp /etc/fstab.pre-sandbox-storage /etc/fstab` (the one snapshot this role
   took before rewriting a bind line; lineinfile's per-edit `.bak` copies may
   already carry one migrated line). If it does NOT exist, the cutover was
   interrupted before any bind line was rewritten (the daemons are masked from
   before the copy, the snapshot is taken only after it): confirm the current
   `/etc/fstab` still carries the ORIGINAL bind lines
   (`/data/containerd /var/lib/containerd none bind 0 0` and
   `/data/docker /var/lib/docker none bind 0 0` on hp) and keep it as it is.
   Remove the two drop-ins under `/etc/systemd/system/{docker,containerd}.service.d/`
   and `systemctl daemon-reload`.
3. `umount /var/lib/containerd` and `umount /var/lib/docker` until
   `mountpoint` says each is not mounted, then mount each from the restored
   lines as two separate commands: `mount /var/lib/containerd` and
   `mount /var/lib/docker`. Verify each is served from the old filesystem
   (`findmnt -rno SOURCE,FSROOT --nofsroot <target>`) and holds its store.
   Then `systemctl unmask containerd.service docker.socket docker.service` and
   start them in that order.
   **Invalidate the migration record**: delete
   `/srv/sandbox-storage/.sandbox-storage-sources.json`. The new directories
   are now stale relative to the old stores that are serving again, and a
   record still marking them `copied: true` would make a later cutover re-bind
   them without recopying — the role refuses that case while the daemons are
   unmasked, but the record is wrong and should not be left to be reasoned
   about.
4. Only if the disk is being retired altogether: `swapoff LABEL=sandbox-swap`,
   `umount /srv/sandbox-storage`, drop the swap and filesystem fstab lines,
   and `systemctl daemon-reload`; the disk's partitions may then be wiped by
   hand.

## Expiry

None: a factory host's stores belong on a disk of their own for as long as the
host runs sandbox containers at all. Retire the role with the host.
