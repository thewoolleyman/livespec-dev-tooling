#!/usr/bin/env bash
# storage-layout.sh — STAGE 1 of the bare-metal rebuild of a CI runner pool
# node: take a node with empty storage to the storage-controller virtual disk,
# partition table, LVM volume groups, logical volumes and role-labelled
# filesystems that the later stages assume already exist.
#
# WHERE IT SITS. `../phase2/storage-layout/install-storage-layout.sh` is this
# script's CONSUMER, not its replacement: it starts from filesystems that
# ALREADY carry the role labels and refuses when a label resolves to zero
# devices. Producing those labelled filesystems from empty storage is what this
# stage does. The stage order for a whole node is in README.md beside this file.
#
# PROCEDURE HERE, DATA IN THE PROFILE. Every value that belongs to one node —
# the controller and its virtual disk, the target device, the partition sizes,
# the volume groups and their physical volumes, the logical volumes and their
# filesystems, the role tiers — is read from the profile named on the command
# line (`profiles/<node>.env`). This script contains none of them, so a second
# node is a second profile and never a second script
# (SPECIFICATION/non-functional-requirements.md §"Runner-pool node rebuild
# recipe").
#
# TWO DISK PLANS, chosen by the profile's DISK_PLAN. `whole-device` is the
# original: the device is the node's to erase, so the run zaps it and writes the
# declared table over the top. `free-space` is for a node that KEEPS THE
# OPERATING SYSTEM IT ALREADY HAS — a device already carrying a root filesystem
# and an EFI system partition, with unpartitioned space after them. That plan
# skips the controller and the zap entirely, adds exactly ONE partition in the
# largest free region, and refuses any step that names a partition the profile
# lists in PRESERVED_PARTITIONS. From the physical volume onward the two plans
# are the same script.
#
# PRESERVATION OUTRANKS CONSENT. `--i-consent-to-destroy` grants ONE destructive
# step against a target the profile is willing to lose. A PRESERVED_PARTITIONS
# entry is a target the profile is NOT willing to lose, so no flag unlocks it:
# the refusal is unconditional and names the partition. The two keys say
# different things on purpose — consent is "yes, that one", preservation is "not
# that one, ever".
#
# RE-RUNNABLE. Every stage probes for the state the profile declares and skips
# when it is already there, saying so. Against a node already in its profile's
# declared state the whole run changes nothing and reports "already in the
# declared state".
#
# DESTRUCTIVE ONLY ON CONSENT. A stage is destructive when — and only when —
# the thing it is about to write over currently holds something: an existing
# virtual disk, a disk that already carries partitions, a device that already
# carries a filesystem signature. Such a stage REFUSES unless the invocation
# carries `--i-consent-to-destroy=<target>` naming that exact target, and the
# refusal names it. Consent for one target is never consent for another.
#
# TOOLS BEFORE MUTATIONS. Stage 1 is a PREFLIGHT: it derives every tool the
# plan will reach for and answers an absent one before anything is written, so
# a run either has what it needs or has changed nothing. The two plans answer
# differently because they run in different places — `free-space` runs on the
# node's own installed operating system, which has a package manager and may
# simply never have been given lvm2, so the package is installed first;
# `whole-device` runs from the Recovery USB, which is BUILT to carry these
# tools, so an absent one is a defect in the USB and the run refuses.
#
# --dry-run PRINTS AND EXECUTES NOTHING. Read-only PROBES still run (they are
# how the plan is derived); every mutating command is printed with a leading
# `+ ` and executed by nothing. A probe whose tool is not installed reports
# "absent", so a dry run on a workstation prints the full sequence a bare node
# would take. Consent is evaluated identically in both modes, so a dry run also
# tells the operator which targets it would need consent for — and a
# whole-device refusal the preflight would make is printed as
# `WOULD REFUSE: <tool> absent (<package>)` rather than taken, so a workstation
# dry run still shows the whole plan.
#
# Usage:
#   storage-layout.sh --dry-run profiles/<node>.env
#   sudo storage-layout.sh [--i-consent-to-destroy=TARGET]... profiles/<node>.env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "$0")"
DRY_RUN=0
PROFILE_PATH=""
CONSENT=()
CHANGES=0

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }
stage() { printf '\n== %s ==\n' "$*"; }

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} [--dry-run] [--i-consent-to-destroy=TARGET]... PROFILE

  --dry-run                     Print every command that would run; run none.
  --i-consent-to-destroy=TARGET Permit the one destructive step whose target is
                                TARGET. Repeatable. Targets are the virtual
                                disk (vd:c<controller-id>) and block-device
                                paths, exactly as a refusal names them.
  PROFILE                       Path to the node's profiles/<node>.env.
