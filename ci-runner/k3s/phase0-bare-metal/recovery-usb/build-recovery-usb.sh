#!/usr/bin/env bash
# build-recovery-usb.sh — build the Ubuntu Desktop Recovery USB that the
# bare-metal stage of the runner-pool rebuild boots from.
#
# PROVENANCE. Ported from the livespec repository's FROZEN plan archive:
#   plan/archive/poweredge-raid-array-maintenance/research/build-recovery-usb.sh
# read at livespec commit 20447b544829d8749c3f460406383f5afeaf7191 (that file's
# own last-touching commit there is 41795f742d21f4c73309f03f4c6d857abe93cc63,
# "docs(plan): re-archive poweredge-raid-array-maintenance …", 2026-09-06).
# The archive is frozen: it is never edited, and this file is the maintained
# copy. The sibling record `recovery-usb-build.md` at that same archived path
# is the source of the two boot traps folded in below.
#
# WHAT THIS FILE ADDS OVER THE ARCHIVED SCRIPT. The archived script built the
# stick that was later made to boot, but it PREDATES the two traps that had to
# be fixed by hand to get there, so replaying it reproduces a stick that stops
# at a bare `grub>` prompt. Both fixes are scripted steps here:
#
#   TRAP 1 — GRUB must never read the stick's ext4. Ubuntu's signed
#   `grubx64.efi` cannot read an ext4 carrying resolute's `mkfs.ext4` defaults
#   (`orphan_file` / `orphan_present` / `metadata_csum_seed`). Fix: the kernel
#   and initrd are COPIED from `/boot` onto the FAT32 ESP and loaded from
#   there; only the kernel mounts the ext4 root. See step [7].
#
#   TRAP 2 — the CD-variant GRUB reads its menu ONLY from `ESP:/boot/grub/
#   grub.cfg`. `grub-install --removable` with the signed packages installs
#   that variant, and it ignores `EFI/ubuntu/grub.cfg` and `EFI/BOOT/
#   grub.cfg`. Fix: the menu is written at that one path. See step [8].
#
# SAFETY. Every destructive step is gated on an explicit destruction consent:
# a target that already carries a filesystem or a partition table is REFUSED,
# by name, unless the invocation carries `--i-consent-to-destroy=<device>`
# naming that same device. The gate is fail-closed — a probe that cannot
# answer is treated as "populated", never as "empty".
#
# `--dry-run` prints every command this script would run, in order, and
# executes NONE of them. The one thing it does execute is the read-only
# destruction gate (a `blkid` probe), because the gate decides whether the
# plan is allowed to exist at all; the gate never writes.
#
# Spec: SPECIFICATION/non-functional-requirements.md §"Runner-pool node
# rebuild recipe" ("Re-runnable, and destructive only on consent").

set -euo pipefail

# Trace output goes to fd 9 (a dup of the script's original stdout) so that a
# command substitution capturing a probe's value does not swallow the plan.
exec 9>&1

DEVICE=""
CONSENT=""
DRY_RUN=0
RELEASE=resolute
MIRROR=http://archive.ubuntu.com/ubuntu
MNT=/mnt/recovery-usb
PERCCLI_SOURCE=/opt/MegaRAID
# The proven stick's kernel line was exactly `root=UUID=<root> rw`. The serial
# console is appended so `test-recovery-usb.sh` can observe the kernel reaching
# a login prompt under QEMU; `console=tty0` keeps the local console first, so a
# physical boot is unchanged. `--no-serial-console` renders the proven line.
CMDLINE_EXTRA="console=tty0 console=ttyS0,115200"

