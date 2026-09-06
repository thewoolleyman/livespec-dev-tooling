#!/usr/bin/env bash
# profile.sh — SOURCED by every stage in this directory (never run): the ONE
# parser for the per-node profile format.
#
# WHY IT IS SHARED. Each stage REFUSES a profile key it does not know, so a key
# added for a later stage would be rejected by an earlier one if every stage
# carried its own list. The profile header states the format is "identical for
# every node's profile, so one parser reads them all"; this file is that
# parser, and the list of keys below is the single place the format is defined.
#
# PARSED, NEVER SOURCED. The profile is read line by line as KEY=value data, so
# a profile cannot smuggle in procedure: it is data or it is rejected. Every
# key is REQUIRED to be PRESENT; the emptiness rules are applied after the whole
# file is read, because whether a key may be empty depends on another key's
# value.
#
# Expects the caller to have defined `die MESSAGE` (which must exit non-zero)
# before sourcing this file; every rejection goes through it.
#
# After `profile_load PATH` the caller has, as globals:
#   PROFILE_PATH           the path that was read
#   CFG[KEY]               every profile key's value
#   VG_NAMES[]             the declared volume groups, in profile order
#   VG_PV[vg]              each volume group's physical-volume device
#   LV_RECORDS[]           the raw <vg>:<lv>:<size>:<fstype>:<label> records
#   TIER_RECORDS[]         the raw <role-label>:<vg> records, in profile order
#   LV_OF_LABEL[label]     the volume group a labelled logical volume lives in
#   LV_NAME_OF_LABEL[l]    that logical volume's name
#   LV_FSTYPE_OF_LABEL[l]  that logical volume's filesystem type

# Every key a profile must carry, in the order the profile itself declares them.
PROFILE_REQUIRED_KEYS=(
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
  OS_DISTRIBUTION
  OS_RELEASE
  OS_ARCHITECTURE
  OS_MIRROR
  OS_SECURITY_MIRROR
  OS_COMPONENTS
  KERNEL_PACKAGE
  INITRAMFS_GENERATOR
  ROOT_LABEL
  SWAP_LABEL
  BOOT_ENTRY_LABEL
  OPERATOR_ACCOUNT
  OPERATOR_GROUPS
  NODE_NETWORK_INTERFACE
  NODE_ADDRESS
  CLUSTER_ROLE
  CLUSTER_JOIN_ADDRESS
  ADMISSION_CAPACITY_C
)

# An ext4 label holds 16 bytes, an XFS label 12, a FAT label 11 and a swap
# label 15; a longer name is silently TRUNCATED by mkfs, which is how a live
# tier label was lost once already (`.ai/ci-node-storage-tiers.md`). Refuse it
# here instead.
profile_label_limit() {
  case "$1" in
    xfs) printf '12' ;;
    vfat) printf '11' ;;
    swap) printf '15' ;;
    *) printf '16' ;;
  esac
}

profile_load() {
  PROFILE_PATH="$1"
  local key line lineno record
  local rec_vg rec_pv rec_lv rec_size rec_fstype rec_label rec_role rec_extra

  declare -gA CFG=()
  declare -gA VG_PV=()
  declare -gA LV_OF_LABEL=()
  declare -gA LV_NAME_OF_LABEL=()
  declare -gA LV_FSTYPE_OF_LABEL=()
  VG_NAMES=()

  local -A known=()
  for key in "${PROFILE_REQUIRED_KEYS[@]}"; do known["$key"]=1; done

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
    if [ -z "${known[$key]:-}" ]; then
      die "${PROFILE_PATH}:${lineno}: unknown profile key '${key}'"
    fi
    if [ -n "${CFG[$key]+set}" ]; then
      die "${PROFILE_PATH}:${lineno}: profile key '${key}' given more than once"
    fi
    CFG["$key"]="${line#*=}"
  done < "$PROFILE_PATH"

  for key in "${PROFILE_REQUIRED_KEYS[@]}"; do
    if [ -z "${CFG[$key]+set}" ]; then
      die "${PROFILE_PATH}: missing required profile key '${key}'"
    fi
  done

  # Emptiness. CLUSTER_JOIN_ADDRESS is empty for a node that forms its own
  # cluster; SWAP_LABEL is empty for a node with no swap volume; the controller
  # and virtual-disk keys are empty for a node that has no storage controller.
  # Every other key must carry a value.
  local -a may_be_empty=(CLUSTER_JOIN_ADDRESS SWAP_LABEL)
  if [ "${CFG[CONTROLLER_KIND]}" = "none" ]; then
    may_be_empty+=(CONTROLLER_CLI CONTROLLER_ID VD_ENCLOSURE VD_SLOTS VD_RAID_LEVEL VD_STRIP_KIB VD_CACHE_POLICY)
  fi
  local -A optional=()
  for key in "${may_be_empty[@]}"; do optional["$key"]=1; done
  for key in "${PROFILE_REQUIRED_KEYS[@]}"; do
    if [ -z "${CFG[$key]}" ] && [ -z "${optional[$key]:-}" ]; then
      die "${PROFILE_PATH}: profile key '${key}' must not be empty"
    fi
  done

  # -------------------------------------------------------------------------
  # Records
  # -------------------------------------------------------------------------
  local -a vg_records=()
  read -r -a vg_records <<< "${CFG[VOLUME_GROUPS]}"
  read -r -a LV_RECORDS <<< "${CFG[LOGICAL_VOLUMES]}"
  read -r -a TIER_RECORDS <<< "${CFG[ROLE_TIERS]}"

  for record in "${vg_records[@]}"; do
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

  for record in "${LV_RECORDS[@]}"; do
    IFS=: read -r rec_vg rec_lv rec_size rec_fstype rec_label rec_extra <<< "$record"
    if [ -z "$rec_vg" ] || [ -z "$rec_lv" ] || [ -z "$rec_size" ] || [ -z "$rec_fstype" ] || [ -z "$rec_label" ] || [ -n "$rec_extra" ]; then
      die "${PROFILE_PATH}: LOGICAL_VOLUMES record '${record}' is not <vg>:<lv>:<size>:<fstype>:<label>"
    fi
    if [ -z "${VG_PV[$rec_vg]+set}" ]; then
      die "${PROFILE_PATH}: LOGICAL_VOLUMES record '${record}' names volume group '${rec_vg}', which VOLUME_GROUPS does not declare"
    fi
    if [ "${#rec_label}" -gt "$(profile_label_limit "$rec_fstype")" ]; then
      die "${PROFILE_PATH}: label '${rec_label}' exceeds ${rec_fstype}'s $(profile_label_limit "$rec_fstype")-byte limit"
    fi
    LV_OF_LABEL["$rec_label"]="$rec_vg"
    # shellcheck disable=SC2034  # read by the stages that source this file
    LV_NAME_OF_LABEL["$rec_label"]="$rec_lv"
    # shellcheck disable=SC2034  # read by the stages that source this file
    LV_FSTYPE_OF_LABEL["$rec_label"]="$rec_fstype"
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
}
