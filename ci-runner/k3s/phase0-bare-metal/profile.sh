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
# key in PROFILE_REQUIRED_KEYS is REQUIRED to be PRESENT; the emptiness rules
# are applied after the whole file is read, because whether a key may be empty
# depends on another key's value.
#
# THE ONE EXCEPTION, AND WHY. PROFILE_KEY_DEFAULTS below lists keys a profile
# MAY omit, each with the value the parser fills in when it does. Every one of
# them was added AFTER the first node's profile existed, and each default is the
# behaviour that was implicit before the key had a name — `whole-device`
# partitioning, nothing preserved, no taint, no join secret. A profile that
# predates the key therefore keeps parsing AND keeps behaving identically, which
# is not true of a required key: making one required turns "this node was
# written before the second node existed" into a parse failure. A profile is
# still free to state the default explicitly, and the committed one does.
#
# HOW THIS FORMAT SPELLS "NO LABEL". A filesystem label is a string a node's
# filesystem either carries or does not; the format's spelling for "does not" is
# the EMPTY value, which is what SWAP_LABEL has always meant on a node with no
# swap volume. ESP_LABEL and ROOT_LABEL take the same spelling, and only under
# `DISK_PLAN=free-space`: that plan describes filesystems the node ALREADY
# carries, whose labels are the host's fact and may genuinely be none, while
# `whole-device` MAKES both filesystems with `mkfs -L`, so an empty label there
# would be a label the procedure chose to leave off and the later stages then
# could not resolve. An empty ROOT_LABEL is consequently a profile stage 2 must
# never run against — see `profile_require_root_volume` below, which is the
# refusal, not a comment.
#
# Expects the caller to have defined `die MESSAGE` (which must exit non-zero)
# before sourcing this file; every rejection goes through it.
#
# After `profile_load PATH` the caller has, as globals:
#   PROFILE_PATH           the path that was read
#   CFG[KEY]               every profile key's value, defaults already applied
#   PRESERVED_DEVICES[]    the devices no stage may write to, in profile order
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

# Keys a profile MAY omit, and the value the parser supplies when it does. Read
# the header above for why these are defaulted rather than required: each
# default is the behaviour that was implicit before the key existed.
#
#   DISK_PLAN             `whole-device` — the device is the node's to erase:
#                         zap it and write the declared table over the top.
#                         `free-space` — the device already carries an operating
#                         system: leave every existing partition alone and take
#                         ONLY the unpartitioned tail.
#   PRESERVED_PARTITIONS  space-separated device paths no stage may write to.
#                         REQUIRED to be non-empty under `free-space` (that plan
#                         exists to protect something) and REQUIRED to be empty
#                         under `whole-device` (which erases the whole device,
#                         so a partition named here could not survive it and
#                         listing one would be a promise the plan cannot keep).
#   CLUSTER_TOKEN_FILE    the path on the node holding the token an `agent` (or
#                         a joining server) authenticates to CLUSTER_JOIN_ADDRESS
#                         with. A PATH, never the token: this tree carries no
#                         secret. Empty for a node that forms its own cluster.
#   NODE_TAINTS           space-separated `key=value:Effect` taints the node
#                         registers with. Empty for a node that takes general
#                         work.
#   CHURN_KUBECONFIG_FILE the path on the node holding the kubeconfig a
#                         NODE-LOCAL churn-slot reapply timer authenticates to
#                         the API with. A PATH, never the credential: this tree
#                         carries no secret. Empty for a node that runs no such
#                         timer — which is every node today, and is what the
#                         SERVER means permanently: a server patches node status
#                         through its own admin file
#                         (/etc/rancher/k3s/k3s.yaml), which an AGENT does not
#                         have. See
#                         ../../phase2/node-status-credential/README.md for the
#                         credential this path receives and who mints it.
#   CI_NODE_FACILITIES    `full` — the node carries the three LABEL-keyed CI
#                         storage tiers and the facilities a CI JOB executes
#                         against (the fleet-patched ARC container hook, the
#                         pool-provided sccache binary, its cache telemetry).
#                         `none` — the node joins the pool but executes no CI
#                         job, so it declares no physical volume, no volume
#                         group, no logical volume and no tier, and the stages
#                         and roles that build or feed them self-gate off.
#                         `full` is the default because it is what both nodes
#                         written before the key existed are.
#   FACTORY_NODE          `true` renders this node's FACTORY node label, which
#                         the kubernetes-sandbox-backend selects factory
#                         capacity on. `false` is the default — the behaviour
#                         before the key existed.
#   NODE_DATA_DIR         the directory k3s keeps THIS node's data in
#                         (`--data-dir`): the bundled containerd's store, the
#                         kubelet root and the local-path root. Empty for a node
#                         that takes k3s's own default of /var/lib/rancher/k3s,
#                         which is every node whose containerd store is a BIND
#                         onto a role-labelled tier instead.
#   KUBELET_ARGS          space-separated kubelet arguments belonging to THIS
#                         node, APPENDED to the fleet's shared list rather than
#                         replacing it. Empty for a node that needs none. This
#                         is where a node's coexistence reservations live —
#                         system-reserved, kube-reserved, eviction-hard — because
#                         they are measured against the OTHER workloads on that
#                         one machine and so belong to no other node.
# `-g` on purpose: a stage that sources this file from inside a function (the
# exit tests read a profile that way) would otherwise get a table scoped to
# that function.
declare -gA PROFILE_KEY_DEFAULTS=(
  [DISK_PLAN]=whole-device
  [PRESERVED_PARTITIONS]=""
  [CLUSTER_TOKEN_FILE]=""
  [NODE_TAINTS]=""
  [CHURN_KUBECONFIG_FILE]=""
  [CI_NODE_FACILITIES]=full
  [FACTORY_NODE]=false
  [NODE_DATA_DIR]=""
  [KUBELET_ARGS]=""
)