usage() {
  cat <<'USAGE'
Usage: build-recovery-usb.sh --device=<path> [options]

Required:
  --device=<path>              Target stick. Address it by its immutable
                               /dev/disk/by-id/ path: sdb vs sdc ordering
                               swaps between boots.

Options:
  --i-consent-to-destroy=<path>
                               Destruction consent. Must name the SAME string
                               passed to --device. Required whenever the target
                               already carries a filesystem or partition table.
  --dry-run                    Print every command that would run; run none.
  --release=<name>             Ubuntu release to debootstrap (default: resolute)
  --mirror=<url>               Ubuntu mirror (default: http://archive.ubuntu.com/ubuntu)
  --mount=<path>               Build mountpoint (default: /mnt/recovery-usb)
  --perccli-source=<path>      perccli tree copied onto the stick
                               (default: /opt/MegaRAID; skipped if absent)
  --no-serial-console          Render the kernel line exactly as the proven
                               stick had it, with no console= arguments.
  -h, --help                   This text.
USAGE
}

die() {
  printf 'ABORT: %s\n' "$*" >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Command emission. Everything that mutates the target goes through `run`,
# `write_file`, or `run_chroot`, so `--dry-run` is a complete plan by
# construction rather than by an author remembering to echo each step.
# ---------------------------------------------------------------------------

# Print an argv as a copy-pasteable command line: shell-safe words verbatim,
# anything else through printf %q, so an operator can lift a step out of a dry
# run and run it by hand without unpicking escapes that were never needed.
trace_argv() {
  local word
  {
    printf '+'
    for word in "$@"; do
      if [[ $word =~ ^[A-Za-z0-9_@%+=:,./-]+$ ]]; then
        printf ' %s' "$word"
      else
        printf ' %q' "$word"
      fi
    done
    printf '\n'
  } >&9
}

run() {
  trace_argv "$@"
  if [ "$DRY_RUN" -eq 1 ]; then
    return 0
  fi
  "$@"
}

# Same, for the steps whose failure is expected and harmless — unmounting a
# partition nothing had mounted, copying a resolv.conf the host may not have.
run_optional() {
  trace_argv "$@"
  if [ "$DRY_RUN" -eq 1 ]; then
    return 0
  fi
  "$@" || true
}

# write_file <path>  — content on stdin.
write_file() {
  local path="$1" content
  content="$(cat)"
  {
    printf "+ cat > %s <<'EOF'\n" "$path"
    printf '%s\n' "$content"
    printf 'EOF\n'
  } >&9
  if [ "$DRY_RUN" -eq 1 ]; then
    return 0
  fi
  printf '%s\n' "$content" >"$path"
}

# run_chroot — chroot script on stdin.
run_chroot() {
  local script
  script="$(cat)"
  {
    printf "+ chroot %s /bin/bash -euxo pipefail <<'CHROOT'\n" "$MNT"
    printf '%s\n' "$script"
    printf 'CHROOT\n'
  } >&9
  if [ "$DRY_RUN" -eq 1 ]; then
    return 0
  fi
  printf '%s\n' "$script" | chroot "$MNT" /bin/bash -euxo pipefail
}

# probe <placeholder> <command...> — a READ-ONLY capture. Under --dry-run the
# command is printed and the placeholder is returned, so the plan renders with
# a value in the shape of the real one and still touches nothing.
probe() {
  local placeholder="$1"
  shift
  trace_argv "$@"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '%s' "$placeholder"
    return 0
  fi
  "$@"
}

note() {
  printf '%s\n' "$*" >&9
}

# Lazily tear the build mounts down if the build dies partway. Installed only
# on a real run — a dry run mounted nothing.
cleanup_mounts() {
  local d
  for d in dev/pts dev proc sys boot/efi; do
    umount -l "${MNT}/${d}" 2>/dev/null || true
  done
  umount -l "$MNT" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --device=*) DEVICE="${1#*=}" ;;
      --device)
        [ "$#" -ge 2 ] || die "--device needs a value"
        DEVICE="$2"
        shift
        ;;
      --i-consent-to-destroy=*) CONSENT="${1#*=}" ;;
      --i-consent-to-destroy)
        [ "$#" -ge 2 ] || die "--i-consent-to-destroy needs a value"
        CONSENT="$2"
        shift
        ;;
      --dry-run) DRY_RUN=1 ;;
      --release=*) RELEASE="${1#*=}" ;;
      --mirror=*) MIRROR="${1#*=}" ;;
      --mount=*) MNT="${1#*=}" ;;
      --perccli-source=*) PERCCLI_SOURCE="${1#*=}" ;;
      --no-serial-console) CMDLINE_EXTRA="" ;;
      -h | --help)
        usage
        exit 0
        ;;
      *) die "unknown argument: $1" ;;
    esac
    shift
  done
  [ -n "$DEVICE" ] || die "--device=<path> is required (see --help)"
}

