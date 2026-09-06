#!/usr/bin/env bash
# base-os-install.sh — STAGE 2 of the bare-metal rebuild of a CI runner pool
# node: take the volumes stage 1 created to an INSTALLED OPERATING SYSTEM that
# boots on its own, which is the precondition the k3s stage and the node-local
# runbook assume and never establish
# (SPECIFICATION/non-functional-requirements.md §"Runner-pool node rebuild
# recipe": "whose preconditions (an installed operating system; an installed
# k3s and its admin kubeconfig) the bare-metal stage MUST establish").
#
# WHAT IT REPLACES. On 2026-09-04 this whole stage was hand-run from the
# Recovery USB, and the node then would not boot until `lvm2` was installed
# INSIDE the chroot and the initramfs regenerated, so that the root volume
# group activates before the root filesystem is looked for (the
# "lvm2-in-chroot plus dracut bootability fix" of that day). Only the END STATE
# was recorded — an ESP entry chaining a signed shim to GRUB to
# `root=/dev/mapper/<vg>-<root>` — in the per-host information repository. The
# specification section above forbids treating a restore image as the way a
# node's configuration is reproduced, so the procedure is here, in git, and the
# bootability fix is stages 7 and 8 rather than a remembered afterthought.
#
# WHERE IT SITS. It runs from the Recovery USB against a node whose storage
# layout stage has completed, and BEFORE `../provision-k3s.sh`. The `/etc/fstab`
# it writes carries the same five tier lines
# `../phase2/storage-layout/install-storage-layout.sh` ensures, BYTE-EXACT, so
# that stage 4's installer finds its own layout already present and is the
# no-op it is designed to be on a conforming host. Those five lines are
# co-maintained with that script; changing one means changing both.
#
# PROCEDURE HERE, DATA IN THE PROFILE. The release, the mirrors, the kernel
# package, the initramfs generator, the root and swap volumes, the EFI system
# partition, the hostname, the network address, the operator account and the
# firmware boot entry's label are all read from the profile named on the
# command line (`profiles/<node>.env`, parsed by the shared `profile.sh`). This
# script contains no value that belongs to one node.
#
# RE-RUNNABLE. A root volume already carrying the profile's release is LEFT
# ALONE and reported — the debootstrap is skipped and the remaining steps, each
# of which converges rather than appends, bring the rest of the configuration
# up to date. Against a node already in its profile's declared state the whole
# run changes nothing.
#
# DESTRUCTIVE ONLY ON CONSENT. Overwriting a POPULATED root volume that carries
# something other than the profile's release REFUSES unless the invocation
# carries `--i-consent-to-destroy=<logical-volume>` naming that exact volume,
# and the refusal names it.
#
# --dry-run PRINTS AND EXECUTES NOTHING. Read-only probes still run; every
# mutating command is printed with a leading `+ ` and every file write with
# `+ write`, and nothing is executed. Because the mount in stage 1 is only
# PRINTED under `--dry-run`, the release check in stage 2 reads whatever is
# already at the mount root — which is also how the exit tests beside this
# script inject a populated root volume without touching a host.
#
# Usage:
#   base-os-install.sh --dry-run profiles/<node>.env
#   sudo base-os-install.sh [--i-consent-to-destroy=LV]... profiles/<node>.env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "$0")"
DRY_RUN=0
PROFILE_PATH=""
CONSENT=()
CHANGES=0

# The scratch directory the target root is mounted at while it is being built.
# Not a node value: it exists only for the duration of a run. `--mount-root`
# moves it for a Recovery USB whose layout differs.
MOUNT_ROOT="/mnt/target"

