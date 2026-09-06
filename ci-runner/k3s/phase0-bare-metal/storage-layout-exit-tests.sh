#!/usr/bin/env bash
# storage-layout-exit-tests.sh — prove the four properties the bare-metal
# storage stage is required to have, WITHOUT touching any host.
#
#   1. the profile is DATA and is validated as data (a missing, unknown,
#      duplicated or malformed key is refused, naming it);
#   2. `--dry-run` against the committed poweredge profile emits the virtual
#      disk, partition, physical-volume, volume-group, logical-volume and mkfs
#      commands IN THAT ORDER, with the recorded values, and executes none of
#      them;
#   3. a destructive step refuses without `--i-consent-to-destroy` naming its
#      exact target, and the refusal names it;
#   4. the poweredge profile's volume groups, logical-volume sizes and tier
#      placements are the ones `profiles/poweredge-xubuntu.recorded-facts`
#      transcribes from the host record. Properties 1-3 all ask whether the
#      profile is WELL FORMED; only this one asks whether it is TRUE, which is
#      the gap a 64 GiB swap and a missing `nvmeb` sat in unnoticed until
#      2026-09-06.
#
# HOW IT STAYS OFF THE HOST. Every case runs `storage-layout.sh --dry-run`, so
# no mutating command is ever executed by construction. On top of that, each
# case prepends a scratch directory of FAKE tools to PATH:
#   - the read-only probes (`lsblk`, `blkid`, `pvs`, `vgs`, `lvs`) are faked so
#     the case controls the state the script sees, and so the suite's verdict
#     never depends on the block devices of the machine running it;
#   - every MUTATING command the script can reach (`sgdisk`, `wipefs`,
#     `partprobe`, `pvcreate`, `vgcreate`, `lvcreate`, `mkfs.*`, `mkswap`) is
#     faked as a TRIPWIRE that appends to a file and exits 0. A dry run that
#     executed anything would leave the tripwire file non-empty, which case D
#     asserts it does not.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/storage-layout.sh"
POWEREDGE="${HERE}/profiles/poweredge-xubuntu.env"

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
# every probe reports "nothing there" — i.e. a bare node.
make_bare_fakes() {  # make_bare_fakes DIR
  local dir="$1" tool
  mkdir -p "$dir"
  for tool in sgdisk wipefs partprobe udevadm pvcreate vgcreate lvcreate mkswap \
              mkfs.ext4 mkfs.xfs mkfs.vfat; do
    # Single-quoted on purpose: the body is the FAKE's source, expanded when
    # the fake runs, not when this suite writes it.
    mkfake "$dir" "$tool" 'printf "%s %s\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"; exit 0'
  done
  for tool in lsblk pvs vgs lvs; do
    mkfake "$dir" "$tool" 'exit 1'
  done
  mkfake "$dir" blkid 'exit 2'
}