EOF
}

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
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

# ---------------------------------------------------------------------------
# Profile: parsed, never sourced
#
# The parser lives in profile.sh beside this script and is shared with every
# other stage, so no two stages can disagree about what a profile may contain —
# each of them REFUSES an unknown key, which a per-stage key list would turn
# into "the key a later stage needs breaks the earlier one".
# ---------------------------------------------------------------------------
# shellcheck source=ci-runner/k3s/phase0-bare-metal/profile.sh
source "${SCRIPT_DIR}/profile.sh"
profile_load "$PROFILE_PATH"

# ---------------------------------------------------------------------------
# Execution, probing and consent
# ---------------------------------------------------------------------------

# refuse_preserved — the ONE gate between any plan and a partition the profile
# says must survive.
#
# It scans the ARGUMENT LIST rather than sitting inside the handful of steps
# that are destructive today, because the promise PRESERVED_PARTITIONS makes is
# about the partition and not about a step: a step added later that names one is
# caught by this without anybody remembering to guard it. Nothing about the
# scan is clever — every mutating command this script can issue passes the
# device as its own word.
refuse_preserved() {
  local word preserved
  for word in "$@"; do
    for preserved in ${PRESERVED_DEVICES[@]+"${PRESERVED_DEVICES[@]}"}; do
      if [ "$word" = "$preserved" ]; then
        printf 'REFUSED: %s planned a step naming %s, which %s lists in PRESERVED_PARTITIONS.\n' \
          "$SCRIPT_NAME" "$preserved" "$PROFILE_PATH" >&2
        printf '         the step was: %s\n' "$*" >&2
        printf '         A preserved partition is never written, and no --i-consent-to-destroy unlocks it.\n' >&2
        printf '         Drop it from PRESERVED_PARTITIONS if this node really is meant to lose it.\n' >&2
        exit 1
      fi
    done
  done
}

# run — the ONE place a mutating command is either printed or executed.
run() {
  refuse_preserved "$@"
  printf '+'
  printf ' %s' "$@"
  printf '\n'
  if [ "$DRY_RUN" -eq 0 ]; then
    "$@"
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
#
# It asks refuse_preserved FIRST, which is what makes "preservation outranks
# consent" true of the MESSAGE and not merely of the outcome. Without it a
# preserved partition that carries a filesystem — which the preserved root of a
# free-space node always does — is caught one step later, by `run`, and the
# operator meanwhile reads a refusal whose remedy is
# `--i-consent-to-destroy=<that partition>`. The run never destroys it either
# way, but that advice is wrong about which of the two keys is in the way, and
# following it produces a second, different refusal. A preserved target is not a
# consent question, so it must never be asked as one.
require_consent() {
  local target="$1" what="$2"
  refuse_preserved "$target"
  if consented "$target"; then
    note "consent given for ${target}: proceeding to ${what}"
    return 0
  fi
  printf 'REFUSED: %s would destroy %s, which is not empty.\n' "$SCRIPT_NAME" "$target" >&2
  printf '         %s\n' "$what" >&2
  printf '         Re-run with --i-consent-to-destroy=%s if that is what you want.\n' "$target" >&2
  exit 1
}

# size_arg — the profile states binary sizes the human way (GiB/TiB); sgdisk
# and lvcreate spell the same units with a bare letter.
size_arg() {
  case "$1" in
    *KiB) printf '%sK' "${1%KiB}" ;;
    *MiB) printf '%sM' "${1%MiB}" ;;
    *GiB) printf '%sG' "${1%GiB}" ;;
    *TiB) printf '%sT' "${1%TiB}" ;;
    *) printf '%s' "$1" ;;
  esac
}

