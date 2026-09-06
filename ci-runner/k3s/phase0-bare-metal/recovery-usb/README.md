# The Recovery USB — the rescue environment the bare-metal stage boots from

A PNY 128 GB USB 3.2 stick carrying a REAL installed Ubuntu 26.04 "resolute"
(debootstrap, not a live image): GNOME desktop (`ubuntu-desktop-minimal`),
sshd with `PermitRootLogin yes` + `PasswordAuthentication yes`, NOPASSWD
sudoers, NetworkManager DHCP on all NICs, and the full storage toolchain —
`lvm2 mdadm gdisk parted dosfstools smartmontools nvme-cli ipmitool rsync
debootstrap` plus a copy of `perccli64` at `/opt/MegaRAID/perccli/`.

This is the environment a pool node is rebuilt FROM: it boots before the node
has an operating system, before k3s exists, and before `../../phase2/
install-node.sh`'s admin-kubeconfig precondition can be satisfied. Spec:
`SPECIFICATION/non-functional-requirements.md` §"Runner-pool node rebuild
recipe".

## Provenance — why this tree exists at all

The builder and the boot harness were written in the livespec repository's
plan `poweredge-raid-array-maintenance` and now live in its FROZEN archive at
`plan/archive/poweredge-raid-array-maintenance/research/`
(`build-recovery-usb.sh`, `test-recovery-usb.sh`, `recovery-usb-build.md`),
read here at livespec commit `20447b544829d8749c3f460406383f5afeaf7191`.
**Those copies are never edited** — an archived plan is a record of what
happened, not a maintained artifact.

That mattered, because the archived builder is WRONG in a way that only shows
up at boot: it predates the two traps that had to be fixed by hand to make the
stick boot at all, so replaying it reproduces a stick that stops at a bare
`grub>` prompt. The artifact in git did not reproduce the artifact that was
proven. The fix could not land in a frozen archive, so the maintained copy
lives here, with both fixes folded in as scripted steps. Discharges livespec
work-item `livespec-ifwnqj.4`.

## Files

| Path | Role |
|---|---|
| `build-recovery-usb.sh` | Builds the stick end-to-end on a running host: partition → debootstrap → chroot package install → grub → **both boot fixes** → perccli. `--dry-run` prints every command and executes none. Destructive steps are refused, by name, against a target that already carries data unless the invocation carries `--i-consent-to-destroy=<device>` naming it. |
| `test-recovery-usb.sh` | Boots the built stick under QEMU + OVMF and FAILS unless the kernel reaches a login prompt on the serial console. This harness is what caught both traps below before anyone walked to a machine. `--ssh-verify` additionally logs in and checks the toolchain, perccli, and the stick README. |
| `recovery-usb-exit-tests.sh` | 35 behavioral exit tests for both scripts, run entirely through `--dry-run` against shim binaries. Proves the ESP kernel copy is emitted, the menu is written at the one path GRUB reads, the rendered menu points at the ESP copies and never at the ext4, the destruction gate refuses and names the device, and — measured, not asserted — that a dry run executes nothing at all. |

## The two boot traps (both hit, both fixed, both will recur on a rebuild)

Recorded verbatim in intent from the archived `recovery-usb-build.md`
§"The two boot traps". They are properties of Ubuntu's signed GRUB, not
accidents of one build, so any rebuild that does not carry these fixes hits
them again.

### 1. Ubuntu's signed GRUB cannot read modern ext4

resolute's `mkfs.ext4` defaults include `orphan_file`, `orphan_present`, and
`metadata_csum_seed`; the signed `grubx64.efi` fails on them, leaving a bare
`grub>` prompt with no menu and no diagnosis.

**Fix — GRUB must never touch the ext4.** The kernel and initrd are COPIED
from `/boot` onto the FAT32 ESP as `/vmlinuz` and `/initrd.img` and loaded
from there; only the kernel mounts the ext4 root. `build-recovery-usb.sh`
step `[7]` does this, resolving the newest `/boot/vmlinuz-*` inside the
chroot.

**Consequence, and it bites later:** after any kernel upgrade ON THE STICK,
re-copy the new `vmlinuz`/`initrd.img` from `/boot` to the ESP or the stick
keeps booting the old kernel. The recipe is printed in the stick's own
`/root/README-RECOVERY.md`, which the builder writes.

### 2. The CD-variant GRUB reads its menu from ONE path on the ESP

`grub-install --removable` with the signed packages installs the CD-variant
GRUB, whose baked-in config path is `/boot/grub/grub.cfg` **on the ESP**
(tell-tale: `/.disk/info` probe errors on the serial console). It ignores
`EFI/ubuntu/grub.cfg` and `EFI/BOOT/grub.cfg` — a menu written there is a
silently ignored second source of truth, which is the worst shape: no error,
no menu.

**Fix — the menu lives at `ESP:/boot/grub/grub.cfg` and nowhere else.**
`build-recovery-usb.sh` step `[8]` writes exactly:

```
set timeout=3
search.fs_uuid <ESP-UUID> root
menuentry "Ubuntu Desktop Recovery USB" {
  linux /vmlinuz root=UUID=<ext4-root-UUID> rw console=tty0 console=ttyS0,115200
  initrd /initrd.img
}
```

Note what the `linux` and `initrd` lines name: the ESP copies, not the ext4
partition. That is trap 1's fix and trap 2's fix meeting in one file, and it
is what `recovery-usb-exit-tests.sh` tests 4 and 5 assert.

## Boot proofs

Carried over from the archived record. These are the proofs of the stick that
was built and fixed BY HAND in 2026-09; the committed builder reproduces that
stick plus the deviations listed below, and owes its own physical proof.

| Where | When | Result |
|---|---|---|
| QEMU/OVMF on `poweredge-xubuntu` | 2026-09-03 | PASS in ~40 s — firmware → shim → GRUB → kernel, root login, all tools verified. |
| gmktec (physical) | 2026-09-04 | Booted to desktop; sshd reachable over a Mac reverse tunnel; then enrolled in tailscale. |
| `poweredge-xubuntu` (physical) | 2026-09-04 | Booted via firmware entry `Boot0004 "Ubuntu Recovery USB"` (created with `efibootmgr -C -d <PNY-by-id> -p 1 -L "Ubuntu Recovery USB" -l "\EFI\BOOT\BOOTX64.EFI"`; default BootOrder untouched — select it per-boot with `efibootmgr --bootnext 0004` or F11). Up in ~190 s at LAN `192.168.1.200`; hardware verified `PowerEdge R630`. |
| This builder, physical | **not yet** | Building and booting a physical stick from THIS script is a human step, recorded on livespec work-item `livespec-ifwnqj.4`. Until then, treat this builder as unproven on hardware. |

## Deviations from the stick that was proven

Stated plainly, because "reproduces the proven stick" is the whole point and
these are the places it does not:

1. **Both boot fixes are scripted.** The proven stick got them by hand. This
   is the intended difference — it is why the file exists.
2. **`console=tty0 console=ttyS0,115200` on the kernel line.** The proven
   menu had `root=UUID=… rw` and nothing else. The serial console is what
   lets `test-recovery-usb.sh` observe the kernel reaching a login prompt
   instead of only observing that GRUB got that far; `console=tty0` stays
   first, so the local console is unchanged on a physical boot. Pass
   `--no-serial-console` to render the proven line exactly — a stick built
   that way cannot be proven by the QEMU harness.
3. **The target device is a parameter, not a hard-coded serial.** The
   archived script addressed one PNY stick by its by-id path and verified the
   vendor string. The device is now `--device=<path>`, and the safety
   property is the destruction gate below rather than a vendor match.
4. **Nothing is destroyed without consent.** The archived script wiped its
   hard-coded target on sight. Per the spec's "Re-runnable, and destructive
   only on consent", a target already carrying a filesystem or partition
   table is refused, by name, unless `--i-consent-to-destroy` names that same
   device. The gate is fail-closed: a probe that cannot answer is treated as
   populated.

## Using it

Read the plan before writing anything — the dry run is a complete, ordered
list of every command, and it executes none of them:

```bash
./build-recovery-usb.sh --device=/dev/disk/by-id/usb-PNY_USB_3.2.1_FD_… --dry-run
```

Then build for real. A stick that has ever been used carries a filesystem, so
the destruction consent is the normal case, not the exception:

```bash
sudo ./build-recovery-usb.sh \
  --device=/dev/disk/by-id/usb-PNY_USB_3.2.1_FD_… \
  --i-consent-to-destroy=/dev/disk/by-id/usb-PNY_USB_3.2.1_FD_…
```

Prove it boots before carrying it to a rack:

```bash
sudo ./test-recovery-usb.sh --image=/dev/disk/by-id/usb-PNY_USB_3.2.1_FD_… --ssh-verify
```

Run the exit tests after any edit to either script (no device, no network, no
root):

```bash
./recovery-usb-exit-tests.sh
```

## Operational notes

- **Address the stick by its by-id path, only.** `sdb` vs `sdc` ordering swaps
  between boots, and on the rebuild host the Toshiba backup disk is also USB
  (`usb-TOSHIBA_External_USB_3.0_…`). Every example above uses
  `/dev/disk/by-id/`; so should every invocation.
- **The credentials are deliberately weak.** `root` / `password`, sshd with
  password auth, NOPASSWD sudo. This is lab-only rescue media whose whole job
  is to be reachable on a machine with no working operating system. It is not
  a host that runs anything, and it must never be treated as one.
- **The identity travels with the stick.** The proven stick was enrolled on
  the tailnet as `ubuntu-recovery-usb`, so whatever machine boots it appears
  under that name — which is what makes a rebuild window remotely drivable
  with no tunnel. Enrolment is a human step and is not scripted here.
- **The GNOME first-boot wizard rewrites the hostname** on the first
  interactive boot. The proven stick's was re-set by hand afterwards.