run_layout() {  # run_layout FAKEDIR ARGS... -> stdout+stderr in REPLY_OUT, code in REPLY_RC
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

# A minimal, self-contained profile a case can mutate one key of. It declares
# no storage controller, so cases that are not about the virtual disk do not
# have to fake one.
write_profile() {  # write_profile PATH
  cat > "$1" <<'EOF'
NODE_NAME=fixture-node
CONTROLLER_KIND=none
CONTROLLER_CLI=
CONTROLLER_ID=
VD_ENCLOSURE=
VD_SLOTS=
VD_RAID_LEVEL=
VD_STRIP_KIB=
VD_CACHE_POLICY=
TARGET_DEVICE=/dev/fixture
ESP_DEVICE=/dev/fixture1
ESP_SIZE=1GiB
ESP_FSTYPE=vfat
ESP_LABEL=ESP
PV_PARTLABEL=lvm
VOLUME_GROUPS=fixturevg:/dev/fixture2
LOGICAL_VOLUMES=fixturevg:ci-cache:1TiB:ext4:ci-cache
ROLE_TIERS=ci-cache:fixturevg
OS_DISTRIBUTION=ubuntu
OS_RELEASE=fixturerelease
OS_ARCHITECTURE=amd64
OS_MIRROR=http://fixture.invalid/ubuntu
OS_SECURITY_MIRROR=http://fixture.invalid/ubuntu
OS_COMPONENTS=main universe
KERNEL_PACKAGE=linux-image-generic
INITRAMFS_GENERATOR=dracut
ROOT_LABEL=ci-cache
SWAP_LABEL=
BOOT_ENTRY_LABEL=fixture
OPERATOR_ACCOUNT=fixture-admin
OPERATOR_GROUPS=sudo
NODE_NETWORK_INTERFACE=auto
NODE_ADDRESS=auto
CLUSTER_ROLE=server
CLUSTER_JOIN_ADDRESS=
ADMISSION_CAPACITY_C=32
EOF
}

BARE="${TMPROOT}/bare-bin"
make_bare_fakes "$BARE"

# ---------------------------------------------------------------------------
echo "== A. The profile is data, and is validated as data =="
# ---------------------------------------------------------------------------

p="${TMPROOT}/missing-key.env"
write_profile "$p"
grep -v '^ROLE_TIERS=' "$p" > "${p}.tmp" && mv "${p}.tmp" "$p"
run_layout "$BARE" --dry-run "$p"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF "missing required profile key 'ROLE_TIERS'"; then
  ok "A1  a profile missing a required key is refused, naming the key"
else
  no "A1  a profile missing a required key is refused, naming the key (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

p="${TMPROOT}/unknown-key.env"
write_profile "$p"
printf 'NOT_A_PROFILE_KEY=x\n' >> "$p"
run_layout "$BARE" --dry-run "$p"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF "unknown profile key 'NOT_A_PROFILE_KEY'"; then
  ok "A2  an unknown key is refused, naming it"
else
  no "A2  an unknown key is refused, naming it (rc=${REPLY_RC})"
fi

p="${TMPROOT}/empty-value.env"
write_profile "$p"
sed 's|^TARGET_DEVICE=.*|TARGET_DEVICE=|' "$p" > "${p}.tmp" && mv "${p}.tmp" "$p"
run_layout "$BARE" --dry-run "$p"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF "profile key 'TARGET_DEVICE' must not be empty"; then
  ok "A3  a required key present but empty is refused, naming it"
else
  no "A3  a required key present but empty is refused, naming it (rc=${REPLY_RC})"
fi

p="${TMPROOT}/bad-record.env"
write_profile "$p"
sed 's|^LOGICAL_VOLUMES=.*|LOGICAL_VOLUMES=fixturevg:ci-cache:1TiB|' "$p" > "${p}.tmp" && mv "${p}.tmp" "$p"
run_layout "$BARE" --dry-run "$p"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF 'is not <vg>:<lv>:<size>:<fstype>:<label>'; then
  ok "A4  a malformed logical-volume record is refused, naming the record shape"
else
  no "A4  a malformed logical-volume record is refused, naming the record shape (rc=${REPLY_RC})"
fi

p="${TMPROOT}/orphan-tier.env"
write_profile "$p"
sed 's|^ROLE_TIERS=.*|ROLE_TIERS=ci-workvols:fixturevg|' "$p" > "${p}.tmp" && mv "${p}.tmp" "$p"
run_layout "$BARE" --dry-run "$p"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF "role 'ci-workvols'"; then
  ok "A5  a role tier with no logical volume carrying its label is refused"
else
  no "A5  a role tier with no logical volume carrying its label is refused (rc=${REPLY_RC})"
fi

p="${TMPROOT}/long-label.env"
write_profile "$p"
sed 's|^LOGICAL_VOLUMES=.*|LOGICAL_VOLUMES=fixturevg:wv:1TiB:xfs:thirteenchars|; s|^ROLE_TIERS=.*|ROLE_TIERS=thirteenchars:fixturevg|' "$p" > "${p}.tmp" && mv "${p}.tmp" "$p"
run_layout "$BARE" --dry-run "$p"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF "exceeds xfs's 12-byte limit"; then
  ok "A6  a label longer than its filesystem's limit is refused rather than truncated"
else
  no "A6  a label longer than its filesystem's limit is refused rather than truncated (rc=${REPLY_RC})"
fi

# ---------------------------------------------------------------------------
echo
echo "== B. --dry-run against the committed poweredge profile =="
# ---------------------------------------------------------------------------

run_layout "$BARE" --dry-run "$POWEREDGE"
POWEREDGE_OUT="$REPLY_OUT"
POWEREDGE_RC="$REPLY_RC"

if [ "$POWEREDGE_RC" -eq 0 ]; then
  ok "B1  exits 0"
else
  no "B1  exits 0 (rc=${POWEREDGE_RC})"
  printf '%s\n' "$POWEREDGE_OUT"
fi

# The ordering claim, with the values recorded for this node: the PERC RAID-5
# virtual disk over slots 0-6 at a 64 KB strip; the 1 GiB EFI system partition
# and the LVM partition; the physical volumes; the volume groups; the logical
# volumes; and the mkfs that puts each role label on one.
#
# The `nvmeb` rungs are here on purpose rather than only in B3. The node has TWO
# NVMe volume groups and the profile declared one until 2026-09-06, so the whole
# physical-volume -> volume-group -> logical-volume chain for the second drive is
# what a repeat of that drift would silently drop; asserting only the final mkfs
# would not notice a plan that never created the group it writes into.
if order_ok "$POWEREDGE_OUT" \
    'add vd type=raid5 drives=<enclosure>:0-6 strip=64 wb ra direct' \
    'sgdisk --new=1:0:+1G --typecode=1:ef00 --change-name=1:ESP /dev/sda' \
    'sgdisk --new=2:0:0 --typecode=2:8e00 --change-name=2:lvm /dev/sda' \
    'pvcreate --yes /dev/sda2' \
    'pvcreate --yes /dev/disk/by-id/nvme-WD_BLACK_SN8100_4000GB_25374X802154' \
    'vgcreate poweredge /dev/sda2' \
    'vgcreate nvmeb /dev/disk/by-id/nvme-WD_BLACK_SN8100_4000GB_25374X802154' \
    'lvcreate --yes -L 8G -n swap poweredge' \
    'lvcreate --yes -L 1T -n ci-cache poweredge' \
    'lvcreate --yes -L 1.5T -n ci-workvols nvmeb' \
    'mkfs.ext4 -q -L ci-cache /dev/poweredge/ci-cache' \
    'mkfs.xfs -q -m reflink=1 -L ci-workvols /dev/nvmeb/ci-workvols'; then
  ok "B2  virtual disk, partition, physical volumes, volume groups, logical volumes, mkfs — in that order"
else
  no "B2  virtual disk, partition, physical volumes, volume groups, logical volumes, mkfs — in that order"
fi

# The other two role tiers, and the filesystem types migrate-tier.sh's
# role_fstype decides: ci-containerd ext4 on nvmea, ci-workvols XFS with reflink
# on nvmeb — one tier per medium.
if printf '%s' "$POWEREDGE_OUT" | grep -qF 'mkfs.ext4 -q -L ci-containerd /dev/nvmea/ci-containerd' \
   && printf '%s' "$POWEREDGE_OUT" | grep -qF 'mkfs.xfs -q -m reflink=1 -L ci-workvols /dev/nvmeb/ci-workvols'; then
  ok "B3  all three role labels are made, ci-workvols as XFS with reflink=1 on nvmeb"
else
  no "B3  all three role labels are made, ci-workvols as XFS with reflink=1 on nvmeb"
fi

if printf '%s' "$POWEREDGE_OUT" | grep -qF 'mkfs.vfat -F 32 -n ESP /dev/sda1'; then
  ok "B4  the EFI system partition is made as FAT labelled ESP"
else
  no "B4  the EFI system partition is made as FAT labelled ESP"
fi

# VD_ENCLOSURE=auto is admissible ONLY if the resolver reads the right number
# off this node's controller — otherwise the profile owes a pinned literal. Give
# a copy of the profile a fake perccli that prints the enclosure table an H730P
# prints for `/c0/eall show`, carrying this node's backplane EID 32, and assert
# the plan pins `drives=32:0-6` instead of leaving the placeholder in.
PERC="${TMPROOT}/perc-bin"
make_bare_fakes "$PERC"
mkfake "$PERC" perccli64 '
case "$*" in
  "/c0/vall show")
    printf "Status = Failure\nDescription = No VDs have been configured\n"; exit 0 ;;
  "/c0/eall show")
    cat <<TABLE