# The five tier lines this stage renders into the target's /etc/fstab are the
# five ../phase2/storage-layout/install-storage-layout.sh ensures. These
# mountpoints are FLEET constants, not node values — the same on every pool
# node — and are co-maintained with that script.
CACHE_MOUNT="/var/cache/ci-runner"
CONTAINERD_SRC="${CACHE_MOUNT}/k3s-containerd"
STORAGE_SRC="${CACHE_MOUNT}/k3s-storage"
CONTAINERD_DIR="/var/lib/rancher/k3s/agent/containerd"
STORAGE_DIR="/var/lib/rancher/k3s/storage"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }
stage() { printf '\n== %s ==\n' "$*"; }

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} [--dry-run] [--mount-root=DIR] [--i-consent-to-destroy=LV]... PROFILE

  --dry-run                 Print every command and file write; run none.
  --mount-root=DIR          Build the target root at DIR (default ${MOUNT_ROOT}).
  --i-consent-to-destroy=LV Permit overwriting the populated root logical
                            volume LV, exactly as a refusal names it.
  PROFILE                   Path to the node's profiles/<node>.env.
EOF
}

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --mount-root=*) MOUNT_ROOT="${1#*=}" ;;
    --i-consent-to-destroy=*) CONSENT+=("${1#*=}") ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) usage >&2; die "unknown option '$1'" ;;
    *)
      if [ -n "$PROFILE_PATH" ]; then
        die "more than one profile given ('${PROFILE_PATH}' and '$1')"
      fi
      PROFILE_PATH="$1" ;;
  esac
  shift
done
if [ -z "$PROFILE_PATH" ]; then
  usage >&2
  die "no profile given"
fi
MOUNT_ROOT="${MOUNT_ROOT%/}"
[ -n "$MOUNT_ROOT" ] || die "--mount-root must not be the filesystem root"

# ---------------------------------------------------------------------------
# Profile: parsed, never sourced — by the parser every stage in this directory
# shares, so the format cannot drift between stages.
# ---------------------------------------------------------------------------
# shellcheck source=ci-runner/k3s/phase0-bare-metal/profile.sh
source "${SCRIPT_DIR}/profile.sh"
profile_load "$PROFILE_PATH"

# ---------------------------------------------------------------------------
# Execution, probing and consent — the same three primitives stage 1 uses.
# ---------------------------------------------------------------------------

# run — the ONE place a mutating command is either printed or executed.
run() {
  printf '+'
  printf ' %s' "$@"
  printf '\n'
  if [ "$DRY_RUN" -eq 0 ]; then
    "$@"
  fi
  CHANGES=$((CHANGES + 1))
}

# write_file PATH CONTENT [MODE] — the ONE place a FILE is either printed or
# written. A file that already carries exactly this content is reported and
# left alone, which is most of what makes the stage re-runnable.
write_file() {
  local path="$1" content="$2" mode="${3:-0644}"
  if [ -f "$path" ] && [ "$(< "$path")" = "$content" ]; then
    note "no change: ${path} already carries the declared content"
    return 0
  fi
  printf '+ write %s (mode %s)\n' "$path" "$mode"
  printf '%s\n' "$content" | sed 's/^/+   | /'
  if [ "$DRY_RUN" -eq 0 ]; then
    mkdir -p "$(dirname "$path")"
    printf '%s\n' "$content" > "$path"
    chmod "$mode" "$path"
  fi
  CHANGES=$((CHANGES + 1))
}

have() { command -v "$1" >/dev/null 2>&1; }

# probe — a READ-ONLY command whose absence is not an error. A missing tool
# yields empty output, which every caller reads as "absent".
probe() {
  if ! have "$1"; then
    return 0
  fi
  "$@" 2>/dev/null || true
}

consented() {
  local want="$1" granted
  for granted in ${CONSENT[@]+"${CONSENT[@]}"}; do
    if [ "$granted" = "$want" ]; then
      return 0
    fi
  done
  return 1
}