# Partition device paths. by-id paths suffix `-part1`; nvme/mmcblk/loop names
# suffix `p1`; everything else suffixes a bare `1`.
partition_path() {
  local index="$1"
  case "$DEVICE" in
    */by-id/*) printf '%s-part%s' "$DEVICE" "$index" ;;
    */nvme* | */mmcblk* | */loop*) printf '%sp%s' "$DEVICE" "$index" ;;
    *) printf '%s%s' "$DEVICE" "$index" ;;
  esac
}

# ---------------------------------------------------------------------------
# The destruction gate. Read-only, fail-closed, and it names what it refused.
# ---------------------------------------------------------------------------

# Echoes one of: populated | clean | unknown
device_signature_state() {
  local out rc
  if ! command -v blkid >/dev/null 2>&1; then
    printf 'unknown'
    return 0
  fi
  set +e
  out="$(blkid -p -s TYPE -s PTTYPE -o value -- "$DEVICE" 2>/dev/null)"
  rc=$?
  set -e
  case "$rc" in
    0)
      if [ -n "$out" ]; then printf 'populated'; else printf 'clean'; fi
      ;;
    2) printf 'clean' ;;
    *) printf 'unknown' ;;
  esac
}

enforce_destruction_consent() {
  local state
  state="$(device_signature_state)"
  case "$state" in
    clean)
      note "=== [gate] ${DEVICE} carries no filesystem or partition table; no consent required"
      return 0
      ;;
    populated)
      note "=== [gate] ${DEVICE} already carries a filesystem or partition table"
      ;;
    *)
      note "=== [gate] could not determine what ${DEVICE} carries; treating it as populated"
      ;;
  esac
  if [ -z "$CONSENT" ]; then
    die "refusing to destroy ${DEVICE}: it already carries data and this invocation" \
      "carries no destruction consent. Re-run with --i-consent-to-destroy=${DEVICE}"
  fi
  if [ "$CONSENT" != "$DEVICE" ]; then
    die "refusing to destroy ${DEVICE}: --i-consent-to-destroy names ${CONSENT}," \
      "which is not the device being written. Consent must name ${DEVICE}"
  fi
  note "=== [gate] destruction consent names ${DEVICE}; proceeding"
}

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