CLI Version = 007.1327.0000.0000 Aug 30, 2021
Operating system = Linux 6.14.0-generic
Controller = 0
Status = Success
Description = None

Properties :
==========
---------------------------------------------------------------
EID State Slots PD PS Fans TSs Alms SIM ProdID    VendorSpecific
---------------------------------------------------------------
 32 OK       8   7  0    0   0    0   1 BP13G+EXP
---------------------------------------------------------------
TABLE
    exit 0 ;;
esac
printf "%s %s\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"; exit 0'

p="${TMPROOT}/perc-profile.env"
sed "s|^CONTROLLER_CLI=.*|CONTROLLER_CLI=${PERC}/perccli64|" "$POWEREDGE" > "$p"
run_layout "$PERC" --dry-run "$p"
if [ "$REPLY_RC" -eq 0 ] \
   && printf '%s' "$REPLY_OUT" | grep -qF 'add vd type=raid5 drives=32:0-6 strip=64 wb ra direct'; then
  ok "B5  VD_ENCLOSURE=auto resolves to this node's enclosure 32 off the controller"
else
  no "B5  VD_ENCLOSURE=auto resolves to this node's enclosure 32 off the controller (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

# ---------------------------------------------------------------------------
echo
echo "== C. Destructive steps refuse without consent naming the target =="
# ---------------------------------------------------------------------------