# require_consent TARGET WHAT — refuse, naming the target, unless the operator
# consented to destroying exactly it.
require_consent() {
  local target="$1" what="$2"
  if consented "$target"; then
    note "consent given for ${target}: proceeding to ${what}"
    return 0
  fi
  printf 'REFUSED: %s would destroy %s, which is not empty.\n' "$SCRIPT_NAME" "$target" >&2
  printf '         %s\n' "$what" >&2
  printf '         Re-run with --i-consent-to-destroy=%s if that is what you want.\n' "$target" >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Values derived from the profile
# ---------------------------------------------------------------------------
lv_device() {  # lv_device LABEL -> /dev/<vg>/<lv> for the volume carrying LABEL
  local label="$1"
  [ -n "${LV_OF_LABEL[$label]:-}" ] || die "${PROFILE_PATH}: no LOGICAL_VOLUMES record carries the label '${label}'"
  printf '/dev/%s/%s' "${LV_OF_LABEL[$label]}" "${LV_NAME_OF_LABEL[$label]}"
}

# device-mapper escapes a literal '-' in a volume-group or logical-volume name
# by doubling it, which is why the recorded root= of the 2026-09-04 rebuild is
# a /dev/mapper path and not a /dev/<vg>/<lv> one.
dm_escape() { printf '%s' "${1//-/--}"; }

ROOT_LABEL="${CFG[ROOT_LABEL]}"
ROOT_VG="${LV_OF_LABEL[$ROOT_LABEL]:-}"
[ -n "$ROOT_VG" ] || die "${PROFILE_PATH}: ROOT_LABEL='${ROOT_LABEL}' names no LOGICAL_VOLUMES record"
ROOT_LV="${LV_NAME_OF_LABEL[$ROOT_LABEL]}"
ROOT_FSTYPE="${LV_FSTYPE_OF_LABEL[$ROOT_LABEL]}"
ROOT_DEVICE="$(lv_device "$ROOT_LABEL")"
ROOT_DM="/dev/mapper/$(dm_escape "$ROOT_VG")-$(dm_escape "$ROOT_LV")"

RELEASE="${CFG[OS_RELEASE]}"
ESP_MOUNT="${MOUNT_ROOT}/boot/efi"

# The architecture decides the GRUB package, the EFI platform and the shim the
# firmware entry points at; nothing else in this script is architecture-aware.
case "${CFG[OS_ARCHITECTURE]}" in
  amd64) GRUB_PACKAGE=grub-efi-amd64; GRUB_PLATFORM=x86_64-efi; SHIM_BINARY=shimx64.efi ;;
  arm64) GRUB_PACKAGE=grub-efi-arm64; GRUB_PLATFORM=arm64-efi; SHIM_BINARY=shimaa64.efi ;;
  *) die "${PROFILE_PATH}: OS_ARCHITECTURE='${CFG[OS_ARCHITECTURE]}' is not one this stage knows how to boot (amd64, arm64)" ;;
esac

case "${CFG[OS_DISTRIBUTION]}" in
  ubuntu) ARCHIVE_KEYRING=/usr/share/keyrings/ubuntu-archive-keyring.gpg ;;
  debian) ARCHIVE_KEYRING=/usr/share/keyrings/debian-archive-keyring.gpg ;;
  *) die "${PROFILE_PATH}: OS_DISTRIBUTION='${CFG[OS_DISTRIBUTION]}' is not one this stage knows how to debootstrap (ubuntu, debian)" ;;
esac

# The EFI system partition's number, read off the device path stage 1's fixed
# structure put it at, so an NVMe node's `...p1` needs no second rule.
ESP_PART="${CFG[ESP_DEVICE]##*[!0-9]}"
[ -n "$ESP_PART" ] || die "${PROFILE_PATH}: ESP_DEVICE='${CFG[ESP_DEVICE]}' does not end in a partition number"

