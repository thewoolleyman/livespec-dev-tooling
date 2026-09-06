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
# --dry-run PRINTS AND EXECUTES NOTHING. Read-only PROBES still run (they are
# how the plan is derived); every mutating command is printed with a leading
# `+ ` and executed by nothing. A probe whose tool is not installed reports
# "absent", so a dry run on a workstation prints the full sequence a bare node
# would take. Consent is evaluated identically in both modes, so a dry run also
# tells the operator which targets it would need consent for.
#
# Usage:
#   storage-layout.sh --dry-run profiles/<node>.env
#   sudo storage-layout.sh [--i-consent-to-destroy=TARGET]... profiles/<node>.env
set -euo pipefail

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
# Parsing rather than sourcing means a profile cannot smuggle in procedure: it
# is KEY=value data or it is rejected. Every key below must be PRESENT; the
# emptiness rules are applied after the whole file is read, because whether a
# controller key may be empty depends on another key's value.
# ---------------------------------------------------------------------------
REQUIRED_KEYS=(
  NODE_NAME
  CONTROLLER_KIND
  CONTROLLER_CLI
  CONTROLLER_ID
  VD_ENCLOSURE
  VD_SLOTS
  VD_RAID_LEVEL
  VD_STRIP_KIB
  VD_CACHE_POLICY
  TARGET_DEVICE
  ESP_DEVICE
  ESP_SIZE
  ESP_FSTYPE
  ESP_LABEL
  PV_PARTLABEL
  VOLUME_GROUPS
  LOGICAL_VOLUMES
  ROLE_TIERS
  NODE_NETWORK_INTERFACE
  NODE_ADDRESS
  CLUSTER_ROLE
  CLUSTER_JOIN_ADDRESS
  ADMISSION_CAPACITY_C
)

declare -A CFG=()
declare -A KNOWN=()
for key in "${REQUIRED_KEYS[@]}"; do KNOWN["$key"]=1; done

[ -f "$PROFILE_PATH" ] || die "profile not found: ${PROFILE_PATH}"
lineno=0
while IFS= read -r line || [ -n "$line" ]; do
  lineno=$((lineno + 1))
  case "$line" in ''|'#'*) continue ;; esac
  case "$line" in
    *=*) ;;
    *) die "${PROFILE_PATH}:${lineno}: not a KEY=value line: ${line}" ;;
  esac
  key="${line%%=*}"
  if ! [[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
    die "${PROFILE_PATH}:${lineno}: '${key}' is not a profile key (want ^[A-Z][A-Z0-9_]*\$)"
  fi
  if [ -z "${KNOWN[$key]:-}" ]; then
    die "${PROFILE_PATH}:${lineno}: unknown profile key '${key}'"
  fi
  if [ -n "${CFG[$key]+set}" ]; then
    die "${PROFILE_PATH}:${lineno}: profile key '${key}' given more than once"
  fi
  CFG["$key"]="${line#*=}"
done < "$PROFILE_PATH"

for key in "${REQUIRED_KEYS[@]}"; do
  if [ -z "${CFG[$key]+set}" ]; then
    die "${PROFILE_PATH}: missing required profile key '${key}'"
  fi
done

# Emptiness. CLUSTER_JOIN_ADDRESS is empty for a node that forms its own
# cluster; the controller and virtual-disk keys are empty for a node that has
# no storage controller. Every other key must carry a value.
MAY_BE_EMPTY=(CLUSTER_JOIN_ADDRESS)
if [ "${CFG[CONTROLLER_KIND]}" = "none" ]; then
  MAY_BE_EMPTY+=(CONTROLLER_CLI CONTROLLER_ID VD_ENCLOSURE VD_SLOTS VD_RAID_LEVEL VD_STRIP_KIB VD_CACHE_POLICY)
fi
declare -A OPTIONAL=()
for key in "${MAY_BE_EMPTY[@]}"; do OPTIONAL["$key"]=1; done
for key in "${REQUIRED_KEYS[@]}"; do
  if [ -z "${CFG[$key]}" ] && [ -z "${OPTIONAL[$key]:-}" ]; then
    die "${PROFILE_PATH}: profile key '${key}' must not be empty"
  fi
done

# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------
read -r -a VG_RECORDS <<< "${CFG[VOLUME_GROUPS]}"
read -r -a LV_RECORDS <<< "${CFG[LOGICAL_VOLUMES]}"
read -r -a TIER_RECORDS <<< "${CFG[ROLE_TIERS]}"

declare -A VG_PV=()
VG_NAMES=()
for record in "${VG_RECORDS[@]}"; do
  IFS=: read -r rec_vg rec_pv rec_extra <<< "$record"
  if [ -z "$rec_vg" ] || [ -z "$rec_pv" ] || [ -n "$rec_extra" ]; then
    die "${PROFILE_PATH}: VOLUME_GROUPS record '${record}' is not <vg>:<physical-volume-device>"
  fi
  if [ -n "${VG_PV[$rec_vg]+set}" ]; then
    die "${PROFILE_PATH}: VOLUME_GROUPS declares volume group '${rec_vg}' more than once"
  fi
  VG_PV["$rec_vg"]="$rec_pv"
  VG_NAMES+=("$rec_vg")
done

# An ext4 label holds 16 bytes, an XFS label 12, a FAT label 11 and a swap
# label 15; a longer name is silently TRUNCATED by mkfs, which is how a live
# tier label was lost once already (`.ai/ci-node-storage-tiers.md`). Refuse it
# here instead.
label_limit() {
  case "$1" in
    xfs) printf '12' ;;
    vfat) printf '11' ;;
    swap) printf '15' ;;
    *) printf '16' ;;
  esac
}