# fs_tool TYPE — set FS_TOOL to the maker a declared filesystem type is made
# with. It is the TOOL side of `make_fs`, split out because the preflight has
# to know which makers a plan will reach for before the stage that reaches for
# them runs. The two carry the same list of types on purpose: `make_fs` owns
# each maker's ARGUMENTS, this owns its NAME, and a type that has neither is
# refused HERE — before any mutation, rather than at stage 7 with five stages
# of writes already behind it.
#
# An out-variable rather than a `$(…)` helper on purpose: its rejection has to
# stop the RUN, and an `exit` inside a command substitution only ends the
# subshell that ran it.
fs_tool() {
  case "$1" in
    ext4) FS_TOOL='mkfs.ext4' ;;
    xfs) FS_TOOL='mkfs.xfs' ;;
    vfat) FS_TOOL='mkfs.vfat' ;;
    swap) FS_TOOL='mkswap' ;;
    *) die "unsupported filesystem type '$1' in ${PROFILE_PATH}" ;;
  esac
}

# tool_package TOOL — set TOOL_PACKAGE to the Debian package carrying TOOL.
#
# Naming the package is what makes both of the preflight's answers actionable:
# the free-space plan installs exactly these, and the whole-device refusal tells
# an operator what the Recovery USB is missing rather than leaving them to work
# out for themselves which package holds `pvcreate`. Same out-variable shape as
# `fs_tool`, and for the same reason.
tool_package() {
  case "$1" in
    sgdisk) TOOL_PACKAGE='gdisk' ;;
    partprobe) TOOL_PACKAGE='parted' ;;
    pvcreate|vgcreate|lvcreate) TOOL_PACKAGE='lvm2' ;;
    mkfs.ext4) TOOL_PACKAGE='e2fsprogs' ;;
    mkfs.xfs) TOOL_PACKAGE='xfsprogs' ;;
    mkfs.vfat) TOOL_PACKAGE='dosfstools' ;;
    mkswap) TOOL_PACKAGE='util-linux' ;;
    *) die "no package is recorded for the tool '$1'; add it to tool_package before the plan can need it" ;;
  esac
}

# fs_type_of / fs_label_of — probe the superblock directly rather than the
# blkid cache, which goes stale after a relabel.
fs_type_of() { probe blkid -p -s TYPE -o value "$1"; }
fs_label_of() { probe blkid -p -s LABEL -o value "$1"; }