if [ "$DRY_RUN" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
  die "must run as root (it mounts volumes, debootstraps and writes a bootloader). Use --dry-run to see the plan unprivileged."
fi

note "profile:  ${PROFILE_PATH}"
note "node:     ${CFG[NODE_NAME]}"
note "release:  ${CFG[OS_DISTRIBUTION]} ${RELEASE} (${CFG[OS_ARCHITECTURE]})"
note "root:     ${ROOT_DEVICE} (${ROOT_FSTYPE}), mounted at ${MOUNT_ROOT}"
if [ "$DRY_RUN" -eq 1 ]; then
  note "mode:     DRY RUN — every '+ ' line is printed and executed by nothing"
else
  note "mode:     LIVE"
fi

# ---------------------------------------------------------------------------
stage "1/10 mount the root logical volume and the EFI system partition"
# ---------------------------------------------------------------------------
# Stage 1 leaves the volume groups created but not necessarily activated: a
# Recovery USB that has just rebooted sees the physical volumes and no device
# nodes. Activate only the groups this node's profile declares. A group counts
# as active when every logical volume the profile puts in it has a device node,
# which is the state the mounts below actually need.
vg_active() {
  local vg="$1" record rec_vg rec_lv
  for record in "${LV_RECORDS[@]}"; do
    IFS=: read -r rec_vg rec_lv _ <<< "$record"
    [ "$rec_vg" = "$vg" ] || continue
    [ -b "/dev/${vg}/${rec_lv}" ] || return 1
  done
  return 0
}
for vg in "${VG_NAMES[@]}"; do
  if vg_active "$vg"; then
    note "no change: every logical volume of volume group ${vg} is already active"
    continue
  fi
  run vgchange --activate y "$vg"
done

if [ -n "$(probe findmnt --noheadings --output TARGET --mountpoint "$MOUNT_ROOT")" ]; then
  note "no change: ${MOUNT_ROOT} is already a mountpoint"
else
  run mkdir -p "$MOUNT_ROOT"
  run mount "$ROOT_DEVICE" "$MOUNT_ROOT"
fi

if [ -n "$(probe findmnt --noheadings --output TARGET --mountpoint "$ESP_MOUNT")" ]; then
  note "no change: ${ESP_MOUNT} is already a mountpoint"
else
  run mkdir -p "$ESP_MOUNT"
  run mount "${CFG[ESP_DEVICE]}" "$ESP_MOUNT"
fi

# ---------------------------------------------------------------------------
stage "2/10 decide: fresh install, re-run, or refusal"
# ---------------------------------------------------------------------------
installed_release=""
if [ -r "${MOUNT_ROOT}/etc/os-release" ]; then
  installed_release="$(awk -F= '$1 == "VERSION_CODENAME" { gsub(/"/, "", $2); print $2 }' "${MOUNT_ROOT}/etc/os-release")"
fi
root_populated=0
if [ -n "$(find "$MOUNT_ROOT" -mindepth 1 -maxdepth 1 ! -name 'lost+found' -print -quit 2>/dev/null)" ]; then
  root_populated=1
fi

DEBOOTSTRAP=1
if [ -n "$installed_release" ] && [ "$installed_release" = "$RELEASE" ]; then
  DEBOOTSTRAP=0
  note "no change: ${ROOT_DEVICE} already carries ${CFG[OS_DISTRIBUTION]} ${RELEASE}; leaving it alone"
  note "           (the steps below converge the rest of the configuration on it)"
elif [ "$root_populated" -eq 1 ]; then
  if [ -n "$installed_release" ]; then
    require_consent "$ROOT_DEVICE" \
      "the ${CFG[OS_DISTRIBUTION]} ${installed_release} installation on ${ROOT_DEVICE} is overwritten by a fresh ${RELEASE} one"
  else
    require_consent "$ROOT_DEVICE" \
      "the existing contents of ${ROOT_DEVICE} are overwritten by a fresh ${CFG[OS_DISTRIBUTION]} ${RELEASE} installation"
  fi
else
  note "${ROOT_DEVICE} is empty: a fresh ${CFG[OS_DISTRIBUTION]} ${RELEASE} installation destroys nothing"
fi

# ---------------------------------------------------------------------------
stage "3/10 debootstrap ${CFG[OS_DISTRIBUTION]} ${RELEASE} into ${MOUNT_ROOT}"
# ---------------------------------------------------------------------------
if [ "$DEBOOTSTRAP" -eq 0 ]; then
  note "skipped: the release the profile pins is already installed"