# A scratch PATH whose `blkid` reports a partition table already on the target
# device — i.e. the disk is populated, so repartitioning it destroys data.
POPULATED="${TMPROOT}/populated-bin"
make_bare_fakes "$POPULATED"
mkfake "$POPULATED" blkid '
for arg in "$@"; do dev="$arg"; done
if [ "$dev" = "/dev/sda" ]; then
  case " $* " in *" PTTYPE "*) echo gpt; exit 0 ;; esac
fi
exit 2'

run_layout "$POPULATED" --dry-run "$POWEREDGE"
if [ "$REPLY_RC" -ne 0 ] \
   && printf '%s' "$REPLY_OUT" | grep -qF 'REFUSED' \
   && printf '%s' "$REPLY_OUT" | grep -qF '/dev/sda'; then
  ok "C1  repartitioning a populated disk without consent exits non-zero and names the disk"
else
  no "C1  repartitioning a populated disk without consent exits non-zero and names the disk (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

run_layout "$POPULATED" --dry-run --i-consent-to-destroy=/dev/sdz "$POWEREDGE"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF 'REFUSED'; then
  ok "C2  consent naming a DIFFERENT target does not grant this one"
else
  no "C2  consent naming a DIFFERENT target does not grant this one (rc=${REPLY_RC})"
fi

run_layout "$POPULATED" --dry-run --i-consent-to-destroy=/dev/sda "$POWEREDGE"
if [ "$REPLY_RC" -eq 0 ] \
   && printf '%s' "$REPLY_OUT" | grep -qF 'consent given for /dev/sda' \
   && printf '%s' "$REPLY_OUT" | grep -qF 'wipefs --all /dev/sda'; then
  ok "C3  consent naming exactly that target lets the step through"
else
  no "C3  consent naming exactly that target lets the step through (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

# A populated LOGICAL VOLUME is a second, independent destructive target: the
# refusal must name the volume, not the disk.
LV_POPULATED="${TMPROOT}/lv-populated-bin"
make_bare_fakes "$LV_POPULATED"
mkfake "$LV_POPULATED" blkid '
for arg in "$@"; do dev="$arg"; done
if [ "$dev" = "/dev/poweredge/ci-cache" ]; then
  case " $* " in *" TYPE "*) echo ext4; exit 0 ;; *" LABEL "*) echo old-cache; exit 0 ;; esac
fi
exit 2'

run_layout "$LV_POPULATED" --dry-run "$POWEREDGE"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF 'REFUSED' \
   && printf '%s' "$REPLY_OUT" | grep -qF '/dev/poweredge/ci-cache'; then
  ok "C4  remaking a populated logical volume without consent refuses, naming the volume"
else
  no "C4  remaking a populated logical volume without consent refuses, naming the volume (rc=${REPLY_RC})"
fi

# ---------------------------------------------------------------------------
echo
echo "== D. --dry-run executes nothing, and a converged node changes nothing =="
# ---------------------------------------------------------------------------

if [ ! -s "$TRIPWIRE" ]; then
  ok "D1  no mutating command ran in any of the dry runs above"
else
  no "D1  a dry run EXECUTED a mutating command:"
  cat "$TRIPWIRE"
fi

# A node already in its profile's declared state: every probe reports exactly
# what the fixture profile declares.
CONVERGED="${TMPROOT}/converged-bin"
make_bare_fakes "$CONVERGED"
mkfake "$CONVERGED" lsblk 'printf "\nESP\nlvm\n"; exit 0'
mkfake "$CONVERGED" pvs 'echo "  /dev/fixture2"; exit 0'
mkfake "$CONVERGED" vgs 'echo "  fixturevg"; exit 0'
mkfake "$CONVERGED" lvs 'echo "  ci-cache"; exit 0'
mkfake "$CONVERGED" blkid '
for arg in "$@"; do dev="$arg"; done
case "$dev" in
  /dev/fixture1) case " $* " in *" TYPE "*) echo vfat;; *" LABEL "*) echo ESP;; esac; exit 0 ;;
  /dev/fixturevg/ci-cache) case " $* " in *" TYPE "*) echo ext4;; *" LABEL "*) echo ci-cache;; esac; exit 0 ;;
esac
exit 2'