# The ONE taint key the pool's scheduling gate uses, and the same string
# ansible/roles/node_taints/defaults/main.yml declares. Named here because
# `CI_NODE_FACILITIES=none` is refused without it: a node that carries none of
# the CI facilities must also be CLOSED to CI scheduling, and the two halves of
# "taking nothing" are checked against each other rather than left to agree.
PROFILE_CI_TAINT_KEY="node-role/ci"

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
  PRESERVED_DEVICES=()

  local -A known=()
  for key in "${PROFILE_REQUIRED_KEYS[@]}"; do known["$key"]=1; done
  for key in "${!PROFILE_KEY_DEFAULTS[@]}"; do known["$key"]=1; done

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

  # A defaulted key the profile did not state takes its default HERE, before any
  # rule below reads it, so every rule sees one value per key whether the profile
  # spelled it out or not.
  for key in "${!PROFILE_KEY_DEFAULTS[@]}"; do
    if [ -z "${CFG[$key]+set}" ]; then
      CFG["$key"]="${PROFILE_KEY_DEFAULTS[$key]}"
    fi
  done

  # -------------------------------------------------------------------------
  # The two enumerated POSTURES, validated FIRST
  #
  # Before the emptiness rules, because CI_NODE_FACILITIES SELECTS them: under
  # `none` four storage keys become permissibly empty, and an unrecognised value
  # falls through to `full`, where those same four keys are required non-empty.
  # So a misspelt posture used to be reported as an empty PV_PARTLABEL — a
  # message about the wrong key, pointing an operator at the wrong edit.
  # Measured on 2026-10-13 with `CI_NODE_FACILITIES=non`, which is exactly the
  # typo the enum exists to catch (the key misspelt is caught as an unknown key;
  # the VALUE misspelt was not). Validating the enums here reports the posture
  # as the posture, and the emptiness rules below then run against a value the
  # parser has already agreed to.
  # -------------------------------------------------------------------------
  case "${CFG[FACTORY_NODE]}" in
    true | false) ;;
    *) die "${PROFILE_PATH}: FACTORY_NODE must be 'true' or 'false', got '${CFG[FACTORY_NODE]}'" ;;
  esac
  case "${CFG[CI_NODE_FACILITIES]}" in
    full | none) ;;
    *) die "${PROFILE_PATH}: CI_NODE_FACILITIES must be 'full' or 'none', got '${CFG[CI_NODE_FACILITIES]}'" ;;
  esac

  # Emptiness. CLUSTER_JOIN_ADDRESS is empty for a node that forms its own
  # cluster; SWAP_LABEL is empty for a node with no swap volume; the controller
  # and virtual-disk keys are empty for a node that has no storage controller;
  # the three defaulted list-or-path keys are empty for the node the default
  # describes. Every other key must carry a value.
  local -a may_be_empty=(
    CLUSTER_JOIN_ADDRESS
    SWAP_LABEL
    PRESERVED_PARTITIONS
    CLUSTER_TOKEN_FILE
    NODE_TAINTS
    CHURN_KUBECONFIG_FILE
    NODE_DATA_DIR
    KUBELET_ARGS
  )
  # A node declaring NO CI facilities declares no storage for them either, and
  # the four keys below are the storage it would otherwise declare: the
  # partition label of the physical volume, the volume group over it, the
  # logical volumes in it and the role tiers on them. They are permitted empty
  # here and REQUIRED empty further down — a node cannot name a tier it has
  # said it does not carry.
  if [ "${CFG[CI_NODE_FACILITIES]}" = "none" ]; then
    may_be_empty+=(PV_PARTLABEL VOLUME_GROUPS LOGICAL_VOLUMES ROLE_TIERS)
  fi
  if [ "${CFG[CONTROLLER_KIND]}" = "none" ]; then
    may_be_empty+=(CONTROLLER_CLI CONTROLLER_ID VD_ENCLOSURE VD_SLOTS VD_RAID_LEVEL VD_STRIP_KIB VD_CACHE_POLICY)
  fi
  # The header's "no label" spelling, and it is deliberately plan-conditional.
  # Under `free-space` the EFI system partition and the root are filesystems the
  # node already carries: their labels are the host's fact, read off the device,
  # and "none" is a fact a plain installer leaves behind routinely. Under
  # `whole-device` this procedure MAKES both with `mkfs -L`, so an empty label
  # is not a fact about the node but a label the run would decline to write —
  # and the fstab stage 2 renders finds root and the ESP by LABEL, so it would
  # then have nothing to find.
  if [ "${CFG[DISK_PLAN]}" = "free-space" ]; then
    may_be_empty+=(ESP_LABEL ROOT_LABEL)
  fi
  local -A optional=()
  for key in "${may_be_empty[@]}"; do optional["$key"]=1; done
  for key in "${PROFILE_REQUIRED_KEYS[@]}" "${!PROFILE_KEY_DEFAULTS[@]}"; do
    if [ -z "${CFG[$key]}" ] && [ -z "${optional[$key]:-}" ]; then
      die "${PROFILE_PATH}: profile key '${key}' must not be empty"
    fi
  done

  # -------------------------------------------------------------------------
  # The two plans, and the keys each one obliges
  #
  # Both rules below refuse a profile that PARSES but describes a run the stage
  # cannot honour, which is the only kind of wrong profile the stages cannot
  # catch for themselves: `free-space` with nothing preserved would take the
  # protective plan and protect nothing, and `whole-device` with a preserved
  # partition would erase the very partition the key promises to keep. Both were
  # silent before they were refusals.
  # -------------------------------------------------------------------------
  case "${CFG[DISK_PLAN]}" in
    whole-device)
      if [ -n "${CFG[PRESERVED_PARTITIONS]}" ]; then
        die "${PROFILE_PATH}: DISK_PLAN=whole-device erases ${CFG[TARGET_DEVICE]} entirely, so it cannot preserve '${CFG[PRESERVED_PARTITIONS]}'; use DISK_PLAN=free-space to keep a partition"
      fi ;;
    free-space)
      if [ -z "${CFG[PRESERVED_PARTITIONS]}" ]; then
        die "${PROFILE_PATH}: DISK_PLAN=free-space must name the partitions it preserves in PRESERVED_PARTITIONS"
      fi ;;
    *) die "${PROFILE_PATH}: DISK_PLAN must be 'whole-device' or 'free-space', got '${CFG[DISK_PLAN]}'" ;;
  esac
  # shellcheck disable=SC2034  # read by the stages that source this file
  read -r -a PRESERVED_DEVICES <<< "${CFG[PRESERVED_PARTITIONS]}"

  # -------------------------------------------------------------------------
  # What the `none` posture OBLIGES
  #
  # The enums themselves were validated above, before the emptiness rules they
  # select. What is left here is the part that has to run after the records are
  # in hand: a profile that PARSES and then means something the stages cannot
  # honour.
  # -------------------------------------------------------------------------
  case "${CFG[CI_NODE_FACILITIES]}" in
    full)
      # Nothing to oblige: the three storage keys are required non-empty
      # already, which IS the `full` shape.
      ;;
    none)
      # TAKING NOTHING, SAID THREE WAYS, AND CHECKED AGAINST ITSELF. A node that
      # carries none of the CI facilities must also declare no storage for them,
      # admit no churn slot, and be CLOSED to CI scheduling. Each of the three
      # is independently editable, so a node is opened to CI only by a profile
      # edit that satisfies all of them at once — which is the property that
      # makes "opening this node later is a profile edit plus an apply" true
      # rather than hopeful.
      local key
      for key in PV_PARTLABEL VOLUME_GROUPS LOGICAL_VOLUMES ROLE_TIERS; do
        if [ -n "${CFG[$key]}" ]; then
          die "${PROFILE_PATH}: CI_NODE_FACILITIES=none declares no CI storage tier, so '${key}' must be empty; it names '${CFG[$key]}'. Set CI_NODE_FACILITIES=full if this node really does carry the pool's tiers."
        fi
      done
      if [ "${CFG[ADMISSION_CAPACITY_C]}" != "0" ]; then
        die "${PROFILE_PATH}: CI_NODE_FACILITIES=none executes no CI job, so ADMISSION_CAPACITY_C must be 0; it is '${CFG[ADMISSION_CAPACITY_C]}'. A node advertising churn slots it has no facilities to serve admits work it cannot run."
      fi
      case " ${CFG[NODE_TAINTS]} " in
        *" ${PROFILE_CI_TAINT_KEY}="*) ;;
        *) die "${PROFILE_PATH}: CI_NODE_FACILITIES=none must also be CLOSED to CI scheduling, so NODE_TAINTS must carry a ${PROFILE_CI_TAINT_KEY}=<value>:<Effect> record; it is '${CFG[NODE_TAINTS]}'. ADMISSION_CAPACITY_C=0 stops Kueue's admission; the taint is what stops the scheduler." ;;
      esac ;;
    # No third arm: the enum was validated above, before the emptiness rules it
    # selects, so an unrecognised value has already been refused by name and
    # cannot reach here.
  esac

  # CLUSTER_ROLE selects the node-local step plan (now the ansible/ci-pool.yml roles,
  # applied with `just ansible-apply`; it was ../phase2/install-node.sh before R5/9btv); an agent
  # has no cluster to run in without both the address it joins and the token
  # file it authenticates with, and a missing one of those fails at the node,
  # after the storage and the base OS are already written.
  case "${CFG[CLUSTER_ROLE]}" in
    server) ;;
    agent)
      if [ -z "${CFG[CLUSTER_JOIN_ADDRESS]}" ] || [ -z "${CFG[CLUSTER_TOKEN_FILE]}" ]; then
        die "${PROFILE_PATH}: CLUSTER_ROLE=agent must name both CLUSTER_JOIN_ADDRESS and CLUSTER_TOKEN_FILE"
      fi ;;
    *) die "${PROFILE_PATH}: CLUSTER_ROLE must be 'server' or 'agent', got '${CFG[CLUSTER_ROLE]}'" ;;
  esac

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