else
  components="${CFG[OS_COMPONENTS]// /,}"
  run debootstrap \
    "--arch=${CFG[OS_ARCHITECTURE]}" \
    "--components=${components}" \
    "$RELEASE" "$MOUNT_ROOT" "${CFG[OS_MIRROR]}"
fi

# The apt sources debootstrap leaves behind carry only the components it was
# given and no -updates or -security suite, so the kernel and bootloader would
# be installed at release-day versions with no security pocket. Write the
# deb822 sources the release actually uses instead.
sources_content="# written by ci-runner/k3s/phase0-bare-metal/${SCRIPT_NAME} from ${PROFILE_PATH}
Types: deb
URIs: ${CFG[OS_MIRROR]}
Suites: ${RELEASE} ${RELEASE}-updates ${RELEASE}-backports
Components: ${CFG[OS_COMPONENTS]}
Signed-By: ${ARCHIVE_KEYRING}

Types: deb
URIs: ${CFG[OS_SECURITY_MIRROR]}
Suites: ${RELEASE}-security
Components: ${CFG[OS_COMPONENTS]}
Signed-By: ${ARCHIVE_KEYRING}"
write_file "${MOUNT_ROOT}/etc/apt/sources.list.d/${CFG[OS_DISTRIBUTION]}.sources" "$sources_content"

# ---------------------------------------------------------------------------
stage "4/10 /etc/fstab, every line found by LABEL"
# ---------------------------------------------------------------------------
# BY LABEL, not by UUID: a UUID is minted by every mkfs, so a UUID-keyed fstab
# has to be rewritten on every media move and can never be byte-identical to
# the copy in git. A label is chosen by us and is the same on any medium
# (../phase2/storage-layout/install-storage-layout.sh, "WHY LABELS").
#
# The three tier lines and the two binds below are BYTE-EXACT with the five
# that installer ensures, so stage 4 of the rebuild finds them already present
# and changes nothing. Each bind requires ITS OWN SOURCE mount, not merely the
# cache volume: otherwise systemd may bind the empty mountpoint directory
# before the tier volume lands on it and k3s would silently run on the wrong
# filesystem, since every path exists either way.
tier_mountpoint() {
  case "$1" in
    ci-cache) printf '%s' "$CACHE_MOUNT" ;;
    ci-containerd) printf '%s' "$CONTAINERD_SRC" ;;
    ci-workvols) printf '%s' "$STORAGE_SRC" ;;
    *) return 1 ;;
  esac
}
tier_options() {
  # The cache volume is the parent of the other two, so only they carry the
  # ordering dependency on it.
  case "$1" in
    ci-cache) printf 'defaults,noatime' ;;
    *) printf 'defaults,noatime,x-systemd.requires-mounts-for=%s' "$CACHE_MOUNT" ;;
  esac
}

fstab_lines=()
fstab_lines+=("LABEL=${ROOT_LABEL} / ${ROOT_FSTYPE} defaults 0 1")
fstab_lines+=("LABEL=${CFG[ESP_LABEL]} /boot/efi ${CFG[ESP_FSTYPE]} umask=0077 0 1")
if [ -n "${CFG[SWAP_LABEL]}" ]; then
  fstab_lines+=("LABEL=${CFG[SWAP_LABEL]} none swap sw 0 0")
fi
declare -A TIER_DECLARED=()
for record in "${TIER_RECORDS[@]}"; do
  IFS=: read -r rec_role _ <<< "$record"
  mountpoint="$(tier_mountpoint "$rec_role")" \
    || die "${PROFILE_PATH}: ROLE_TIERS names role '${rec_role}', which install-storage-layout.sh has no mountpoint for"
  fstab_lines+=("LABEL=${rec_role} ${mountpoint} ${LV_FSTYPE_OF_LABEL[$rec_role]} $(tier_options "$rec_role") 0 2")
  TIER_DECLARED["$rec_role"]=1
done
if [ -n "${TIER_DECLARED[ci-containerd]:-}" ]; then
  fstab_lines+=("${CONTAINERD_SRC} ${CONTAINERD_DIR} none bind,x-systemd.requires-mounts-for=${CONTAINERD_SRC} 0 0")
