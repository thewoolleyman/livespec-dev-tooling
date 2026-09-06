#!/usr/bin/env bash
# base-os-install-exit-tests.sh — prove the properties the bare-metal base-OS
# stage is required to have, WITHOUT touching any host.
#
#   1. `--dry-run` against the committed poweredge profile emits the mount,
#      debootstrap, fstab, chroot package-install, initramfs and bootloader
#      commands IN THAT ORDER, and executes none of them;
#   2. the /etc/fstab it renders finds root and the EFI system partition by
#      LABEL and carries the ci-cache, ci-containerd and ci-workvols lines
#      BYTE-EXACT with the five ../phase2/storage-layout/install-storage-layout.sh
#      ensures — so the later stage finds its own layout already present;
#   3. lvm2 is installed INSIDE the chroot and the initramfs is regenerated
#      afterwards with LVM support, which is the bootability fix the 2026-09-04
#      hand rebuild needed;
#   4. a root logical volume already carrying the profile's release is left
#      alone and reported, and one carrying anything else is REFUSED unless the
#      invocation names it in --i-consent-to-destroy;
#   5. the script holds no node-specific literal: every one comes from the
#      profile.
#
# HOW IT STAYS OFF THE HOST. Every case runs `base-os-install.sh --dry-run`, so
# no mutating command is ever executed by construction. On top of that each case
# prepends a scratch directory of FAKE tools to PATH in which every MUTATING
# command the script can reach (`vgchange`, `mount`, `umount`, `mkdir`,
# `debootstrap`, `chroot`) is a TRIPWIRE that appends to a file and exits 0, so
# a dry run that executed anything leaves the tripwire file non-empty — which
# case E asserts it does not. The cases that need the script to SEE a populated
# root volume pass `--mount-root=` a scratch directory they filled themselves;
# under `--dry-run` the mount is only printed, so that directory is exactly what
# the release check reads.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/base-os-install.sh"
POWEREDGE="${HERE}/profiles/poweredge-xubuntu.env"
STORAGE_LAYOUT_INSTALLER="${HERE}/../phase2/storage-layout/install-storage-layout.sh"

pass=0; fail=0
ok() { printf '  PASS  %s\n' "$1"; pass=$((pass + 1)); }
no() { printf '  FAIL  %s\n' "$1"; fail=$((fail + 1)); }