p="${TMPROOT}/converged.env"
write_profile "$p"
run_layout "$CONVERGED" --dry-run "$p"
if [ "$REPLY_RC" -eq 0 ] \
   && printf '%s' "$REPLY_OUT" | grep -qF 'already in the state' \
   && ! printf '%s\n' "$REPLY_OUT" | grep -q '^+ '; then
  ok "D2  a node already in its profile's declared state plans no command and says so"
else
  no "D2  a node already in its profile's declared state plans no command and says so (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

run_layout "$BARE" --dry-run "$p"
if [ "$REPLY_RC" -eq 0 ] && ! printf '%s' "$REPLY_OUT" | grep -qF 'add vd'; then
  ok "D3  a profile declaring no storage controller skips the virtual-disk stage"
else
  no "D3  a profile declaring no storage controller skips the virtual-disk stage (rc=${REPLY_RC})"
fi

# ---------------------------------------------------------------------------
echo
echo "== E. The poweredge profile agrees with the recorded host facts =="
# ---------------------------------------------------------------------------
# The profile is the DATA the rebuild consumes;
# `profiles/poweredge-xubuntu.recorded-facts` is the host RECORD that data must
# agree with. They drifted silently once — swap declared at 64 GiB against the
# host's 8 GiB, and `ci-workvols` on `nvmea` when the host carries it on a
# second volume group `nvmeb` the profile never declared — because every case
# above asks whether the profile is WELL FORMED and none asked whether it is
# TRUE. This one does, and it is deliberately an equality in both directions: a
# recorded fact the profile omits fails it, and a volume group, volume or tier
# the profile invents fails it too.

FACTS="${HERE}/profiles/poweredge-xubuntu.recorded-facts"

# The profile side is read with the SAME parser every stage sources, so this
# case compares the record against what storage-layout.sh would actually act
# on — not against a second, independent reading of the same file.
profile_facts() {  # profile_facts PROFILE -> its vg/lv/tier records on stdout
  (
    die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
    # shellcheck source=ci-runner/k3s/phase0-bare-metal/profile.sh
    source "${HERE}/profile.sh"
    profile_load "$1"
    local vg record
    for vg in "${VG_NAMES[@]}"; do printf 'vg %s %s\n' "$vg" "${VG_PV[$vg]}"; done
    for record in "${LV_RECORDS[@]}"; do printf 'lv %s\n' "${record//:/ }"; done
    for record in "${TIER_RECORDS[@]}"; do printf 'tier %s\n' "${record//:/ }"; done
  )
}

recorded_facts() {  # recorded_facts PATH -> its records, comments and padding gone
  sed -e 's/#.*//' -e 's/[[:space:]]\{1,\}/ /g' -e 's/^ //' -e 's/ $//' "$1" | grep .
}

if [ -f "$FACTS" ]; then
  ok "E1  the recorded-facts table is committed beside the profile"
else
  no "E1  the recorded-facts table is committed beside the profile (${FACTS} is absent)"
fi

declared="$(profile_facts "$POWEREDGE" | LC_ALL=C sort)"
recorded="$(recorded_facts "$FACTS" | LC_ALL=C sort)"
if [ "$declared" = "$recorded" ]; then
  ok "E2  every volume group, logical volume size and tier placement matches the record"
else
  no "E2  the profile and the recorded facts disagree:"
  printf '%s\n' "$recorded" > "${TMPROOT}/recorded"
  printf '%s\n' "$declared" > "${TMPROOT}/declared"
  diff -u --label 'recorded facts' --label 'profile' \
    "${TMPROOT}/recorded" "${TMPROOT}/declared" | sed 's/^/        /'
fi

# E2 is an equality, so it is equally satisfied by correcting the RECORD to
# match a drifted profile — which would be exactly backwards. The three values
# the 2026-09-06 read corrected are therefore also asserted literally: moving
# one now takes an edit in two places, and the second place is a file whose
# header says it changes only by re-reading the host.
missing=""
while IFS= read -r want; do
  recorded_facts "$FACTS" | grep -qxF "$want" || missing="${missing}
        ${want}"
done <<'EOF'
lv poweredge swap 8GiB swap swap
vg nvmeb /dev/disk/by-id/nvme-WD_BLACK_SN8100_4000GB_25374X802154
tier ci-workvols nvmeb
EOF
if [ -z "$missing" ]; then
  ok "E3  the record still carries the three values the 2026-09-06 read corrected"
else
  no "E3  the record no longer carries:${missing}"
fi

echo
printf 'phase0 storage-layout: %d pass / %d fail\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