if [ "$DRY_RUN" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
  die "must run as root (it writes partition tables, volume groups and filesystems). Use --dry-run to see the plan unprivileged."
fi

note "profile:  ${PROFILE_PATH}"
note "node:     ${CFG[NODE_NAME]}"
if [ "${CFG[DISK_PLAN]}" = "free-space" ]; then
  note "plan:     free-space — only the unpartitioned tail of ${CFG[TARGET_DEVICE]} is taken"
  note "preserve: ${CFG[PRESERVED_PARTITIONS]}"
fi
if [ "$DRY_RUN" -eq 1 ]; then
  note "mode:     DRY RUN — every '+ ' line is printed and executed by nothing"
else
  note "mode:     LIVE"
fi

# ---------------------------------------------------------------------------
stage "1/7 the tools this plan needs"
# ---------------------------------------------------------------------------
# THE HALF-APPLIED LAYOUT THIS STAGE EXISTS TO PREVENT. Every stage below
# reaches for a tool the node may not carry, and they are not equally likely to
# be there: a stock desktop install HAS `sgdisk`, `partprobe` and `mkfs.ext4`
# and has neither lvm2 nor xfsprogs. Without this stage a `free-space` run on
# such a node writes the new partition, re-reads the table, and only THEN dies
# at `pvcreate: command not found` — the device now carries a partition with
# nothing on it, and because the tail it was cut from is no longer free, a
# re-run computes a DIFFERENT "largest free region" against a device that
# changed under it. Measured on gmktec-xubuntu 2026-09-07, before its
# rehearsal.
#
# THE TOOL SET IS DERIVED FROM THE PLAN, never listed: a profile whose logical
# volumes name a filesystem type puts that type's maker in the set, so a new
# type is a profile edit and a `fs_tool` arm, and never a list to keep in step
# by hand.
#
# THE TWO PLANS ANSWER AN ABSENCE DIFFERENTLY, because they run in different
# places. `whole-device` runs from the Recovery USB, which is built to carry
# these tools, so an absent one is a defect in the USB and the honest answer is
# to refuse before writing anything. `free-space` runs on the operating system
# the node already has — which has a package manager, and no reason to have
# been given lvm2 — so the honest answer is to install it FIRST, ahead of the
# partition table, which is what keeps "either everything it needs or nothing
# changed" true. (An `apt-get` that is itself missing fails there, as the first
# mutating command of the run, with the disk still untouched.)
required_tools=()
declare -A tool_seen=()
add_required_tool() {
  if [ -z "${tool_seen[$1]:-}" ]; then
    tool_seen["$1"]=1
    required_tools+=("$1")
  fi
}

# The partition table is written with sgdisk and re-read with partprobe; the
# physical volume, its group and its volumes with the LVM trio. The EFI system
# partition's maker joins the set only under `whole-device`, which is the plan
# that MAKES it; under `free-space` it is a filesystem the node already boots
# from and stage 7 never writes it.
for tool in sgdisk partprobe pvcreate vgcreate lvcreate; do
  add_required_tool "$tool"
done
if [ "${CFG[DISK_PLAN]}" != "free-space" ]; then
  fs_tool "${CFG[ESP_FSTYPE]}"
  add_required_tool "$FS_TOOL"
fi
for record in "${LV_RECORDS[@]}"; do
  IFS=: read -r _ _ _ rec_fstype _ <<< "$record"
  fs_tool "$rec_fstype"
  add_required_tool "$FS_TOOL"
done

missing_tools=()
for tool in "${required_tools[@]}"; do
  have "$tool" || missing_tools+=("$tool")
done

if [ "${#missing_tools[@]}" -eq 0 ]; then
  note "no change: every tool this plan needs is installed (${required_tools[*]})"
elif [ "${CFG[DISK_PLAN]}" = "free-space" ]; then
  # One `apt-get` for all of them, and each package named once: the LVM trio is
  # three tools out of one package, so a per-tool install would ask for lvm2
  # three times and read as three separate problems.
  missing_packages=()
  declare -A package_seen=()
  for tool in "${missing_tools[@]}"; do
    tool_package "$tool"
    if [ -z "${package_seen[$TOOL_PACKAGE]:-}" ]; then
      package_seen["$TOOL_PACKAGE"]=1
      missing_packages+=("$TOOL_PACKAGE")
    fi
  done
  note "plan:     ${missing_tools[*]} absent; ${missing_packages[*]} installed before the partition table is touched"
  # Nobody is sitting at this node, so apt-get must never stop for a prompt.
  export DEBIAN_FRONTEND=noninteractive
  run apt-get install -y --no-install-recommends "${missing_packages[@]}"
  if [ "$DRY_RUN" -eq 0 ]; then
    # RE-PROBED, because "apt-get exited 0" is a statement about apt-get and not
    # about the tool: a package that installs its binary somewhere this PATH
    # does not reach leaves the run exactly as unable to finish as before.
    for tool in "${missing_tools[@]}"; do
      tool_package "$tool"
      have "$tool" || die "${tool} is still absent after installing ${TOOL_PACKAGE}; nothing has been written to ${CFG[TARGET_DEVICE]}"
    done
    note "installed: ${missing_tools[*]} are present now"
  fi
else
  for tool in "${missing_tools[@]}"; do
    tool_package "$tool"
    if [ "$DRY_RUN" -eq 1 ]; then
      note "WOULD REFUSE: ${tool} absent (${TOOL_PACKAGE})"
    else
      printf 'REFUSED: %s needs %s, which is not installed (package %s).\n' \
        "$SCRIPT_NAME" "$tool" "$TOOL_PACKAGE" >&2
    fi
  done
  if [ "$DRY_RUN" -eq 0 ]; then
    die "DISK_PLAN=whole-device runs from the Recovery USB, which is built to carry every tool this plan needs. Nothing has been written to ${CFG[TARGET_DEVICE]}. Add the package(s) named above to recovery-usb/build-recovery-usb.sh and re-run."
  fi
  note "          a live run refuses there; the rest of the plan is printed so a dry run still shows it in full"
fi

# ---------------------------------------------------------------------------
stage "2/7 storage-controller virtual disk"
# ---------------------------------------------------------------------------
# A free-space plan runs against a device that already carries this node's
# operating system, so there is nothing here to build: the virtual disk (or the
# bare drive) the OS boots from is the one the node already has, and creating a
# new one would destroy it. The skip names CONTROLLER_KIND when the profile
# declares a controller, so a plan that quietly disagrees with its own hardware
# keys says so rather than passing in silence.
if [ "${CFG[DISK_PLAN]}" = "free-space" ]; then
  if [ "${CFG[CONTROLLER_KIND]}" = "none" ]; then
    note "no change: DISK_PLAN=free-space keeps the storage ${CFG[TARGET_DEVICE]} already presents"
  else
    note "no change: DISK_PLAN=free-space keeps the storage ${CFG[TARGET_DEVICE]} already presents, so the declared ${CFG[CONTROLLER_KIND]} controller is left untouched"
  fi
elif [ "${CFG[CONTROLLER_KIND]}" = "none" ]; then
  note "no change: profile declares no storage controller"
else
  controller_cli="${CFG[CONTROLLER_CLI]}"
  controller="/c${CFG[CONTROLLER_ID]}"
  vd_target="vd:c${CFG[CONTROLLER_ID]}"
  if [ "$DRY_RUN" -eq 0 ] && [ ! -x "$controller_cli" ]; then
    die "${controller_cli} is not executable; install the ${CFG[CONTROLLER_KIND]} CLI before running this stage"
  fi
  vd_show=""
  if [ -x "$controller_cli" ]; then
    vd_show="$("$controller_cli" "${controller}/vall" show 2>/dev/null || true)"
  else
    note "probe:    ${controller_cli} not present — reading the controller as unconfigured"
  fi
  if printf '%s' "$vd_show" | grep -qiE "RAID${CFG[VD_RAID_LEVEL]}([^0-9]|\$)"; then
    note "no change: ${controller} already carries a RAID${CFG[VD_RAID_LEVEL]} virtual disk"
  else
    if printf '%s' "$vd_show" | grep -qiE '\bRAID[0-9]'; then
      require_consent "$vd_target" "the existing virtual disk on ${controller} is deleted and replaced"
      run "$controller_cli" "${controller}/vall" delete force
    fi
    # The enclosure id is `auto` in a profile that has not measured it; read it
    # off the controller rather than pinning a number. A dry run on a host
    # without the controller cannot resolve it, and says so in the printed
    # command rather than inventing one.
    enclosure="${CFG[VD_ENCLOSURE]}"
    if [ "$enclosure" = "auto" ]; then
      if [ -x "$controller_cli" ]; then
        note "resolving the enclosure id from the controller (VD_ENCLOSURE=auto)"
        enclosure="$("$controller_cli" "${controller}/eall" show 2>/dev/null | awk '$1 ~ /^[0-9]+$/ {print $1; exit}')"
        [ -n "$enclosure" ] || die "could not read an enclosure id from ${controller_cli} ${controller}/eall show; set VD_ENCLOSURE in the profile"
      else
        enclosure="<enclosure>"
        note "probe:    enclosure id unresolvable without the controller; printed as ${enclosure}"
      fi
    fi
    vd_args=(
      "add" "vd"
      "type=raid${CFG[VD_RAID_LEVEL]}"
      "drives=${enclosure}:${CFG[VD_SLOTS]}"
      "strip=${CFG[VD_STRIP_KIB]}"
    )
    IFS=, read -r -a cache_policy <<< "${CFG[VD_CACHE_POLICY]}"
    vd_args+=("${cache_policy[@]}")
    run "$controller_cli" "$controller" "${vd_args[@]}"
    # The block device the new virtual disk presents as does not exist the
    # instant the controller returns. Wait for udev to finish enumerating it
    # rather than partitioning a path that is not there yet. `settle` only
    # WAITS; it is not the blanket `udevadm trigger` that stopped every
    # device-mapper-backed mount on this node once already
    # (`.ai/ci-node-storage-tiers.md`).
    run udevadm settle
  fi
fi

# ---------------------------------------------------------------------------
stage "3/7 partition table on ${CFG[TARGET_DEVICE]}"
# ---------------------------------------------------------------------------
# Under `whole-device` the structure is fixed by the procedure — partition 1 is
# the EFI system partition, partition 2 is the LVM physical volume — while the
# device, the sizes and the partition names are the profile's.
#
# Under `free-space` the existing table is the node's and only ONE partition is
# added to it: the EFI system partition and the root the device already carries
# are the ones it boots from, so the procedure neither numbers nor sizes them.
target="${CFG[TARGET_DEVICE]}"
partlabels_seen="$(probe lsblk -rno PARTLABEL "$target" | grep . || true)"
if [ "${CFG[DISK_PLAN]}" = "free-space" ]; then
  if printf '%s\n' "$partlabels_seen" | grep -qxF "${CFG[PV_PARTLABEL]}"; then
    note "no change: ${target} already carries a partition labelled ${CFG[PV_PARTLABEL]}"
  else
    # The next free partition number, read off the table rather than assumed:
    # this device's existing partitions belong to an operating system this
    # procedure did not install, so their count is not the procedure's to know.
    partnums_seen="$(probe lsblk -rno PARTN "$target" | grep . || true)"
    partnum=1
    while printf '%s\n' "$partnums_seen" | grep -qxF "$partnum"; do
      partnum=$((partnum + 1))
    done
    note "plan:     partition ${partnum} takes the largest free region of ${target}"
    # `--new=N:0:0` is sgdisk's own "the largest free block, start to end": the
    # first 0 is that block's first sector and the second is its last, so the
    # tail is sized by what is actually free rather than by a size this file
    # would otherwise have to carry for one node.
    run sgdisk "--new=${partnum}:0:0" "--typecode=${partnum}:8e00" "--change-name=${partnum}:${CFG[PV_PARTLABEL]}" "$target"
    run partprobe "$target"
  fi
else
  declared_labels="$(printf '%s' "$partlabels_seen" | paste -sd, -)"
  if [ "$declared_labels" = "${CFG[ESP_LABEL]},${CFG[PV_PARTLABEL]}" ]; then
    note "no change: ${target} already carries the declared partition table"
  else
    if [ -n "$(probe blkid -p -s PTTYPE -o value "$target")" ] || [ -n "$(fs_type_of "$target")" ]; then
      require_consent "$target" "every partition and signature on ${target} is erased and the declared table written in its place"
      run wipefs --all "$target"
    fi
    run sgdisk --zap-all "$target"
    run sgdisk "--new=1:0:+$(size_arg "${CFG[ESP_SIZE]}")" "--typecode=1:ef00" "--change-name=1:${CFG[ESP_LABEL]}" "$target"
    run sgdisk "--new=2:0:0" "--typecode=2:8e00" "--change-name=2:${CFG[PV_PARTLABEL]}" "$target"
    # Scoped to this one disk on purpose. A blanket `udevadm trigger` over the
    # block subsystem is what stopped every device-mapper-backed mount on this
    # node once already (`.ai/ci-node-storage-tiers.md`).
    run partprobe "$target"
  fi
fi

# ---------------------------------------------------------------------------
stage "4/7 LVM physical volumes"
# ---------------------------------------------------------------------------
for vg in "${VG_NAMES[@]}"; do
  pv="${VG_PV[$vg]}"
  if [ -n "$(probe pvs --noheadings -o pv_name "$pv")" ]; then
    note "no change: ${pv} is already a physical volume"
    continue
  fi
  pv_type="$(fs_type_of "$pv")"
  if [ -n "$pv_type" ]; then
    require_consent "$pv" "the existing ${pv_type} signature on ${pv} is overwritten by an LVM physical volume"
  fi
  run pvcreate --yes "$pv"
done

# ---------------------------------------------------------------------------
stage "5/7 volume groups"
# ---------------------------------------------------------------------------
for vg in "${VG_NAMES[@]}"; do
  if [ -n "$(probe vgs --noheadings -o vg_name "$vg")" ]; then
    note "no change: volume group ${vg} exists"
    continue
  fi
  run vgcreate "$vg" "${VG_PV[$vg]}"
done

# ---------------------------------------------------------------------------
stage "6/7 logical volumes"
# ---------------------------------------------------------------------------
for record in "${LV_RECORDS[@]}"; do
  IFS=: read -r rec_vg rec_lv rec_size _ _ <<< "$record"
  if [ -n "$(probe lvs --noheadings -o lv_name "${rec_vg}/${rec_lv}")" ]; then
    note "no change: logical volume ${rec_vg}/${rec_lv} exists"
    continue
  fi
  run lvcreate --yes -L "$(size_arg "$rec_size")" -n "$rec_lv" "$rec_vg"
done

# ---------------------------------------------------------------------------
stage "7/7 filesystems, carrying the labels install-storage-layout.sh resolves"
# ---------------------------------------------------------------------------
# The per-role filesystem types come from the profile and MUST agree with
# ../phase2/storage-layout/migrate-tier.sh's role_fstype and with
# install-storage-layout.sh's fstab lines — the reflink option is what lets the
# warm-cache seed give every job its own inodes.
make_fs() {
  local fstype="$1" label="$2" device="$3"
  case "$fstype" in
    ext4) run mkfs.ext4 -q -L "$label" "$device" ;;
    xfs) run mkfs.xfs -q -m reflink=1 -L "$label" "$device" ;;
    vfat) run mkfs.vfat -F 32 -n "$label" "$device" ;;
    swap) run mkswap -L "$label" "$device" ;;
    *) die "unsupported filesystem type '${fstype}' in ${PROFILE_PATH}" ;;
  esac
}