main() {
  parse_args "$@"

  local p1 p2 esp uuid_root uuid_esp
  p1="$(partition_path 1)"
  p2="$(partition_path 2)"
  esp="${MNT}/boot/efi"

  if [ "$DRY_RUN" -eq 1 ]; then
    note "=== DRY RUN — every command below is printed and none is executed ==="
  fi
  note "=== target: ${DEVICE} (esp ${p1}, root ${p2}) release ${RELEASE} ==="

  # Before the gate, not after: a device that is not there at all must say so,
  # rather than reaching the gate, failing its probe, and being refused with
  # "it already carries data" — a true refusal for an untrue reason.
  if [ "$DRY_RUN" -eq 0 ] && [ ! -b "$DEVICE" ]; then
    die "${DEVICE} is not a block device"
  fi

  enforce_destruction_consent

  note "=== [1] unmount any auto-mounts on ${DEVICE} ==="
  run_optional umount -f "$p1"
  run_optional umount -f "$p2"

  note "=== [2] partition: GPT, 1G ESP + rest ext4 ==="
  run wipefs -a "$DEVICE"
  run sgdisk --zap-all "$DEVICE"
  run sgdisk -n 1:0:+1G -t 1:EF00 -c 1:RECOVERY-ESP "$DEVICE"
  run sgdisk -n 2:0:0 -t 2:8300 -c 2:RECOVERY-ROOT "$DEVICE"
  run partprobe "$DEVICE"
  run udevadm settle

  note "=== [3] filesystems ==="
  run mkfs.vfat -F 32 -n RECESP "$p1"
  run mkfs.ext4 -q -F -L RECOVERY-USB "$p2"

  note "=== [4] mount + debootstrap ${RELEASE} ==="
  run mkdir -p "$MNT"
  run mount "$p2" "$MNT"
  run debootstrap --arch=amd64 "$RELEASE" "$MNT" "$MIRROR"

  note "=== [5] base config ==="
  run mkdir -p "$esp"
  run mount "$p1" "$esp"
  uuid_root="$(probe '<ROOT-UUID-resolved-at-build-time>' blkid -s UUID -o value "$p2")"
  uuid_esp="$(probe '<ESP-UUID-resolved-at-build-time>' blkid -s UUID -o value "$p1")"

  write_file "${MNT}/etc/fstab" <<EOF
UUID=${uuid_root} / ext4 defaults,noatime 0 1
UUID=${uuid_esp} /boot/efi vfat umask=0077 0 1
EOF
  write_file "${MNT}/etc/hostname" <<'EOF'
recovery-usb
EOF
  write_file "${MNT}/etc/hosts" <<'EOF'
127.0.0.1 localhost
127.0.1.1 recovery-usb
EOF
  write_file "${MNT}/etc/apt/sources.list" <<EOF
deb ${MIRROR} ${RELEASE} main restricted universe multiverse
deb ${MIRROR} ${RELEASE}-updates main restricted universe multiverse
deb http://security.ubuntu.com/ubuntu ${RELEASE}-security main restricted universe multiverse
EOF
  run_optional cp /etc/resolv.conf "${MNT}/etc/resolv.conf"

  run mount --bind /dev "${MNT}/dev"
  run mount --bind /dev/pts "${MNT}/dev/pts"
  run mount --bind /proc "${MNT}/proc"
  run mount --bind /sys "${MNT}/sys"
  if [ "$DRY_RUN" -eq 0 ]; then
    trap cleanup_mounts EXIT
  fi

  note "=== [6] install packages (kernel, grub, desktop, sshd, storage tools) ==="
  run_chroot <<'CHROOT'
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q locales
locale-gen en_US.UTF-8
apt-get install -y -q linux-generic grub-efi-amd64 grub-efi-amd64-signed shim-signed efibootmgr
apt-get install -y -q openssh-server sudo network-manager
apt-get install -y -q lvm2 mdadm gdisk parted dosfstools smartmontools nvme-cli ipmitool rsync pciutils usbutils debootstrap curl wget vim less htop
apt-get install -y -q ubuntu-desktop-minimal
echo 'root:password' | chpasswd
cat > /etc/ssh/sshd_config.d/99-recovery.conf <<EOF
PermitRootLogin yes
PasswordAuthentication yes
EOF
cat > /etc/sudoers.d/99-recovery <<EOF
root ALL=(ALL) NOPASSWD:ALL
%sudo ALL=(ALL) NOPASSWD:ALL
EOF
chmod 440 /etc/sudoers.d/99-recovery
mkdir -p /etc/netplan
cat > /etc/netplan/01-recovery.yaml <<EOF
network:
  version: 2
  renderer: NetworkManager
EOF
chmod 600 /etc/netplan/01-recovery.yaml
systemctl enable ssh NetworkManager
echo 'GRUB_DISABLE_OS_PROBER=true' >> /etc/default/grub
sed -i 's/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT=3/' /etc/default/grub || true
grub-install --target=x86_64-efi --efi-directory=/boot/efi --boot-directory=/boot --removable --no-nvram
update-grub
CHROOT

  note "=== [7] BOOT FIX 1: copy the kernel and initrd from /boot onto the ESP ==="
  note "===     Ubuntu's signed GRUB cannot read resolute's ext4; it must load"
  note "===     both from the FAT32 ESP, and only the kernel mounts the ext4."
  run_chroot <<'CHROOT'
KVER="$(ls -1 /boot/vmlinuz-* | sed 's|^/boot/vmlinuz-||' | sort -V | tail -n 1)"
test -n "$KVER"
cp -f "/boot/vmlinuz-$KVER" /boot/efi/vmlinuz
cp -f "/boot/initrd.img-$KVER" /boot/efi/initrd.img
sync
CHROOT

  note "=== [8] BOOT FIX 2: write the menu at ESP:/boot/grub/grub.cfg ==="
  note "===     grub-install --removable installs the CD-variant GRUB, whose"
  note "===     baked-in config path is /boot/grub/grub.cfg ON THE ESP; it"
  note "===     ignores EFI/ubuntu/grub.cfg and EFI/BOOT/grub.cfg."
  run mkdir -p "${esp}/boot/grub"
  write_file "${esp}/boot/grub/grub.cfg" <<EOF
set timeout=3
search.fs_uuid ${uuid_esp} root
menuentry "Ubuntu Desktop Recovery USB" {
  linux /vmlinuz root=UUID=${uuid_root} rw${CMDLINE_EXTRA:+ ${CMDLINE_EXTRA}}
  initrd /initrd.img
}
EOF

  note "=== [9] copy perccli onto the stick ==="
  if [ "$DRY_RUN" -eq 1 ] || [ -d "$PERCCLI_SOURCE" ]; then
    run mkdir -p "${MNT}/opt"
    run cp -a "$PERCCLI_SOURCE" "${MNT}/opt/"
  else
    note "=== [9] ${PERCCLI_SOURCE} absent on this host; perccli not copied ==="
  fi

  note "=== [10] drop a README for the rebuild window ==="
  write_file "${MNT}/root/README-RECOVERY.md" <<'EOF'
Ubuntu Desktop Recovery USB
- login: root / password  (sshd: PasswordAuthentication+PermitRootLogin yes)
- DHCP on all NICs via NetworkManager; the LAN reservation is MAC-bound, so
  the stick inherits each host's reserved address (192.168.1.200 on poweredge)
- tools: lvm2 mdadm gdisk parted smartmontools nvme-cli ipmitool rsync debootstrap
- perccli at /opt/MegaRAID/perccli/perccli64
- the Toshiba backup + restore.sh mount at /mnt/usb-backup (label POWEREDGE-BACKUP)

AFTER ANY KERNEL UPGRADE ON THIS STICK, re-copy the kernel and initrd to the
ESP or the stick keeps booting the old kernel:

    KVER=$(ls -1 /boot/vmlinuz-* | sed 's|^/boot/vmlinuz-||' | sort -V | tail -n 1)
    cp -f "/boot/vmlinuz-$KVER"   /boot/efi/vmlinuz
    cp -f "/boot/initrd.img-$KVER" /boot/efi/initrd.img
    sync

GRUB never reads this stick's ext4 — it loads /vmlinuz and /initrd.img from
the ESP, and its menu lives at ESP:/boot/grub/grub.cfg and nowhere else.
EOF

  note "=== [11] unmount cleanly ==="
  run sync
  run umount "${MNT}/dev/pts"
  run umount "${MNT}/dev"
  run umount "${MNT}/proc"
  run umount "${MNT}/sys"
  run umount "$esp"
  run umount "$MNT"
  if [ "$DRY_RUN" -eq 0 ]; then
    trap - EXIT
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    note "=== DRY RUN COMPLETE — nothing was executed ==="
  else
    note "=== BUILD COMPLETE ==="
  fi
}

main "$@"