fi
if [ -n "${TIER_DECLARED[ci-workvols]:-}" ]; then
  fstab_lines+=("${STORAGE_SRC} ${STORAGE_DIR} none bind,x-systemd.requires-mounts-for=${STORAGE_SRC} 0 0")
fi

fstab_content="# /etc/fstab — written by ci-runner/k3s/phase0-bare-metal/${SCRIPT_NAME}
# from ${PROFILE_PATH}. Every filesystem is found by LABEL so that a tier can
# move media without this file changing. The three ci-* lines and the two binds
# are byte-exact with the five ../phase2/storage-layout/install-storage-layout.sh
# ensures; edit them there and here together.
$(printf '%s\n' "${fstab_lines[@]}")"
write_file "${MOUNT_ROOT}/etc/fstab" "$fstab_content"

# The mountpoints the tier lines name must exist on the root volume, or the
# first boot fails them all.
mountpoint_dirs=()
for record in "${TIER_RECORDS[@]}"; do
  IFS=: read -r rec_role _ <<< "$record"
  mountpoint_dirs+=("${MOUNT_ROOT}$(tier_mountpoint "$rec_role")")
done
if [ -n "${TIER_DECLARED[ci-containerd]:-}" ]; then mountpoint_dirs+=("${MOUNT_ROOT}${CONTAINERD_DIR}"); fi
if [ -n "${TIER_DECLARED[ci-workvols]:-}" ]; then mountpoint_dirs+=("${MOUNT_ROOT}${STORAGE_DIR}"); fi
missing_dirs=()
for dir in "${mountpoint_dirs[@]}"; do
  [ -d "$dir" ] || missing_dirs+=("$dir")
done
if [ "${#missing_dirs[@]}" -eq 0 ]; then
  note "no change: every tier mountpoint directory already exists"
else
  run mkdir -p "${missing_dirs[@]}"
fi

# ---------------------------------------------------------------------------
stage "5/10 the API filesystems the chroot needs"
# ---------------------------------------------------------------------------
# efivarfs is in the list because stage 9 registers the firmware boot entry
# from inside the chroot, and efibootmgr writes through it.
for api in dev dev/pts proc sys sys/firmware/efi/efivars; do
  target="${MOUNT_ROOT}/${api}"
  if [ -n "$(probe findmnt --noheadings --output TARGET --mountpoint "$target")" ]; then
    note "no change: ${target} is already mounted"
    continue
  fi
  run mkdir -p "$target"
  run mount --rbind "/${api}" "$target"
done

# ---------------------------------------------------------------------------
stage "6/10 kernel, lvm2 and the base packages, inside the chroot"
# ---------------------------------------------------------------------------
# lvm2 IS THE ONE THAT MATTERS: without it in the chroot the initramfs built in
# stage 7 has no way to activate the root volume group, and the node boots to a
# shell that cannot find its root filesystem. That is exactly what happened by
# hand on 2026-09-04. It is listed first after the kernel for that reason.
packages=("${CFG[KERNEL_PACKAGE]}" lvm2)
case "${CFG[INITRAMFS_GENERATOR]}" in
  dracut) packages+=(dracut) ;;
  initramfs-tools) packages+=(initramfs-tools) ;;
  *) die "${PROFILE_PATH}: INITRAMFS_GENERATOR='${CFG[INITRAMFS_GENERATOR]}' is not one this stage knows (dracut, initramfs-tools)" ;;
esac
packages+=("$GRUB_PACKAGE" "${GRUB_PACKAGE}-signed" shim-signed efibootmgr)
packages+=(systemd-sysv netplan.io sudo openssh-server ca-certificates curl)