TMPROOT="$(mktemp -d)"
case "$TMPROOT" in
  /tmp/*|/var/tmp/*) ;;
  *) echo "FATAL: mktemp -d returned an unexpected path '${TMPROOT}'" >&2; exit 1 ;;
esac
cleanup() { rm -rf "$TMPROOT"; }
trap cleanup EXIT

TRIPWIRE="${TMPROOT}/tripwire"
: > "$TRIPWIRE"
export TRIPWIRE

# ---------------------------------------------------------------------------
# Fake-tool scaffolding
# ---------------------------------------------------------------------------
mkfake() {  # mkfake DIR NAME BODY
  printf '#!/usr/bin/env bash\n%s\n' "$3" > "${1}/${2}"
  chmod +x "${1}/${2}"
}

# A scratch PATH directory in which every mutating command is a tripwire and
# every probe reports "nothing there" — i.e. a node fresh out of stage 1.
make_bare_fakes() {  # make_bare_fakes DIR
  local dir="$1" tool
  mkdir -p "$dir"
  for tool in vgchange mount umount mkdir debootstrap chroot; do
    # Single-quoted on purpose: the body is the FAKE's source, expanded when
    # the fake runs, not when this suite writes it.
    mkfake "$dir" "$tool" 'printf "%s %s\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"; exit 0'
  done
  # The read-only probes. A bare `efibootmgr` LISTS the firmware entries and is
  # a probe, not a mutation — the entry-creating call goes through `chroot`,
  # which is a tripwire above. Both report "nothing there".
  for tool in findmnt efibootmgr; do
    mkfake "$dir" "$tool" 'exit 1'
  done
}

run_install() {  # run_install FAKEDIR ARGS... -> output in REPLY_OUT, code in REPLY_RC
  local dir="$1"; shift
  REPLY_OUT="$(PATH="${dir}:${PATH}" "$SCRIPT" "$@" 2>&1)"
  REPLY_RC=$?
}

# order_ok OUTPUT PATTERN... — every pattern present, and each strictly after
# the one before it.
order_ok() {
  local out="$1"; shift
  local prev=0 pat idx
  for pat in "$@"; do
    idx="$(printf '%s\n' "$out" | grep -nF -- "$pat" | head -1 | cut -d: -f1)"
    if [ -z "$idx" ]; then
      printf '        missing line: %s\n' "$pat"
      return 1
    fi
    if [ "$idx" -le "$prev" ]; then
      printf '        out of order: %s\n' "$pat"
      return 1
    fi
    prev="$idx"
  done
  return 0
}

BARE="${TMPROOT}/bare-bin"
make_bare_fakes "$BARE"

# ---------------------------------------------------------------------------
echo "== A. --dry-run against the committed poweredge profile, in order =="
# ---------------------------------------------------------------------------

run_install "$BARE" --dry-run "$POWEREDGE"
POWEREDGE_OUT="$REPLY_OUT"
POWEREDGE_RC="$REPLY_RC"

if [ "$POWEREDGE_RC" -eq 0 ]; then
  ok "A1  exits 0"
else
  no "A1  exits 0 (rc=${POWEREDGE_RC})"
  printf '%s\n' "$POWEREDGE_OUT"
fi

# The ordering claim, with the values this node's profile records: the root
# logical volume of volume group `poweredge` and the ESP at /dev/sda1; the
# pinned release `resolute`; the fstab; the chroot package install; the
# initramfs; and the bootloader onto the ESP.
if order_ok "$POWEREDGE_OUT" \
    'mount /dev/poweredge/root /mnt/target' \
    'mount /dev/sda1 /mnt/target/boot/efi' \
    'debootstrap --arch=amd64 --components=main,restricted,universe,multiverse resolute /mnt/target http://archive.ubuntu.com/ubuntu' \
    'write /mnt/target/etc/fstab' \
    'chroot /mnt/target env DEBIAN_FRONTEND=noninteractive apt-get install' \
    'chroot /mnt/target dracut --force --regenerate-all --add lvm' \
    'chroot /mnt/target grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=ubuntu --uefi-secure-boot --recheck'; then
  ok "A2  mount, debootstrap, fstab, chroot install, initramfs, bootloader — in that order"
else
  no "A2  mount, debootstrap, fstab, chroot install, initramfs, bootloader — in that order"
fi

if printf '%s' "$POWEREDGE_OUT" | grep -qF 'chroot /mnt/target efibootmgr --create --disk=/dev/sda --part=1 --label=ubuntu --loader=\EFI\ubuntu\shimx64.efi'; then
  ok "A3  the firmware boot entry is registered on the profile's disk and ESP partition"
else
  no "A3  the firmware boot entry is registered on the profile's disk and ESP partition"
fi

if printf '%s' "$POWEREDGE_OUT" | grep -qF 'write /mnt/target/etc/hostname' \
   && printf '%s' "$POWEREDGE_OUT" | grep -qF 'poweredge-xubuntu' \
   && printf '%s' "$POWEREDGE_OUT" | grep -qF 'chroot /mnt/target useradd --create-home --shell /bin/bash --groups=sudo ci-admin'; then
  ok "A4  the hostname and the operator account come from the profile"
else
  no "A4  the hostname and the operator account come from the profile"
fi

# NODE_ADDRESS=auto in this profile, so the node pins nothing and takes a lease
# — which is what ../provision-k3s.sh assumes by passing no --node-ip.
if printf '%s' "$POWEREDGE_OUT" | grep -qF 'write /mnt/target/etc/netplan/10-ci-runner.yaml' \
   && printf '%s' "$POWEREDGE_OUT" | grep -qF 'dhcp4: true'; then
  ok "A5  the profile's network address (auto) is rendered as a lease"
else
  no "A5  the profile's network address (auto) is rendered as a lease"
fi

# ---------------------------------------------------------------------------
echo
echo "== B. The rendered fstab finds everything by LABEL =="
# ---------------------------------------------------------------------------

if printf '%s' "$POWEREDGE_OUT" | grep -qF 'LABEL=root / ext4 defaults 0 1' \
   && printf '%s' "$POWEREDGE_OUT" | grep -qF 'LABEL=ESP /boot/efi vfat umask=0077 0 1'; then
  ok "B1  root and the EFI system partition are mounted by LABEL"
else
  no "B1  root and the EFI system partition are mounted by LABEL"
fi

if printf '%s' "$POWEREDGE_OUT" | grep -qF 'LABEL=swap none swap sw 0 0'; then
  ok "B2  the profile's swap volume is enabled by LABEL"
else
  no "B2  the profile's swap volume is enabled by LABEL"
fi

# The three tier lines and the two binds, byte-exact. install-storage-layout.sh
# builds the same five from its own constants; if these drift, stage 4 of the
# rebuild stops being the no-op it is designed to be on a conforming host.
FSTAB_TIER_LINES=(
  'LABEL=ci-cache /var/cache/ci-runner ext4 defaults,noatime 0 2'
  'LABEL=ci-containerd /var/cache/ci-runner/k3s-containerd ext4 defaults,noatime,x-systemd.requires-mounts-for=/var/cache/ci-runner 0 2'
  'LABEL=ci-workvols /var/cache/ci-runner/k3s-storage xfs defaults,noatime,x-systemd.requires-mounts-for=/var/cache/ci-runner 0 2'
  '/var/cache/ci-runner/k3s-containerd /var/lib/rancher/k3s/agent/containerd none bind,x-systemd.requires-mounts-for=/var/cache/ci-runner/k3s-containerd 0 0'
  '/var/cache/ci-runner/k3s-storage /var/lib/rancher/k3s/storage none bind,x-systemd.requires-mounts-for=/var/cache/ci-runner/k3s-storage 0 0'
)
missing=""
for line in "${FSTAB_TIER_LINES[@]}"; do
  printf '%s' "$POWEREDGE_OUT" | grep -qF -- "$line" || missing="${missing}
        ${line}"
done
if [ -z "$missing" ]; then
  ok "B3  the five tier lines install-storage-layout.sh ensures are all rendered"
else
  no "B3  the five tier lines install-storage-layout.sh ensures are all rendered:${missing}"
fi

# And the same five, read out of that installer, so the byte-exactness claim is
# checked against the other side rather than against a second copy of it here.
if [ -r "$STORAGE_LAYOUT_INSTALLER" ]; then
  drift=""
  for line in "${FSTAB_TIER_LINES[@]}"; do
    expanded="$(printf '%s' "$line" \
      | sed 's|/var/cache/ci-runner/k3s-containerd|${CONTAINERD_SRC}|g; s|/var/cache/ci-runner/k3s-storage|${STORAGE_SRC}|g; s|/var/lib/rancher/k3s/agent/containerd|${CONTAINERD_DIR}|g; s|/var/lib/rancher/k3s/storage|${STORAGE_DIR}|g; s|/var/cache/ci-runner|${CACHE_MOUNT}|g; s|LABEL=ci-cache|LABEL=${LABEL_CACHE}|; s|LABEL=ci-containerd|LABEL=${LABEL_CONTAINERD}|; s|LABEL=ci-workvols|LABEL=${LABEL_WORKVOLS}|')"
    grep -qF -- "ensure_line \"${expanded}\"" "$STORAGE_LAYOUT_INSTALLER" || drift="${drift}
        ${expanded}"
  done
  if [ -z "$drift" ]; then
    ok "B4  each of those five is the line install-storage-layout.sh itself ensures"
  else
    no "B4  a tier line has drifted from install-storage-layout.sh:${drift}"
  fi
else
  no "B4  install-storage-layout.sh not readable at ${STORAGE_LAYOUT_INSTALLER}"
fi

# ---------------------------------------------------------------------------
echo
echo "== C. lvm2 in the chroot, then the initramfs — the bootability fix =="
# ---------------------------------------------------------------------------

if order_ok "$POWEREDGE_OUT" \
    'apt-get install --yes --no-install-recommends linux-image-generic lvm2' \
    'dracut --force --regenerate-all --add lvm'; then
  ok "C1  lvm2 is installed in the chroot BEFORE the initramfs is regenerated"
else
  no "C1  lvm2 is installed in the chroot BEFORE the initramfs is regenerated"
fi

# The recorded end state of the 2026-09-04 rebuild, derived here from the
# profile's ROOT_LABEL rather than written down: root=/dev/mapper/poweredge-root.
if printf '%s' "$POWEREDGE_OUT" | grep -qF 'GRUB_CMDLINE_LINUX="root=/dev/mapper/poweredge-root rd.lvm.lv=poweredge/root"'; then
  ok "C2  the bootloader gets root by its LVM id, and the volume to activate"
else
  no "C2  the bootloader gets root by its LVM id, and the volume to activate"
fi

# ---------------------------------------------------------------------------
echo
echo "== D. Re-runs and the consent refusal =="
# ---------------------------------------------------------------------------

# A root volume already carrying the profile's release. Under --dry-run the
# mount is only printed, so --mount-root points the release check at a scratch
# directory this case filled — no host, no block device.
SAME="${TMPROOT}/same-release"
mkdir -p "${SAME}/etc"
printf 'ID=ubuntu\nVERSION_CODENAME=resolute\n' > "${SAME}/etc/os-release"
run_install "$BARE" --dry-run "--mount-root=${SAME}" "$POWEREDGE"
if [ "$REPLY_RC" -eq 0 ] \
   && printf '%s' "$REPLY_OUT" | grep -qF 'already carries ubuntu resolute' \
   && ! printf '%s' "$REPLY_OUT" | grep -qF '+ debootstrap'; then
  ok "D1  a root volume already carrying the profile's release is left alone and reported"
else
  no "D1  a root volume already carrying the profile's release is left alone and reported (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

# A root volume carrying a DIFFERENT release: overwriting it is destructive.
OTHER="${TMPROOT}/other-release"
mkdir -p "${OTHER}/etc"
printf 'ID=ubuntu\nVERSION_CODENAME=noble\n' > "${OTHER}/etc/os-release"
run_install "$BARE" --dry-run "--mount-root=${OTHER}" "$POWEREDGE"
if [ "$REPLY_RC" -ne 0 ] \
   && printf '%s' "$REPLY_OUT" | grep -qF 'REFUSED' \
   && printf '%s' "$REPLY_OUT" | grep -qF '/dev/poweredge/root'; then
  ok "D2  overwriting a populated root volume without consent exits non-zero and names the volume"
else
  no "D2  overwriting a populated root volume without consent exits non-zero and names the volume (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

run_install "$BARE" --dry-run "--mount-root=${OTHER}" --i-consent-to-destroy=/dev/poweredge/ci-cache "$POWEREDGE"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF 'REFUSED'; then
  ok "D3  consent naming a DIFFERENT volume does not grant this one"
else
  no "D3  consent naming a DIFFERENT volume does not grant this one (rc=${REPLY_RC})"
fi

run_install "$BARE" --dry-run "--mount-root=${OTHER}" --i-consent-to-destroy=/dev/poweredge/root "$POWEREDGE"
if [ "$REPLY_RC" -eq 0 ] \
   && printf '%s' "$REPLY_OUT" | grep -qF 'consent given for /dev/poweredge/root' \
   && printf '%s' "$REPLY_OUT" | grep -qF '+ debootstrap'; then
  ok "D4  consent naming exactly that volume lets the install through"
else
  no "D4  consent naming exactly that volume lets the install through (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

# A root volume with content but no /etc/os-release at all is still populated,
# and is still refused — the refusal must not depend on recognising a release.
UNKNOWN="${TMPROOT}/unknown-content"
mkdir -p "${UNKNOWN}/srv"
run_install "$BARE" --dry-run "--mount-root=${UNKNOWN}" "$POWEREDGE"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF '/dev/poweredge/root'; then
  ok "D5  a populated root volume with no recognisable release is refused too"
else
  no "D5  a populated root volume with no recognisable release is refused too (rc=${REPLY_RC})"
fi

# ---------------------------------------------------------------------------
echo
echo "== E. --dry-run executes nothing, and the script holds no node value =="
# ---------------------------------------------------------------------------

if [ ! -s "$TRIPWIRE" ]; then
  ok "E1  no mutating command ran in any of the dry runs above"
else
  no "E1  a dry run EXECUTED a mutating command:"
  cat "$TRIPWIRE"
fi

# Every node-specific value the dry run printed came from the profile, so none
# of them may appear in the script itself. `poweredge` is deliberately in the
# list even though it is also this repository's shorthand for the node.
node_literals=(poweredge-xubuntu /dev/sda nvmea resolute ci-admin WD_BLACK)
found=""
for literal in "${node_literals[@]}"; do
  if grep -qF -- "$literal" "$SCRIPT"; then
    found="${found} ${literal}"
  fi
done
if [ -z "$found" ]; then
  ok "E2  base-os-install.sh contains no node-specific literal of its own"
else
  no "E2  base-os-install.sh contains node-specific literal(s):${found}"
fi

# A profile the shared parser rejects is rejected identically by this stage.
p="${TMPROOT}/unknown-key.env"
cp "$POWEREDGE" "$p"
printf 'NOT_A_PROFILE_KEY=x\n' >> "$p"
run_install "$BARE" --dry-run "$p"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF "unknown profile key 'NOT_A_PROFILE_KEY'"; then
  ok "E3  the profile is validated as data by the parser every stage shares"
else
  no "E3  the profile is validated as data by the parser every stage shares (rc=${REPLY_RC})"
fi

echo
printf 'phase0 base-os-install: %d pass / %d fail\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
