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

## The variables

| variable | default | what it is |
| --- | --- | --- |
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
| `sandbox_storage_preseed_bwlimit` | `40m` | the preseed's read ceiling on the source disk (`rsync --bwlimit`); `ionice -c3` is a no-op under `mq-deadline`, so this is the real control |
| `sandbox_storage_sources_record` | `.sandbox-storage-sources.json` | file on the new disk recording the old stores' paths, written before the cutover unmounts anything; an interrupted cutover resumes from it |
| `sandbox_storage_fstab_snapshot` | `/etc/fstab.pre-sandbox-storage` | the one named pre-cutover fstab copy the rollback restores |
| `sandbox_storage_allow_format` | `false` | **per-run opt-in**: partition and format an unprepared disk (stops nothing) |
| `sandbox_storage_allow_preseed` | `false` | **per-run opt-in**: copy the live stores onto the disk, bandwidth-capped, while the daemons run (stops nothing) |
| `sandbox_storage_allow_live_migration` | `false` | **per-run opt-in**: stop the daemons, checksum-copy the stores, move the binds; refuses while docker carries any container |
| `sandbox_storage_allow_run_loss` | `false` | **per-run opt-in**, with the above: accept ending the containers docker is carrying |

```yaml
# hp-xubuntu — the one value that varies; every other value is the role default.
sandbox_storage_device: /dev/disk/by-id/ata-Fanxiang_S101_4TB_FX233090446
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
   restart the Fabro servers. Then:
   `just ansible-apply ansible/fabro-hosts.yml --limit hp-xubuntu --tags
   sandbox_storage -e sandbox_storage_allow_live_migration=true`. The run
   refuses while `docker ps` shows any container (add `-e
   sandbox_storage_allow_run_loss=true` to accept ending them), records the old
   stores' paths on the new disk, stops `docker.socket`, `docker.service` and
   `containerd.service`, refuses if any mount remains beneath a store (a shim
   that outlived the stop), `rsync -aHAXc --delete`s each store — checksummed,
   because the preseed ran against a live store, so budget tens of minutes
   for the two full reads — unmounts the old binds, snapshots fstab, writes the
   two bind lines, mounts and verifies the new binds, installs the drop-ins,
   and starts the three units. The old store copies are left in place. An
   interrupted cutover is resumed by re-running the same command; it reads its
   sources from the record, never from an exposed target.
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
   `/swap.img` stays as the low-priority second swap.

## Rollback

Rolling back returns the daemons to the OLD stores, which do not carry any
image pulled, container created or volume written after the cutover; reconcile
those first or accept their loss.

1. Inside a drained window, stop `docker.socket`, `docker.service` and
   `containerd.service`.
2. Restore the pre-cutover fstab: `cp /etc/fstab.pre-sandbox-storage
   /etc/fstab` (the one snapshot this role took before rewriting a bind line;
   lineinfile's per-edit `.bak` copies may already carry one migrated line).
   Remove the two drop-ins under `/etc/systemd/system/{docker,containerd}.service.d/`
   and `systemctl daemon-reload`.
3. `umount /var/lib/containerd` and `umount /var/lib/docker` until
   `mountpoint` says each is not mounted, then mount each from the restored
   lines as two separate commands: `mount /var/lib/containerd` and
   `mount /var/lib/docker`. Start `containerd.service`, `docker.socket`,
   `docker.service`.
4. `swapoff LABEL=sandbox-swap` and drop its fstab line only if the swap is
   also being retired; the disk's partitions may then be wiped by hand.

## Expiry

None: a factory host's stores belong on a disk of their own for as long as the
host runs sandbox containers at all. Retire the role with the host.