ensure_fs() {
  local fstype="$1" label="$2" device="$3" current_type current_label
  current_type="$(fs_type_of "$device")"
  current_label="$(fs_label_of "$device")"
  if [ "$current_type" = "$fstype" ] && [ "$current_label" = "$label" ]; then
    note "no change: ${device} already carries ${fstype} labelled ${label}"
    return 0
  fi
  if [ -n "$current_type" ]; then
    require_consent "$device" "the existing ${current_type} filesystem on ${device} is erased and remade as ${fstype} labelled ${label}"
  fi
  make_fs "$fstype" "$label" "$device"
}

# The EFI system partition is MADE only under `whole-device`, where this
# procedure created the partition it sits on. Under `free-space` it is the one
# the node already boots from: the profile's ESP keys describe it so the later
# stages can find it, and `mkfs` over it would take the node's bootloader with
# it. (`refuse_preserved` would stop that anyway when the profile lists it, as
# a free-space profile should; skipping here means the plan does not depend on
# the operator having remembered to.)
if [ "${CFG[DISK_PLAN]}" = "free-space" ]; then
  note "no change: ${CFG[ESP_DEVICE]} is the EFI system partition ${CFG[NODE_NAME]} already boots from"
else
  ensure_fs "${CFG[ESP_FSTYPE]}" "${CFG[ESP_LABEL]}" "${CFG[ESP_DEVICE]}"
fi
for record in "${LV_RECORDS[@]}"; do
  IFS=: read -r rec_vg rec_lv _ rec_fstype rec_label <<< "$record"
  ensure_fs "$rec_fstype" "$rec_label" "/dev/${rec_vg}/${rec_lv}"
done

# ---------------------------------------------------------------------------
printf '\n'
if [ "$CHANGES" -eq 0 ]; then
  note "DONE. ${CFG[NODE_NAME]} is already in the state ${PROFILE_PATH} declares; nothing changed."
elif [ "$DRY_RUN" -eq 1 ]; then
  note "DONE (dry run). ${CHANGES} command(s) printed, none executed."
else
  note "DONE. ${CHANGES} command(s) executed. Next stage: README.md beside this script."
fi
