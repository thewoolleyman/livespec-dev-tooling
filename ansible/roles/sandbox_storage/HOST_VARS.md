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
| `sandbox_storage_swap_label` | `sandbox-swap` | the swap partition's label (GPT partition 1) |
| `sandbox_storage_fs_label` | `sandbox-containers` | the filesystem's label (GPT partition 2, the rest of the disk) |
| `sandbox_storage_swap_size` | `32GiB` | the swap partition's size, an sgdisk suffix; size it to the host's RAM |
| `sandbox_storage_swap_priority` | `10` | the swap line's `pri=`, above the swap file's default `-1` |
| `sandbox_storage_mount` | `/srv/sandbox-storage` | where the filesystem is mounted |
| `sandbox_storage_containerd_src` | `<mount>/containerd` | the containerd store directory on the disk |
| `sandbox_storage_docker_src` | `<mount>/docker` | the docker root directory on the disk |
| `sandbox_storage_containerd_dir` | `/var/lib/containerd` | containerd's bind target |
| `sandbox_storage_docker_dir` | `/var/lib/docker` | docker's bind target |
| `sandbox_storage_dropin_name` | `10-requires-sandbox-storage.conf` | the `RequiresMountsFor=` drop-in each daemon gets |
| `sandbox_storage_allow_format` | `false` | **per-run opt-in**: partition and format an unprepared disk (stops nothing) |
| `sandbox_storage_allow_preseed` | `false` | **per-run opt-in**: copy the live stores onto the disk at idle IO priority while the daemons run (stops nothing) |
| `sandbox_storage_allow_live_migration` | `false` | **per-run opt-in**: stop the daemons, copy the live stores, move the binds |

```yaml
# hp-xubuntu — the one value that varies; every other value is the role default.
sandbox_storage_device: /dev/disk/by-id/ata-Fanxiang_S101_4TB_FX233090446
```

## The procedure

A plain converge **never formats a disk and never stops a daemon**. Each of
those is one run, authorised by its own extra var, and the drift read says
which one is owed.

1. Read the drift report: `just ansible-drift ansible/fabro-hosts.yml --tags
   sandbox_storage`. On an unprepared disk it reports `DRIFT: … carries neither
   LABEL=…`; on a prepared disk whose stores have not moved it reports `DRIFT:
   /var/lib/containerd, /var/lib/docker are not yet served from …`.
2. **Format and preseed — live, no run affected** (formatting destroys
   everything on the disk; it happens only when neither role label resolves
   anywhere on the host, so a prepared disk is never re-formatted):
   `just ansible-apply ansible/fabro-hosts.yml --tags sandbox_storage -e
   sandbox_storage_allow_format=true -e sandbox_storage_allow_preseed=true`.
   This run partitions and formats the disk, writes the swap and filesystem
   fstab lines, mounts the filesystem, activates the swap, copies the live
   stores onto the disk under `ionice -c3 nice -n19` (hours for a large store;
   dispatch it detached), and **defers the store move**, reporting `DEFERRED:
   …` and touching neither daemon, neither bind, and no drop-in. Re-running it
   later with only `allow_preseed` refreshes the copy incrementally.
3. **Drain, then move.** Stopping docker and containerd ends every in-flight
   sandbox run on the host (the Dispatcher records them as failed), so stop
   dispatching to each instance in this host's `fabro_server_instances` and
   either wait for its active runs (`HOME=<home_env> <binary_path> --json ps`)
   or accept their loss. Do NOT restart the Fabro servers. Then:
   `just ansible-apply ansible/fabro-hosts.yml --tags sandbox_storage -e
   sandbox_storage_allow_live_migration=true`. The run stops the daemons
   (socket first), `rsync -aHAX --delete`s each store through its bind target
   onto the disk (an incremental of the preseed), unmounts the old binds,
   writes the two bind lines, mounts the new binds, installs the drop-ins, and
   starts containerd, `docker.socket` and docker. The old store copies are left
   in place.
4. If `/var/lib/docker-sandbox-slice/restart-pending` existed before step 3,
   the restart inside it loaded the sandbox envelope too; clear the marker by
   its own tag in the same window: `just ansible-apply ansible/fabro-hosts.yml
   --tags docker_sandbox_slice_drained_restart` (see that role's HOST_VARS.md).
5. Verify: `cat /proc/swaps` lists the partition, `findmnt /var/lib/containerd
   /var/lib/docker` resolve to `<mount>/…`, `docker images` lists what it did
   before, a dispatch runs to a terminal verdict, and the drift read is clean.
6. Reclaim the old copies only after that dispatch has passed. On
   `hp-xubuntu` they are `/data/containerd` and `/data/docker`, and
   `/swap.img` stays as the low-priority second swap.

## Rollback

1. Restore the previous `/etc/fstab` from the `.bak` lineinfile left beside it
   (or point the two bind lines back at the old store directories), remove the
   two drop-ins under `/etc/systemd/system/{docker,containerd}.service.d/`, and
   `systemctl daemon-reload`.
2. Inside a drained window: stop `docker.socket`, `docker.service` and
   `containerd.service`; `umount` the two binds until `mountpoint` says they
   are not mounted; `mount /var/lib/containerd /var/lib/docker` from the
   restored lines; start the three units. The old stores are intact where step
   6 above would have reclaimed them, so nothing is copied back unless images
   were pulled after the move.
3. `swapoff LABEL=sandbox-swap` and drop its fstab line if the swap is also
   being retired; the disk's partitions may then be wiped by hand.

## Expiry

None: a factory host's stores belong on a disk of their own for as long as the
host runs sandbox containers at all. Retire the role with the host.