# The userspace tools for every filesystem type the profile declares — without
# them the tier lines in fstab fail to mount on the first boot. Derived from
# the profile rather than listed, so a node that adds a type gets its tools.
declare -A FS_TOOL_SEEN=()
fs_tool() {
  case "$1" in
    ext2|ext3|ext4) printf 'e2fsprogs' ;;
    xfs) printf 'xfsprogs' ;;
    btrfs) printf 'btrfs-progs' ;;
    vfat) printf 'dosfstools' ;;
    swap) printf '' ;;
    *) return 1 ;;
  esac
}
add_fs_tool() {
  local fstype="$1" tool
  tool="$(fs_tool "$fstype")" \
    || die "${PROFILE_PATH}: no filesystem tools are known for type '${fstype}'"
  if [ -n "$tool" ] && [ -z "${FS_TOOL_SEEN[$tool]:-}" ]; then
    FS_TOOL_SEEN["$tool"]=1
    packages+=("$tool")
  fi
}
# In profile order, so the printed command is the same on every run — an
# associative array's iteration order is not the profile's.
add_fs_tool "${CFG[ESP_FSTYPE]}"
for record in "${LV_RECORDS[@]}"; do
  IFS=: read -r _ _ _ rec_fstype _ <<< "$record"
  add_fs_tool "$rec_fstype"
done

run chroot "$MOUNT_ROOT" env DEBIAN_FRONTEND=noninteractive apt-get update
run chroot "$MOUNT_ROOT" env DEBIAN_FRONTEND=noninteractive \
  apt-get install --yes --no-install-recommends "${packages[@]}"

# ---------------------------------------------------------------------------
stage "7/10 initramfs with LVM support"
# ---------------------------------------------------------------------------
# Regenerated AFTER lvm2 is installed, never before: the generator can only
# include a module that is on disk when it runs. `--add lvm` / the lvm2 hook is
# what puts the volume-group activation into the early boot, which is the whole
# reason the 2026-09-04 hand rebuild would not come up.
case "${CFG[INITRAMFS_GENERATOR]}" in
  dracut) run chroot "$MOUNT_ROOT" dracut --force --regenerate-all --add lvm ;;
  initramfs-tools) run chroot "$MOUNT_ROOT" update-initramfs -c -k all ;;
esac

# ---------------------------------------------------------------------------
stage "8/10 bootloader: signed shim + GRUB on the EFI system partition"
# ---------------------------------------------------------------------------
# root= is the device-mapper path the volume group presents, and rd.lvm.lv
# names the volume the initramfs must activate to make that path exist. Both
# are derived from the profile's ROOT_LABEL, so they cannot disagree with the
# volume stage 1 created or with the LABEL= line in fstab.
grub_default_content="# written by ci-runner/k3s/phase0-bare-metal/${SCRIPT_NAME}
# from ${PROFILE_PATH}.
GRUB_DEFAULT=0
GRUB_TIMEOUT=5
GRUB_TIMEOUT_STYLE=menu
GRUB_DISTRIBUTOR=${CFG[BOOT_ENTRY_LABEL]}
GRUB_TERMINAL=console
GRUB_CMDLINE_LINUX_DEFAULT=\"\"
GRUB_CMDLINE_LINUX=\"root=${ROOT_DM} rd.lvm.lv=${ROOT_VG}/${ROOT_LV}\""
write_file "${MOUNT_ROOT}/etc/default/grub" "$grub_default_content"

run chroot "$MOUNT_ROOT" grub-install \
  "--target=${GRUB_PLATFORM}" \
  --efi-directory=/boot/efi \
  "--bootloader-id=${CFG[BOOT_ENTRY_LABEL]}" \
  --uefi-secure-boot \
  --recheck
run chroot "$MOUNT_ROOT" update-grub

# ---------------------------------------------------------------------------
stage "9/10 identity: hostname, network, operator account, firmware entry"
# ---------------------------------------------------------------------------
write_file "${MOUNT_ROOT}/etc/hostname" "${CFG[NODE_NAME]}"
write_file "${MOUNT_ROOT}/etc/hosts" "127.0.0.1 localhost
127.0.1.1 ${CFG[NODE_NAME]}

::1 localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters"