declare -A LV_OF_LABEL=()
for record in "${LV_RECORDS[@]}"; do
  IFS=: read -r rec_vg rec_lv rec_size rec_fstype rec_label rec_extra <<< "$record"
  if [ -z "$rec_vg" ] || [ -z "$rec_lv" ] || [ -z "$rec_size" ] || [ -z "$rec_fstype" ] || [ -z "$rec_label" ] || [ -n "$rec_extra" ]; then
    die "${PROFILE_PATH}: LOGICAL_VOLUMES record '${record}' is not <vg>:<lv>:<size>:<fstype>:<label>"
  fi
  if [ -z "${VG_PV[$rec_vg]+set}" ]; then
    die "${PROFILE_PATH}: LOGICAL_VOLUMES record '${record}' names volume group '${rec_vg}', which VOLUME_GROUPS does not declare"
  fi
  if [ "${#rec_label}" -gt "$(label_limit "$rec_fstype")" ]; then
    die "${PROFILE_PATH}: label '${rec_label}' exceeds ${rec_fstype}'s $(label_limit "$rec_fstype")-byte limit"
  fi
  LV_OF_LABEL["$rec_label"]="$rec_vg"
done

for record in "${TIER_RECORDS[@]}"; do
  IFS=: read -r rec_role rec_vg rec_extra <<< "$record"
  if [ -z "$rec_role" ] || [ -z "$rec_vg" ] || [ -n "$rec_extra" ]; then
    die "${PROFILE_PATH}: ROLE_TIERS record '${record}' is not <role-label>:<vg>"
  fi
  if [ "${LV_OF_LABEL[$rec_role]:-}" != "$rec_vg" ]; then
    die "${PROFILE_PATH}: ROLE_TIERS puts role '${rec_role}' on volume group '${rec_vg}', but no LOGICAL_VOLUMES record carries that label there"
  fi
done

# ---------------------------------------------------------------------------
# Execution, probing and consent
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

# fs_type_of / fs_label_of — probe the superblock directly rather than the
# blkid cache, which goes stale after a relabel.
fs_type_of() { probe blkid -p -s TYPE -o value "$1"; }
fs_label_of() { probe blkid -p -s LABEL -o value "$1"; }

if [ "$DRY_RUN" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
  die "must run as root (it writes partition tables, volume groups and filesystems). Use --dry-run to see the plan unprivileged."
fi

note "profile:  ${PROFILE_PATH}"
note "node:     ${CFG[NODE_NAME]}"
if [ "$DRY_RUN" -eq 1 ]; then
  note "mode:     DRY RUN — every '+ ' line is printed and executed by nothing"
else
  note "mode:     LIVE"
fi

# ---------------------------------------------------------------------------
stage "1/6 storage-controller virtual disk"
# ---------------------------------------------------------------------------
if [ "${CFG[CONTROLLER_KIND]}" = "none" ]; then
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
stage "2/6 partition table on ${CFG[TARGET_DEVICE]}"
# ---------------------------------------------------------------------------
# The structure is fixed by the procedure — partition 1 is the EFI system
# partition, partition 2 is the LVM physical volume — while the device, the
# sizes and the partition names are the profile's.
target="${CFG[TARGET_DEVICE]}"
partlabels_seen="$(probe lsblk -rno PARTLABEL "$target" | grep . || true)"
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

# ---------------------------------------------------------------------------
stage "3/6 LVM physical volumes"
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
stage "4/6 volume groups"
# ---------------------------------------------------------------------------
for vg in "${VG_NAMES[@]}"; do
  if [ -n "$(probe vgs --noheadings -o vg_name "$vg")" ]; then
    note "no change: volume group ${vg} exists"
    continue
  fi
  run vgcreate "$vg" "${VG_PV[$vg]}"
done

# ---------------------------------------------------------------------------
stage "5/6 logical volumes"
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
stage "6/6 filesystems, carrying the labels install-storage-layout.sh resolves"
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

ensure_fs "${CFG[ESP_FSTYPE]}" "${CFG[ESP_LABEL]}" "${CFG[ESP_DEVICE]}"
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
