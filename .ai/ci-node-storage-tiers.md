# CI node storage tiers — moving media, and the traps around it

Read this before touching the CI runner node's storage tiers (`ci-cache`,
`ci-containerd`, `ci-workvols`), before installing or surveying NVMe
hardware on the node, and before running anything under
`ci-runner/k3s/phase2/storage-layout/`. It is agent-facing operational
guidance; the layout itself is defined by `install-storage-layout.sh` and
documented in `ci-runner/k3s/phase2/README.md` ("Storage layout:
media-neutral tier identity"). Every entry below is drawn from something that
actually went wrong on `poweredge-xubuntu` on 2026-09-04.

## The model in one paragraph

A tier is identified by its ext4 **label**, which doubles as its LV name. The
label is the same on any medium, so `/etc/fstab` never changes when a tier
moves; the git copy of the layout stays byte-identical to the host's. Moving a
tier is `migrate-tier.sh prepare` (create the volume, temporary label, bulk
copy, live) followed by either `migrate-tier.sh cutover` (quiet window: final
delta, verify, relabel, `mount -a`, k3s back) or, for a tier that holds only
per-job volumes and a regenerable root, `switch-live` → `drain-status` →
`finish-live` (no window: the new filesystem is STACKED over the old, pods
drain on their own) and `reclaim` after the next boot. Each role's filesystem
type is decided once, in `migrate-tier.sh role_fstype`: `ci-workvols` is XFS
with reflink (labels hold 12 bytes there), the other two ext4. Two volumes must never carry the same
role label at once; the installer refuses while they do.

## Rules that came from incidents

- **Never run a blanket `udevadm trigger --subsystem-match=block` on a host
  whose filesystems sit on device-mapper.** The synthetic change event runs
  LVM's udev rules without the activation cookie, marks the dm devices
  not-ready, systemd stops every tier mount bound to them, and the k3s
  `RequiresMountsFor` drop-in stops k3s ahead of the mounts (containerd shims
  orphaned, every listener `Unknown`). After `tune2fs -L` on a mounted LV,
  do nothing: `blkid` already reads the new label, `mount -a` resolves
  `LABEL=` through it, and `lvchange --refresh <vg>/<lv>` or the next boot
  refreshes `/dev/disk/by-label`. `migrate-tier.sh` only ever triggers a
  scoped `--action=change` on volumes it has already unmounted.
- **Before any raw-device `fio`, `test -b` the path, and never pass `--size`
  to a device test.** A `by-id` symlink that does not exist (driver probe
  failed, drive not yet enumerated) makes `fio --filename=/dev/disk/by-id/…`
  CREATE a regular file on RAM-backed `devtmpfs`. On 2026-09-04 it grew to
  88 GB, took host memory from 3 GB to 92 GB, blocked udev from creating the
  real symlink, and the next read reported 435k IOPS at 609 ns — a number
  that looked like a superb drive and was RAM.
- **A stale copy of a tier is never reused.** A drive pulled from a failed
  attempt still holds a volume group with a copy of containerd that was stale
  the moment CI ran again. `migrate-tier.sh prepare` refuses a PV on any
  device carrying a signature; wipe it by hand (`vgremove`, `pvremove`,
  `wipefs -a`) after confirming nothing on it is wanted, then copy afresh.
- **ext4 labels hold 16 bytes; XFS labels hold 12.** `standin-containerd`
  silently became `standin-containe`. Role names, `new-<suffix>` and
  `old-<suffix>` temporary names all fit both limits; check any new name
  before using it (`ci-containerd` is 13, which is why it stays ext4-only).
- **Never unmount a tier mount under a running k3s, not even to swap it.**
  The `RequiresMountsFor` drop-in orders k3s's stop before the mount's, so
  an unmount is a k3s stop. To replace a tier live, STACK the new mount on
  top (`switch-live`); the old one stays underneath until the next boot.
- **An OS-side PCIe link-speed cap can rescue a running system, never a
  boot.** Dell firmware trains a switch card's downstream links before the
  OS runs; a link that is marginal at Gen3 halts POST with `UEFI0066` ("PCIe
  link training failure … system halted"). A card that cannot do Gen3 with
  the drive is replaced, not worked around with `setpci` at boot.
- **Address NVMe physical volumes by `/dev/disk/by-id/` only.** Behind a PCIe
  switch the bus numbers and the `nvme0n1` ordering can shift across boots;
  `migrate-tier.sh prepare` rejects any other PV path.
- **A manual `systemctl start k3s` does not run the boot chain's `After=k3s`
  oneshots.** After a cutover, start `inject-github-app-secret`,
  `reapply-node-extended-resource` and `otel-collector-identity` by hand (the
  script does), or the pool comes up without its secret and capacity.
- **Fans at full with normal temperatures and the lid off is the chassis
  intrusion switch, not thermal.** Seat the lid; do not touch the fan
  settings (`poweredge-xubuntu-info` `FAN_COOLING.md`).

## The link survey is the acceptance test for any NVMe card or socket change

Run it BEFORE writing a byte to the drive, after every reseat. Healthy means:
the card's upstream `LnkSta` at its rated width (8 GT/s x8 for the StarTech
PEX8M2E2), the drive at 8 GT/s x4 ("downgraded" from a Gen4/Gen5 drive's
`LnkCap` is expected), `CESta` all `-` on the endpoint after clearing it and
running I/O, QD1 4k random reads in the tens of microseconds, and no
`nvme … timeout` lines in `dmesg`. The kernel's AER counters can read zero
while the link is faulty: a root port that reports `RootSta: CERcvd-` never
receives correctable-error messages from behind a switch, so read the sticky
`CESta` bits with `lspci -vv` directly.

```bash
lspci -tv                                                  # where the drive landed
for ep in $(lspci -Dn -d ::0108 | awk '{print $1}'); do sudo lspci -vvs "$ep" | grep -E 'LnkSta:|CESta'; done
sudo setpci -s <endpoint> ECAP_AER+0x10.l=0xFFFFFFFF; sudo setpci -s <endpoint> CAP_EXP+0x0a.w=0x000F
D=/dev/disk/by-id/<drive>; test -b "$D" || echo "STOP: not a block device"
sudo fio --name=r --filename=$D --rw=randread --bs=4k --iodepth=1 --ioengine=libaio --direct=1 --runtime=5 --time_based | grep -E 'read: IOPS|clat.*avg'
sudo lspci -vvs <endpoint> | grep -E 'LnkSta:|CESta'      # re-read after I/O
```

Reference results on this host, 2026-09-04: the `PCIE-PEX8747M4` (PLX
PEX8747) failed it on two sockets and two slots (`RxErr+ BadTLP+ BadDLLP+`,
~1 MB/s, then `UEFI0066` at POST); the StarTech PEX8M2E2 (ASM2824) with the
same SN8100 passed it on the first boot (20.7k IOPS at 40 µs QD1, 3.5 GB/s
sequential, `CESta` clean, 245k IOPS at QD32).