# `auto` for both means the node pins nothing: it takes a lease and k3s follows
# the default route, which is what ../provision-k3s.sh assumes by passing
# neither --node-ip nor --flannel-iface. A node that DOES pin an address must
# also name the interface it belongs to.
if [ "${CFG[NODE_ADDRESS]}" = "auto" ]; then
  if [ "${CFG[NODE_NETWORK_INTERFACE]}" = "auto" ]; then
    netplan_content="network:
  version: 2
  ethernets:
    all-ethernet:
      match:
        name: \"en*\"
      dhcp4: true"
  else
    netplan_content="network:
  version: 2
  ethernets:
    ${CFG[NODE_NETWORK_INTERFACE]}:
      dhcp4: true"
  fi
else
  if [ "${CFG[NODE_NETWORK_INTERFACE]}" = "auto" ]; then
    die "${PROFILE_PATH}: NODE_ADDRESS pins '${CFG[NODE_ADDRESS]}' but NODE_NETWORK_INTERFACE is 'auto'; name the interface the address belongs to"
  fi
  netplan_content="network:
  version: 2
  ethernets:
    ${CFG[NODE_NETWORK_INTERFACE]}:
      dhcp4: false
      addresses:
        - ${CFG[NODE_ADDRESS]}"
fi
# 0600: netplan warns, loudly and on every apply, about a world-readable file.
write_file "${MOUNT_ROOT}/etc/netplan/10-ci-runner.yaml" "$netplan_content" 0600

# The sudo-capable admin ../provision-k3s.sh and ../phase2/install-node.sh are
# run as. NO credential is installed for it: this tree carries no secret, so
# authorizing a login is the operator's step at the console or over the
# out-of-band console the rehearsal uses.
operator="${CFG[OPERATOR_ACCOUNT]}"
if grep -q "^${operator}:" "${MOUNT_ROOT}/etc/passwd" 2>/dev/null; then
  note "no change: the operator account ${operator} already exists"
else
  run chroot "$MOUNT_ROOT" useradd --create-home --shell /bin/bash \
    "--groups=${CFG[OPERATOR_GROUPS]}" "$operator"
  note "NOTE: ${operator} has no credential yet — this tree installs no secret."
  note "      Authorize a login for it at the console before the node is left."
fi

# The firmware boot entry. grub-install normally writes one itself; this makes
# it explicit and idempotent, and is the step the recorded Boot#### entry of
# the 2026-09-04 rebuild corresponds to.
if printf '%s' "$(probe efibootmgr)" | grep -qF " ${CFG[BOOT_ENTRY_LABEL]}"; then
  note "no change: a firmware boot entry labelled ${CFG[BOOT_ENTRY_LABEL]} exists"
else
  run chroot "$MOUNT_ROOT" efibootmgr --create \
    "--disk=${CFG[TARGET_DEVICE]}" \
    "--part=${ESP_PART}" \
    "--label=${CFG[BOOT_ENTRY_LABEL]}" \
    "--loader=\\EFI\\${CFG[BOOT_ENTRY_LABEL]}\\${SHIM_BINARY}"
fi

# ---------------------------------------------------------------------------
stage "10/10 unmount the target"
# ---------------------------------------------------------------------------
# Recursive, so the API filesystems bound in stage 5 come down with it; leaving
# /dev bound into a target that is then rebooted has cost real time elsewhere.
if [ -n "$(probe findmnt --noheadings --output TARGET --mountpoint "$MOUNT_ROOT")" ] || [ "$DRY_RUN" -eq 1 ]; then
  run umount --recursive "$MOUNT_ROOT"
else
  note "no change: ${MOUNT_ROOT} is not mounted"
fi

# ---------------------------------------------------------------------------
printf '\n'
if [ "$CHANGES" -eq 0 ]; then
  note "DONE. ${CFG[NODE_NAME]} already carries the operating system ${PROFILE_PATH} declares; nothing changed."
elif [ "$DRY_RUN" -eq 1 ]; then
  note "DONE (dry run). ${CHANGES} command(s) and file write(s) printed, none executed."
else
  note "DONE. ${CHANGES} command(s) executed. The 'installed operating system' precondition is established."
  note "Next stage: README.md beside this script."
fi