# profile_require_root_volume — the gate base-os-install.sh (stage 2) passes
# through before it derives anything from ROOT_LABEL. Call after profile_load.
#
# WHY IT IS NOT JUST "the label resolves to no volume". An empty ROOT_LABEL is
# the header's spelling for "the root filesystem carries no label", which a
# `free-space` node states because its root is a filesystem it KEEPS. Stage 2
# installs an operating system onto the root LOGICAL VOLUME its profile names,
# so against such a profile it has nothing to install onto — and the honest
# refusal says THAT. Left to the resolution failure alone the stage exits with
# `ROOT_LABEL='' names no LOGICAL_VOLUMES record`, which describes the mechanism
# and not the reason, and reads as a malformed profile rather than as the node
# correctly declaring that this stage is not one it runs.
profile_require_root_volume() {
  if [ -z "${CFG[ROOT_LABEL]}" ]; then
    die "${PROFILE_PATH}: ROOT_LABEL is empty, which this format spells as 'the root filesystem carries no label' — a node that KEEPS the root it already has (DISK_PLAN=${CFG[DISK_PLAN]}). This stage installs an operating system onto the root logical volume ROOT_LABEL names, so it has no volume to install onto and would debootstrap over the operating system that plan exists to preserve. Stage 2 is not a stage ${CFG[NODE_NAME]} runs; run stage 1 and then ../provision-k3s.sh."
  fi
}
