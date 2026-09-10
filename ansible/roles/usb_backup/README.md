# usb_backup

A committed, recreatable 12-hourly local USB backup for **poweredge-xubuntu**.

The other backup roles are VPS-only: `restic_backup` pushes the VPS to S3 and
the `arq_*` roles feed a Mac. poweredge had no scheduled backup. This role adds
one to the ext4 USB volume (Toshiba 931G, label `POWEREDGE-BACKUP`) that is
fstab-mounted at `/mnt/usb-backup` (`nofail`), driven by a systemd timer.

It is committed provisioning, not a hand-added crontab, so it is reproducible on
a rebuild.

## Schedule

- Timer `usb-backup.timer` fires at **06:00 and 18:00 America/Los_Angeles**
  (every 12h), `Persistent=true` (catches up a missed run) with a 5-minute
  randomized delay.
- It triggers oneshot `usb-backup.service`, which runs
  `/usr/local/sbin/usb-backup` as root with `TimeoutStartSec=4h`.
- The role **arms the timer but never runs a backup at apply time**. The first
  run is the next scheduled boundary, or a manual `sudo /usr/local/sbin/usb-backup`.

## What it backs up

Written under `/mnt/usb-backup/`:

| Destination | Source | Notes |
|---|---|---|
| `rootfs/` | `/` (`--one-file-system`) | OS + all on-disk config, incl. `/etc` and the k3s server credentials/tls/token under `/var/lib/rancher/k3s/server`. `rsync -aHAXS --numeric-ids --delete --delete-excluded`. |
| `boot-efi/` | `/boot/efi` | vfat ESP, copied `-rltD` (no ownership/xattrs on vfat). |
| `k3s-datastore/state.db` | `/var/lib/rancher/k3s/server/db/state.db` | Online-consistent `sqlite3 .backup` snapshot of the LIVE k3s datastore (see below). |
| `meta/` | host metadata | `lsblk`, `blkid`, `fstab`, `sfdisk -d /dev/sda`, dpkg selections, `uname`, enabled units, `k3s --version`. |

### Excluded from the rootfs pass

- `/var/cache/ci-runner/***` — the ~59G regenerable CI runner cache the
  maintainer does **not** want backed up. (The old standalone backup script had
  a dedicated pass for this; here it is dropped and replaced by the datastore
  snapshot pass.)
- `/k3s-storage/***` — local-path PVC scratch, created and destroyed per CI job.
- `/var/log/pods/***` — transient per-pod logs.
- `/var/lib/rancher/k3s/agent/containerd.premove/***` and
  `/var/lib/rancher/k3s/storage.premove/***` — containerd-relocation rollback copies.
- `/swap.img`, `lost+found`.

### The k3s datastore snapshot

The k3s embedded-SQLite datastore lives on a **tmpfs** mount, so rsync's
`--one-file-system` never sees it. It is a **live** database, so a plain file
copy could be torn. The runner instead takes an online-consistent copy with
`sqlite3 .backup`, which is safe against the open database and captures any WAL.

Guards: if `sqlite3` is missing the pass **fails** (the host is mis-provisioned
— the role installs it); if the datastore file is absent (cluster down, or this
is not the server node) the pass **warns** and continues rather than failing.

## Exit-code policy

`usb-backup.sh` exits `0` only if every pass succeeded. rsync `24` (files
vanished mid-copy) is a WARN; rsync `23` (files not transferred — incomplete)
and anything else is a FAILURE named in the summary. Do not judge success by
eyeballing the log — check the exit status / journal result.

## Restore notes

- **Files:** `rsync` back from `/mnt/usb-backup/rootfs/` and `boot-efi/`
  (preserve `--numeric-ids`), then regenerate the ESP with `grub-install`.
- **k3s datastore:** with k3s stopped, copy `k3s-datastore/state.db` back to
  `/var/lib/rancher/k3s/server/db/state.db`, then start k3s. The snapshot is a
  plain SQLite database file.

## Coupling to watch

`files/usb-backup.sh` is a **static** runner and owns the operative `DEST`
(`/mnt/usb-backup`) and `DATASTORE`
(`/var/lib/rancher/k3s/server/db/state.db`) constants. `defaults/main.yml`
mirrors them in `usb_backup_dest` (consumed by the mountpoint assertion) and
`usb_backup_datastore_path` (documentation). Nothing mechanical checks the two
against each other — if you move the mount or the datastore, edit **both**.
