#!/usr/bin/env bash
# storage-layout-exit-tests.sh — prove the six properties the bare-metal
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
#      2026-09-06;
#   5. a `free-space` profile — a node that KEEPS the operating system already
#      on its device — plans no controller command and no zap, adds exactly one
#      partition, and REFUSES any step naming a partition it preserves; and the
#      `whole-device` plan the first node takes is byte-for-byte the plan it
#      took before `free-space` existed;
#   6. the COMMITTED second node's profile, `profiles/gmktec-xubuntu.env`,
#      declares that node's measured facts and yields the plan they imply
#      through this same script — no controller command, one new partition at
#      the number its own table leaves free, the one volume group and the three
#      labelled tier filesystems — and refuses every step naming either of the
#      two partitions the running node boots from. Property 5 asks whether the
#      PLAN is right against a fixture; only this one asks whether the second
#      NODE's committed data is. As for the first node, that data is also held
#      against a RECORD (`profiles/gmktec-xubuntu.recorded-facts`) and the plan
#      against a committed capture (`profiles/gmktec-xubuntu.expected-plan`);
#   7. the TOOL PREFLIGHT never lets a run start a layout it cannot finish.
#      Under `free-space` an absent tool's package is installed BEFORE the
#      first partition command; under `whole-device` an absent tool refuses
#      before any mutation, printed as `WOULD REFUSE:` rather than taken under
#      `--dry-run`; and a node carrying every tool sees neither. This is the
#      one property whose fixtures REPLACE the PATH rather than prepending to
#      it — see §H.
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
POWEREDGE_PLAN="${HERE}/profiles/poweredge-xubuntu.expected-plan"

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
  # UNLINKED FIRST, and that is not tidiness. `make_selfcontained_path` fills a
  # scratch directory with SYMLINKS to real host utilities, and a `>` redirect
  # onto a symlink writes THROUGH it: overwriting a fake that happens to be one
  # of those links would truncate `/usr/bin/id` on the machine running this
  # suite. It did, once, before this line existed. A suite whose whole claim is
  # that it touches no host cannot leave that to the order its callers happen
  # to use.
  rm -f "${1}/${2}"
  printf '#!/usr/bin/env bash\n%s\n' "$3" > "${1}/${2}"
  chmod +x "${1}/${2}"
}

# A scratch PATH directory in which every mutating command is a tripwire and
# every probe reports "nothing there" — i.e. a bare node.
make_bare_fakes() {  # make_bare_fakes DIR
  local dir="$1" tool
  mkdir -p "$dir"
  # `apt-get` is a tripwire like the rest and for a sharper reason than the
  # others: the host running this suite is the one kind of machine that really
  # does have it, so a preflight bug that reached an install would install
  # packages onto the developer's own workstation. Faked, it lands in the
  # tripwire file that §D1 and §I1 assert is empty instead.
  for tool in sgdisk wipefs partprobe udevadm pvcreate vgcreate lvcreate mkswap \
              mkfs.ext4 mkfs.xfs mkfs.vfat apt-get; do
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

# The utilities storage-layout.sh and profile.sh actually call, so that §H can
# REPLACE the whole PATH rather than prepend to it. Prepending cannot make a
# tool ABSENT — the host's own copy is one directory further along — and
# absence is precisely what the preflight cases have to construct. `bash` is
# here because every fake, and the script itself, is `#!/usr/bin/env bash`, and
# `env` resolves that name against the PATH it is handed.
PATH_UTILITIES=(bash cat id grep awk paste basename dirname)

make_selfcontained_path() {  # make_selfcontained_path DIR [ABSENT-TOOL...]
  local dir="$1"; shift
  local util real absent
  make_bare_fakes "$dir"
  for util in "${PATH_UTILITIES[@]}"; do
    # `type -P` and not `command -v`: the latter answers with the NAME when the
    # caller's shell has one of these as a function or an alias, and a symlink
    # named `grep` pointing at `grep` resolves to itself. The absolute-path
    # check is what turns that into a stop rather than a directory of tools
    # that silently are not there.
    real="$(type -P "$util")"
    case "$real" in
      /*) ;;
      *) echo "FATAL: the host running this suite has no ${util} on PATH" >&2; exit 1 ;;
    esac
    ln -sf "$real" "${dir}/${util}"
  done
  for absent in "$@"; do
    rm -f "${dir}/${absent}"
  done
}

run_layout_only() {  # run_layout_only DIR ARGS... — PATH REPLACED, not prepended
  local dir="$1"; shift
  REPLY_OUT="$(PATH="$dir" "$SCRIPT" "$@" 2>&1)"
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

# The same fixture as a `free-space` node: a device whose partitions 1 and 2
# already carry an operating system this procedure must not touch, with the
# tiers to go in the unpartitioned tail. It states the two new keys by APPENDING
# them, which is itself part of the claim — the base fixture above names neither,
# and every case that uses it asserts the whole-device behaviour those keys
# default to.
write_freespace_profile() {  # write_freespace_profile PATH [PV-DEVICE]
  local path="$1" pv="${2:-/dev/fixture3}"
  write_profile "$path"
  sed "s|^VOLUME_GROUPS=.*|VOLUME_GROUPS=fixturevg:${pv}|" "$path" > "${path}.tmp"
  mv "${path}.tmp" "$path"
  cat >> "$path" <<'EOF'
DISK_PLAN=free-space
PRESERVED_PARTITIONS=/dev/fixture1 /dev/fixture2
EOF
}

BARE="${TMPROOT}/bare-bin"
make_bare_fakes "$BARE"

# A device that already carries two partitions: `lsblk` answers both the label
# probe and the partition-number probe, so the script derives "the next free
# number is 3" from the table rather than from an assumption.
FREESPACE="${TMPROOT}/freespace-bin"
make_bare_fakes "$FREESPACE"
mkfake "$FREESPACE" lsblk '
case " $* " in
  *" PARTLABEL "*) printf "\nrootfs\nEFI\n"; exit 0 ;;
  *" PARTN "*) printf "\n1\n2\n"; exit 0 ;;
esac
exit 1'

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

# ---------------------------------------------------------------------------
echo
echo "== F. The free-space plan, and the whole-device plan it must not disturb =="
# ---------------------------------------------------------------------------
# `DISK_PLAN=free-space` exists for a node that KEEPS the operating system
# already on its device: partitions it did not create carry the root and the
# EFI system partition, and only the unpartitioned tail is the procedure's to
# take. Everything this section asserts is about what the plan does NOT do —
# which is the half a plan cannot demonstrate by running correctly.

p="${TMPROOT}/freespace.env"
write_freespace_profile "$p"
run_layout "$FREESPACE" --dry-run "$p"
FS_OUT="$REPLY_OUT"
FS_RC="$REPLY_RC"
new_partition_lines="$(printf '%s\n' "$FS_OUT" | grep -c '^+ sgdisk --new' || true)"

if [ "$FS_RC" -eq 0 ] \
   && ! printf '%s\n' "$FS_OUT" | grep -q '^+ .*add vd' \
   && ! printf '%s\n' "$FS_OUT" | grep -q '^+ .*--zap-all' \
   && ! printf '%s\n' "$FS_OUT" | grep -q '^+ wipefs'; then
  ok "F1  a free-space plan emits no controller command and no zap"
else
  no "F1  a free-space plan emits no controller command and no zap (rc=${FS_RC})"
  printf '%s\n' "$FS_OUT"
fi

# ONE partition, numbered from the table the device actually carries (1 and 2
# are taken, so 3), typed LVM, and taking the largest free region — which is
# what sgdisk's `0:0` means, and why no size for it appears in the profile.
if [ "$new_partition_lines" -eq 1 ] \
   && printf '%s\n' "$FS_OUT" | grep -qxF '+ sgdisk --new=3:0:0 --typecode=3:8e00 --change-name=3:lvm /dev/fixture'; then
  ok "F2  exactly one new partition, at the next free number, typed LVM over the free region"
else
  no "F2  exactly one new partition, at the next free number, typed LVM over the free region (${new_partition_lines} new-partition command(s))"
  printf '%s\n' "$FS_OUT"
fi

# The node boots off the EFI system partition it already has. A plan that
# remade it would take the bootloader with it, so the plan must not contain the
# mkfs at all — not merely refuse it later.
if ! printf '%s\n' "$FS_OUT" | grep -q '^+ mkfs.vfat' \
   && printf '%s' "$FS_OUT" | grep -qF 'already boots from'; then
  ok "F3  the existing EFI system partition is left alone, and the plan says so"
else
  no "F3  the existing EFI system partition is left alone, and the plan says so"
  printf '%s\n' "$FS_OUT"
fi

# The tiers still get built: preservation is about the partitions named, not
# about the run doing nothing.
if printf '%s' "$FS_OUT" | grep -qF 'pvcreate --yes /dev/fixture3' \
   && printf '%s' "$FS_OUT" | grep -qF 'mkfs.ext4 -q -L ci-cache /dev/fixturevg/ci-cache'; then
  ok "F4  the tail partition still becomes the physical volume, the group and the labelled filesystem"
else
  no "F4  the tail partition still becomes the physical volume, the group and the labelled filesystem"
fi

# The refusal that makes the rest of it trustworthy. This profile points its
# physical volume at partition 1 — the node's root — which is a step that WOULD
# have run: `pvcreate` on an empty-looking device needs no consent at all.
p="${TMPROOT}/freespace-clobber.env"
write_freespace_profile "$p" /dev/fixture1
run_layout "$FREESPACE" --dry-run "$p"
if [ "$REPLY_RC" -ne 0 ] \
   && printf '%s' "$REPLY_OUT" | grep -qF 'REFUSED' \
   && printf '%s' "$REPLY_OUT" | grep -qF '/dev/fixture1' \
   && printf '%s' "$REPLY_OUT" | grep -qF 'PRESERVED_PARTITIONS'; then
  ok "F5  a step naming a preserved partition exits non-zero and names that partition"
else
  no "F5  a step naming a preserved partition exits non-zero and names that partition (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

# Preservation is not consent's stronger cousin, it is a different key: consent
# names a target the profile is willing to lose, so naming a preserved one must
# not unlock it.
run_layout "$FREESPACE" --dry-run --i-consent-to-destroy=/dev/fixture1 "$p"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF 'REFUSED'; then
  ok "F6  --i-consent-to-destroy does not unlock a preserved partition"
else
  no "F6  --i-consent-to-destroy does not unlock a preserved partition (rc=${REPLY_RC})"
fi

# The same clobber, on a device that looks like a REAL one: a preserved root
# carries a filesystem, and a populated device is exactly what makes a step ask
# for consent. So this is the case where the two keys meet, and the one the
# live node would actually hit — F5's bare fixture reaches the preservation
# guard through `run`, whereas here `require_consent` is reached first.
#
# Asserting the WORDING, not just the exit code, is the point. Both orderings
# refuse; only one of them tells the operator the truth about why. A refusal
# reading "Re-run with --i-consent-to-destroy=/dev/fixture1" is advice that a
# preserved partition can be unlocked, which is the one thing this key promises
# it cannot.
FS_POPULATED="${TMPROOT}/freespace-populated-bin"
make_bare_fakes "$FS_POPULATED"
mkfake "$FS_POPULATED" lsblk '
case " $* " in
  *" PARTLABEL "*) printf "\nrootfs\nEFI\n"; exit 0 ;;
  *" PARTN "*) printf "\n1\n2\n"; exit 0 ;;
esac
exit 1'
mkfake "$FS_POPULATED" blkid '
for a in "$@"; do
  case "$a" in /dev/fixture1) printf "ext4\n"; exit 0 ;; esac
done
exit 2'

run_layout "$FS_POPULATED" --dry-run "$p"
if [ "$REPLY_RC" -ne 0 ] \
   && printf '%s' "$REPLY_OUT" | grep -qF 'PRESERVED_PARTITIONS' \
   && printf '%s' "$REPLY_OUT" | grep -qF '/dev/fixture1' \
   && ! printf '%s' "$REPLY_OUT" | grep -qF 'Re-run with --i-consent-to-destroy'; then
  ok "F6a a preserved partition that CARRIES a filesystem refuses as preserved, never as a consent prompt"
else
  no "F6a a preserved partition that CARRIES a filesystem refuses as preserved, never as a consent prompt (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

# The profile-level contradictions, each of which parsed cleanly before it was a
# refusal: a protective plan protecting nothing, and an erasing plan promising
# to keep something it erases.
p="${TMPROOT}/freespace-nothing-preserved.env"
write_profile "$p"
printf 'DISK_PLAN=free-space\n' >> "$p"
run_layout "$BARE" --dry-run "$p"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF 'must name the partitions it preserves in PRESERVED_PARTITIONS'; then
  ok "F7  free-space with nothing preserved is refused"
else
  no "F7  free-space with nothing preserved is refused (rc=${REPLY_RC})"
fi

p="${TMPROOT}/whole-device-preserving.env"
write_profile "$p"
printf 'PRESERVED_PARTITIONS=/dev/fixture1\n' >> "$p"
run_layout "$BARE" --dry-run "$p"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF 'cannot preserve'; then
  ok "F8  whole-device naming a preserved partition is refused rather than silently erasing it"
else
  no "F8  whole-device naming a preserved partition is refused rather than silently erasing it (rc=${REPLY_RC})"
fi

p="${TMPROOT}/bad-disk-plan.env"
write_profile "$p"
printf 'DISK_PLAN=partial\n' >> "$p"
run_layout "$BARE" --dry-run "$p"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF "DISK_PLAN must be 'whole-device' or 'free-space', got 'partial'"; then
  ok "F9  an unknown DISK_PLAN is refused, naming what was given"
else
  no "F9  an unknown DISK_PLAN is refused, naming what was given (rc=${REPLY_RC})"
fi

# An agent has nothing to join without both halves, and a missing one of them
# fails at the node — after the storage and the base OS are already written.
p="${TMPROOT}/agent-no-join.env"
write_profile "$p"
sed 's|^CLUSTER_ROLE=.*|CLUSTER_ROLE=agent|' "$p" > "${p}.tmp" && mv "${p}.tmp" "$p"
run_layout "$BARE" --dry-run "$p"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF 'CLUSTER_ROLE=agent must name both CLUSTER_JOIN_ADDRESS and CLUSTER_TOKEN_FILE'; then
  ok "F10 an agent with no join address and no token file is refused"
else
  no "F10 an agent with no join address and no token file is refused (rc=${REPLY_RC})"
fi

p="${TMPROOT}/agent-half.env"
write_profile "$p"
sed -e 's|^CLUSTER_ROLE=.*|CLUSTER_ROLE=agent|' \
    -e 's|^CLUSTER_JOIN_ADDRESS=.*|CLUSTER_JOIN_ADDRESS=https://fixture.invalid:6443|' "$p" > "${p}.tmp" && mv "${p}.tmp" "$p"
run_layout "$BARE" --dry-run "$p"
if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF 'CLUSTER_ROLE=agent must name both'; then
  ok "F11 an agent with a join address but no token file is refused too"
else
  no "F11 an agent with a join address but no token file is refused too (rc=${REPLY_RC})"
fi

printf 'CLUSTER_TOKEN_FILE=/var/lib/fixture/join-token\nNODE_TAINTS=pool=ci:NoSchedule\n' >> "$p"
run_layout "$BARE" --dry-run "$p"
if [ "$REPLY_RC" -eq 0 ]; then
  ok "F12 an agent naming both, with taints, is accepted"
else
  no "F12 an agent naming both, with taints, is accepted (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

# The regression the whole of F is written against. `free-space` reshaped the
# partition stage, the controller stage and the mkfs stage; the first node takes
# none of those branches, and §B would not notice a step quietly added, dropped
# or reworded between the rungs it asserts. This is the full sequence, as an
# equality, against a file committed from the run BEFORE this change existed.
POWEREDGE_PLANNED="$(printf '%s\n' "$POWEREDGE_OUT" | sed -n 's/^+ //p')"
POWEREDGE_EXPECTED="$(grep -v '^#' "$POWEREDGE_PLAN" | grep . || true)"
if [ "$POWEREDGE_PLANNED" = "$POWEREDGE_EXPECTED" ]; then
  ok "F13 the poweredge whole-device plan is byte-identical to its committed expected plan"
else
  no "F13 the poweredge whole-device plan differs from its committed expected plan:"
  printf '%s\n' "$POWEREDGE_EXPECTED" > "${TMPROOT}/expected-plan"
  printf '%s\n' "$POWEREDGE_PLANNED" > "${TMPROOT}/planned"
  diff -u --label 'expected plan' --label 'planned' \
    "${TMPROOT}/expected-plan" "${TMPROOT}/planned" | sed 's/^/        /'
fi

# ---------------------------------------------------------------------------
echo
echo "== G. The COMMITTED second node's profile: gmktec-xubuntu =="
# ---------------------------------------------------------------------------
# Section F proved the free-space PLAN against a fixture. This one proves the
# node: `profiles/gmktec-xubuntu.env` is the second pool node as DATA for the
# one procedure, and the whole point of it is that it needs no new code. So
# everything below drives the SAME script through the SAME `--dry-run` and
# asserts the plan the second node's committed profile actually yields — which
# is the only thing that can catch a profile that is well formed, parses, and
# describes the wrong machine.
#
# Two claims are separated on purpose:
#   * what the profile DECLARES, read back through the parser every stage
#     sources (G1), so a value silently edited out is caught even if no
#     planned command happens to name it; and
#   * what the plan the script DERIVES from it looks like (G2 onward).

GMKTEC="${HERE}/profiles/gmktec-xubuntu.env"

# The measured device: two partitions the node already boots from, carrying no
# GPT partition NAMES (a plain installer leaves them unnamed), and nothing
# labelled `lvm` yet. `lsblk` answers both the label probe and the
# partition-number probe, so the script derives "the next free number is 3" from
# the table rather than from an assumption.
GMKTEC_BIN="${TMPROOT}/gmktec-bin"
make_bare_fakes "$GMKTEC_BIN"
mkfake "$GMKTEC_BIN" lsblk '
case " $* " in
  *" PARTLABEL "*) printf "\n\n\n"; exit 0 ;;
  *" PARTN "*) printf "\n1\n2\n"; exit 0 ;;
esac
exit 1'

# G1 reads the committed profile back through the SAME parser the stages source,
# so what is asserted is what storage-layout.sh would act on — not a second,
# independent reading of the same file. Each `want` is one of the node facts
# measured on 2026-09-06; a profile that drops or mutates one fails here even if
# no planned command would have named it.
gmktec_declared() {  # gmktec_declared -> `KEY value` lines for the keys G1 checks
  (
    die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
    # shellcheck source=ci-runner/k3s/phase0-bare-metal/profile.sh
    source "${HERE}/profile.sh"
    profile_load "$GMKTEC"
    local key record
    # NODE_TAINTS is checked separately below (G1b): R5 emptied it, and an empty
    # value would need a trailing-space heredoc line to match here, so it is
    # asserted as an emptiness rather than through this `KEY value` list.
    for key in CONTROLLER_KIND DISK_PLAN TARGET_DEVICE PRESERVED_PARTITIONS \
               ESP_DEVICE ESP_FSTYPE VOLUME_GROUPS NODE_NETWORK_INTERFACE \
               NODE_ADDRESS CLUSTER_ROLE \
               CLUSTER_JOIN_ADDRESS CLUSTER_TOKEN_FILE \
               BOOT_ENTRY_LABEL OPERATOR_ACCOUNT \
               ADMISSION_CAPACITY_C; do
      printf '%s %s\n' "$key" "${CFG[$key]}"
    done
    for record in "${TIER_RECORDS[@]}"; do printf 'tier %s\n' "${record//:/ }"; done
  )
}

GMKTEC_DECLARED="$(gmktec_declared)"
missing=""
while IFS= read -r want; do
  printf '%s\n' "$GMKTEC_DECLARED" | grep -qxF "$want" || missing="${missing}
        ${want}"
done <<'EOF'
CONTROLLER_KIND none
DISK_PLAN free-space
TARGET_DEVICE /dev/nvme0n1
PRESERVED_PARTITIONS /dev/nvme0n1p1 /dev/nvme0n1p2
ESP_DEVICE /dev/nvme0n1p2
ESP_FSTYPE vfat
VOLUME_GROUPS nvmea:/dev/nvme0n1p3
NODE_NETWORK_INTERFACE eno1
NODE_ADDRESS 192.168.1.156/24
CLUSTER_ROLE agent
CLUSTER_JOIN_ADDRESS https://192.168.1.200:6443
CLUSTER_TOKEN_FILE /etc/rancher/k3s/agent-join-token
BOOT_ENTRY_LABEL Ubuntu
OPERATOR_ACCOUNT cwoolley
ADMISSION_CAPACITY_C 12
tier ci-cache nvmea
tier ci-containerd nvmea
tier ci-workvols nvmea
EOF
if [ -z "$missing" ]; then
  ok "G1  the committed profile declares the second node's measured facts"
else
  no "G1  the committed profile no longer declares:${missing}"
fi

# G1b: R5 (livespec-dev-tooling-xa6o) opened this node for general CI churn, so
# its NODE_TAINTS is now EMPTY — the `node-role/ci=pending:NoSchedule` that kept
# it closed is gone, in lockstep with ADMISSION_CAPACITY_C rising 0 -> 12 above.
# Read back through the SAME parser, and asserted as an emptiness rather than a
# `KEY value` line so no trailing-whitespace heredoc is needed.
gmktec_taints() {  # gmktec_taints -> the committed profile's NODE_TAINTS value
  (
    die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
    # shellcheck source=ci-runner/k3s/phase0-bare-metal/profile.sh
    source "${HERE}/profile.sh"
    profile_load "$GMKTEC"
    printf '%s' "${CFG[NODE_TAINTS]}"
  )
}
if [ -z "$(gmktec_taints)" ]; then
  ok "G1b the opened profile declares an empty NODE_TAINTS"
else
  no "G1b the opened profile declares an empty NODE_TAINTS (got: $(gmktec_taints))"
fi

run_layout "$GMKTEC_BIN" --dry-run "$GMKTEC"
GM_OUT="$REPLY_OUT"
GM_RC="$REPLY_RC"
gm_new_partitions="$(printf '%s\n' "$GM_OUT" | grep -c '^+ sgdisk --new' || true)"

if [ "$GM_RC" -eq 0 ]; then
  ok "G2  --dry-run against the committed gmktec profile exits 0"
else
  no "G2  --dry-run against the committed gmktec profile exits 0 (rc=${GM_RC})"
  printf '%s\n' "$GM_OUT"
fi

# The node has no controller and keeps its operating system, so the two
# destructive halves of the whole-device plan must be absent from the plan
# ENTIRELY — not merely refused later.
if ! printf '%s\n' "$GM_OUT" | grep -q '^+ .*add vd' \
   && ! printf '%s\n' "$GM_OUT" | grep -q '^+ .*--zap-all' \
   && ! printf '%s\n' "$GM_OUT" | grep -q '^+ wipefs' \
   && ! printf '%s\n' "$GM_OUT" | grep -q '^+ mkfs.vfat'; then
  ok "G3  no controller command, no zap, no wipefs, and no mkfs over the ESP it boots from"
else
  no "G3  no controller command, no zap, no wipefs, and no mkfs over the ESP it boots from"
  printf '%s\n' "$GM_OUT"
fi

# EXACTLY ONE new partition, and at number 3 — read off the device's own table
# (1 and 2 taken), which is the number `VOLUME_GROUPS` spells out as a path.
# Those two agreeing is the one thing the profile cannot state and the plan
# cannot check for itself, so it is asserted here.
if [ "$gm_new_partitions" -eq 1 ] \
   && printf '%s\n' "$GM_OUT" | grep -qxF '+ sgdisk --new=3:0:0 --typecode=3:8e00 --change-name=3:lvm /dev/nvme0n1'; then
  ok "G4  exactly one new partition, numbered 3 off the device's own table, typed LVM"
else
  no "G4  exactly one new partition, numbered 3 off the device's own table (${gm_new_partitions} new-partition command(s))"
  printf '%s\n' "$GM_OUT"
fi

# The tail partition becomes the physical volume, the one volume group, the
# three tier volumes and the three labelled filesystems — in that order, with
# the sizes and types the profile declares. `ci-workvols` is XFS with reflink,
# which is what lets the warm-cache seed give every job its own inodes.
if order_ok "$GM_OUT" \
    'pvcreate --yes /dev/nvme0n1p3' \
    'vgcreate nvmea /dev/nvme0n1p3' \
    'lvcreate --yes -L 350G -n ci-cache nvmea' \
    'lvcreate --yes -L 525G -n ci-containerd nvmea' \
    'lvcreate --yes -L 525G -n ci-workvols nvmea' \
    'mkfs.ext4 -q -L ci-cache /dev/nvmea/ci-cache' \
    'mkfs.ext4 -q -L ci-containerd /dev/nvmea/ci-containerd' \
    'mkfs.xfs -q -m reflink=1 -L ci-workvols /dev/nvmea/ci-workvols'; then
  ok "G5  physical volume, volume group, the three tier volumes and the three labelled filesystems — in that order"
else
  no "G5  physical volume, volume group, the three tier volumes and the three labelled filesystems — in that order"
  printf '%s\n' "$GM_OUT"
fi

# The refusal the whole free-space plan rests on, driven against THIS node's
# real partition paths rather than a fixture's. Each case repoints the physical
# volume at a preserved partition — a step that WOULD otherwise have run, since
# `pvcreate` on an empty-looking device needs no consent at all — and the
# refusal must name that exact partition and the key that protects it.
for preserved in /dev/nvme0n1p1 /dev/nvme0n1p2; do
  p="${TMPROOT}/gmktec-clobber$(basename "$preserved").env"
  sed "s|^VOLUME_GROUPS=.*|VOLUME_GROUPS=nvmea:${preserved}|" "$GMKTEC" > "$p"
  run_layout "$GMKTEC_BIN" --dry-run "$p"
  if [ "$REPLY_RC" -ne 0 ] \
     && printf '%s' "$REPLY_OUT" | grep -qF 'REFUSED' \
     && printf '%s' "$REPLY_OUT" | grep -qF "$preserved" \
     && printf '%s' "$REPLY_OUT" | grep -qF 'PRESERVED_PARTITIONS'; then
    ok "G6  a step naming ${preserved} is refused, naming it and PRESERVED_PARTITIONS"
  else
    no "G6  a step naming ${preserved} is refused, naming it and PRESERVED_PARTITIONS (rc=${REPLY_RC})"
    printf '%s\n' "$REPLY_OUT"
  fi

  # And consent does not unlock it: preservation is a different key, not a
  # stronger flavour of consent.
  run_layout "$GMKTEC_BIN" --dry-run "--i-consent-to-destroy=${preserved}" "$p"
  if [ "$REPLY_RC" -ne 0 ] && printf '%s' "$REPLY_OUT" | grep -qF 'REFUSED'; then
    ok "G7  --i-consent-to-destroy=${preserved} does not unlock it either"
  else
    no "G7  --i-consent-to-destroy=${preserved} does not unlock it either (rc=${REPLY_RC})"
  fi
done

# G1 through G7 ask whether the profile is WELL FORMED and whether the plan it
# yields is right. The rest of this section asks whether the profile is TRUE —
# the question that went unasked on the first node until a 64 GiB swap and a
# missing volume group turned up in it, and the question this node needs asked
# more sharply still: four of its values were placeholders copied from the FIRST
# node's profile, and the 2026-09-06 read found all four wrong. Nothing but a
# record and a comparison notices that a plausible label is a fiction.

GMKTEC_FACTS="${HERE}/profiles/gmktec-xubuntu.recorded-facts"
GMKTEC_PLAN="${HERE}/profiles/gmktec-xubuntu.expected-plan"

# Read back through the SAME parser the stages source, so what is compared is
# what storage-layout.sh would act on. An EMPTY value prints as the key alone,
# which is how the record spells "carries no label" — the two sides agree on
# that spelling rather than one of them encoding it specially.
gmktec_key_values() {  # gmktec_key_values KEY... -> `key <KEY> [<value>]` lines
  (
    die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
    # shellcheck source=ci-runner/k3s/phase0-bare-metal/profile.sh
    source "${HERE}/profile.sh"
    profile_load "$GMKTEC"
    local key
    for key in "$@"; do
      if [ -z "${CFG[$key]}" ]; then
        printf 'key %s\n' "$key"
      else
        printf 'key %s %s\n' "$key" "${CFG[$key]}"
      fi
    done
  )
}

if [ -f "$GMKTEC_FACTS" ] && [ -f "$GMKTEC_PLAN" ]; then
  ok "G8  the recorded-facts table and the expected plan are committed beside the profile"
else
  no "G8  the recorded-facts table and the expected plan are committed beside the profile (missing one of ${GMKTEC_FACTS}, ${GMKTEC_PLAN})"
fi

# An equality in both directions, exactly as §E2 is for the first node: a
# recorded volume, group or tier the profile omits fails it, and one the profile
# invents fails it too.
declared="$(profile_facts "$GMKTEC" | LC_ALL=C sort)"
recorded="$(recorded_facts "$GMKTEC_FACTS" | grep -E '^(vg|lv|tier) ' | LC_ALL=C sort)"
if [ "$declared" = "$recorded" ]; then
  ok "G9  every volume group, logical volume size and tier placement matches the record"
else
  no "G9  the profile and the recorded facts disagree:"
  printf '%s\n' "$recorded" > "${TMPROOT}/gmktec-recorded"
  printf '%s\n' "$declared" > "${TMPROOT}/gmktec-declared"
  diff -u --label 'recorded facts' --label 'profile' \
    "${TMPROOT}/gmktec-recorded" "${TMPROOT}/gmktec-declared" | sed 's/^/        /'
fi

# The four values the 2026-09-06 read resolved, compared as VALUES rather than
# as the presence of a line: two of them are EMPTY, and an assertion that cannot
# tell "empty" from "absent" is exactly the assertion this node does not need.
recorded_keys="$(recorded_facts "$GMKTEC_FACTS" | grep '^key ' || true)"
mapfile -t gmktec_key_names < <(printf '%s\n' "$recorded_keys" | awk 'NF {print $2}')
if [ "${#gmktec_key_names[@]}" -gt 0 ]; then
  declared_keys="$(gmktec_key_values "${gmktec_key_names[@]}")"
else
  declared_keys=""
fi
if [ -n "$recorded_keys" ] && [ "$declared_keys" = "$recorded_keys" ]; then
  ok "G10 every base-OS key the record resolves carries the recorded value, empty ones included"
else
  no "G10 the profile's base-OS keys and the recorded values disagree:"
  printf '%s\n' "$recorded_keys" > "${TMPROOT}/gmktec-recorded-keys"
  printf '%s\n' "$declared_keys" > "${TMPROOT}/gmktec-declared-keys"
  diff -u --label 'recorded facts' --label 'profile' \
    "${TMPROOT}/gmktec-recorded-keys" "${TMPROOT}/gmktec-declared-keys" | sed 's/^/        /'
fi

# G10 is an equality, so it is equally satisfied by editing the RECORD back to a
# drifted profile's values — which would be exactly backwards. The four the read
# corrected are therefore also asserted literally, so moving one takes an edit in
# two places and the second is a file whose header says it changes only by
# re-reading the host.
missing=""
while IFS= read -r want; do
  printf '%s\n' "$recorded_keys" | grep -qxF "$want" || missing="${missing}
        ${want}"
done <<'EOF'
key ESP_LABEL
key ROOT_LABEL
key BOOT_ENTRY_LABEL Ubuntu
key OPERATOR_ACCOUNT cwoolley
EOF
if [ -z "$missing" ]; then
  ok "G11 the record still carries the four values the 2026-09-06 read corrected"
else
  no "G11 the record no longer carries:${missing}"
fi

# And the marker those four values used to carry is GONE — every value in this
# profile is now measured. It is asserted rather than merely done, because the
# marker is what a reader greps for to learn which of a profile's values are
# guesses: one re-added here without a read behind it would put this node back
# to the state that produced four wrong values, and the record above cannot
# catch that on its own (a `# UNVERIFIED` line beside a value the record also
# carries passes G10 unremarked). The FIRST node's profile still carries its
# own; resolving those needs a rehearsal of THAT node and is not this file's.
unverified="$(grep -cE '^# UNVERIFIED' "$GMKTEC" || true)"
if [ "$unverified" -eq 0 ]; then
  ok "G12 no line of the committed gmktec profile is marked UNVERIFIED"
else
  no "G12 the committed gmktec profile marks ${unverified} line(s) UNVERIFIED:"
  grep -nE '^# UNVERIFIED' "$GMKTEC" | sed 's/^/        /'
fi

# The partitions the node already carries are the record's, and they are what
# makes "3" a DERIVED number rather than an assumed one: the record says 1 and 2
# are taken, so the plan's new partition must be the next after the highest of
# them, and `VOLUME_GROUPS` must spell out that same number as a path.
recorded_parts="$(recorded_facts "$GMKTEC_FACTS" | grep '^part ' || true)"
recorded_part_devices="$(printf '%s\n' "$recorded_parts" | awk 'NF {print $2}' | LC_ALL=C sort | paste -sd' ' -)"
declared_preserved="$(printf '%s\n' "$GMKTEC_DECLARED" | sed -n 's/^PRESERVED_PARTITIONS //p' \
  | tr ' ' '\n' | grep . | LC_ALL=C sort | paste -sd' ' -)"
recorded_esp="$(printf '%s\n' "$recorded_parts" | awk '$5 == "/boot/efi" {print $2, $3}')"
declared_esp="$(printf '%s\n' "$GMKTEC_DECLARED" | sed -n 's/^ESP_DEVICE //p') $(printf '%s\n' "$GMKTEC_DECLARED" | sed -n 's/^ESP_FSTYPE //p')"
highest_recorded_part="$(printf '%s\n' "$recorded_parts" | awk 'NF {print $2}' \
  | sed 's/.*[^0-9]\([0-9][0-9]*\)$/\1/' | LC_ALL=C sort -n | tail -1)"
next_free_part=$((highest_recorded_part + 1))
if [ "$recorded_part_devices" = "$declared_preserved" ] \
   && [ "$recorded_esp" = "$declared_esp" ] \
   && printf '%s\n' "$GM_OUT" | grep -qF "sgdisk --new=${next_free_part}:0:0" \
   && printf '%s\n' "$GMKTEC_DECLARED" | grep -qxF "VOLUME_GROUPS nvmea:/dev/nvme0n1p${next_free_part}"; then
  ok "G13 the record's two preserved partitions are the profile's, and the plan takes the next number after them (${next_free_part})"
else
  no "G13 the record's preserved partitions, the ESP or the derived partition number disagree with the profile"
  printf '        recorded partitions: %s\n' "$recorded_part_devices"
  printf '        profile preserves:   %s\n' "$declared_preserved"
  printf '        recorded ESP:        %s\n' "$recorded_esp"
  printf '        profile ESP:         %s\n' "$declared_esp"
  printf '        next free number:    %s\n' "$next_free_part"
fi

# The whole plan, as an equality, against a capture taken from the run BEFORE
# the four base-OS values were resolved. Two of them became EMPTY, and stage 1
# must not notice: under `free-space` it never `mkfs`es the EFI system partition,
# so ESP_LABEL is a value it describes and never writes. G4 and G5 assert a
# number and an ORDERED SUBSET, so a step silently added, dropped or reworded
# between two asserted rungs passes them and fails this.
GMKTEC_PLANNED="$(printf '%s\n' "$GM_OUT" | sed -n 's/^+ //p')"
GMKTEC_EXPECTED="$(grep -v '^#' "$GMKTEC_PLAN" | grep . || true)"
if [ "$GMKTEC_PLANNED" = "$GMKTEC_EXPECTED" ]; then
  ok "G14 the gmktec free-space plan is byte-identical to its committed expected plan"
else
  no "G14 the gmktec free-space plan differs from its committed expected plan:"
  printf '%s\n' "$GMKTEC_EXPECTED" > "${TMPROOT}/gmktec-expected-plan"
  printf '%s\n' "$GMKTEC_PLANNED" > "${TMPROOT}/gmktec-planned"
  diff -u --label 'expected plan' --label 'planned' \
    "${TMPROOT}/gmktec-expected-plan" "${TMPROOT}/gmktec-planned" | sed 's/^/        /'
fi

# ---------------------------------------------------------------------------
echo
echo "== H. The tool preflight: never start a layout this node cannot finish =="
# ---------------------------------------------------------------------------
# Every case above runs on a PATH where every tool the plan reaches for is
# present, which is the one state a real node is not guaranteed to be in.
# Measured on gmktec-xubuntu 2026-09-07, before its rehearsal: the node has
# `sgdisk`, `partprobe` and `mkfs.ext4` and has NEITHER lvm2 NOR xfsprogs. A
# live `free-space` run there would have cut partition 3, re-read the table and
# then died at `pvcreate: command not found`, leaving a partition with nothing
# on it — and a re-run would compute its "largest free region" against a device
# that had changed under it.
#
# THESE CASES REPLACE THE PATH RATHER THAN PREPENDING TO IT, which is the one
# way this section differs from every other. Prepending a scratch directory can
# make a tool ANSWER differently; it cannot make one ABSENT, because the host's
# own `/usr/sbin/pvcreate` is simply one directory further along. So each
# fixture below is a SELF-CONTAINED PATH: the fake tools plus symlinks to the
# handful of real utilities the script calls, minus the tools the case is about.
#
# `apt-get` is faked as a tripwire in every one of them, so a preflight bug that
# reached an install lands in the tripwire file rather than in the packages of
# the machine running this suite.

# The gmktec node as measured: two partitions taken, no `lvm` label — and now
# also without `pvcreate` (lvm2) or `mkfs.xfs` (xfsprogs).
GM_NO_TOOLS="${TMPROOT}/gmktec-no-tools-bin"
make_selfcontained_path "$GM_NO_TOOLS" pvcreate mkfs.xfs
mkfake "$GM_NO_TOOLS" lsblk '
case " $* " in
  *" PARTLABEL "*) printf "\n\n\n"; exit 0 ;;
  *" PARTN "*) printf "\n1\n2\n"; exit 0 ;;
esac
exit 1'

run_layout_only "$GM_NO_TOOLS" --dry-run "$GMKTEC"
PF_FS_OUT="$REPLY_OUT"
PF_FS_RC="$REPLY_RC"
pf_apt_lines="$(printf '%s\n' "$PF_FS_OUT" | grep -c '^+ apt-get ' || true)"
pf_apt_idx="$(printf '%s\n' "$PF_FS_OUT" | grep -n '^+ apt-get ' | head -1 | cut -d: -f1)"
pf_sgdisk_idx="$(printf '%s\n' "$PF_FS_OUT" | grep -n '^+ sgdisk ' | head -1 | cut -d: -f1)"

# ONE apt-get line, naming both packages and only the packages actually missing:
# `vgcreate` and `lvcreate` are also lvm2's, so a per-tool install would ask for
# lvm2 three times and read as three separate problems.
if [ "$PF_FS_RC" -eq 0 ] \
   && [ "$pf_apt_lines" -eq 1 ] \
   && printf '%s\n' "$PF_FS_OUT" | grep -qxF '+ apt-get install -y --no-install-recommends lvm2 xfsprogs'; then
  ok "H1  free-space with lvm2 and xfsprogs absent plans exactly one apt-get, naming both packages"
else
  no "H1  free-space with lvm2 and xfsprogs absent plans exactly one apt-get, naming both packages (rc=${PF_FS_RC}, ${pf_apt_lines} apt-get line(s))"
  printf '%s\n' "$PF_FS_OUT"
fi

# BEFORE the first partition command, which is the whole property: an install
# after the sgdisk is an install that runs on a disk already cut.
if [ -n "$pf_apt_idx" ] && [ -n "$pf_sgdisk_idx" ] && [ "$pf_apt_idx" -lt "$pf_sgdisk_idx" ]; then
  ok "H2  the apt-get line comes before the first sgdisk line"
else
  no "H2  the apt-get line does not precede the first sgdisk line (apt-get at ${pf_apt_idx:-none}, sgdisk at ${pf_sgdisk_idx:-none})"
  printf '%s\n' "$PF_FS_OUT"
fi

# The rest of the plan is UNCHANGED — the committed expected plan with exactly
# that one line in front of it. This is an equality, so it also proves the two
# things a per-line assertion cannot: that the preflight added nothing else and
# dropped nothing, and that the self-contained PATH above is COMPLETE (a missing
# utility would have derived a different plan, not an error).
PF_FS_PLANNED="$(printf '%s\n' "$PF_FS_OUT" | sed -n 's/^+ //p')"
PF_FS_EXPECTED="apt-get install -y --no-install-recommends lvm2 xfsprogs
${GMKTEC_EXPECTED}"
if [ "$PF_FS_PLANNED" = "$PF_FS_EXPECTED" ]; then
  ok "H3  the rest of the free-space plan is the committed expected plan, unchanged"
else
  no "H3  the free-space plan is not the committed expected plan plus the install:"
  printf '%s\n' "$PF_FS_EXPECTED" > "${TMPROOT}/pf-expected"
  printf '%s\n' "$PF_FS_PLANNED" > "${TMPROOT}/pf-planned"
  diff -u --label 'expected plan' --label 'planned' \
    "${TMPROOT}/pf-expected" "${TMPROOT}/pf-planned" | sed 's/^/        /'
fi

# The whole-device answer to the same absence. That plan runs from the Recovery
# USB, which is BUILT to carry these tools, so installing them would paper over
# a defect in the USB; the run refuses instead. Under --dry-run the refusal is
# PRINTED rather than taken, so a workstation still sees the whole plan — which
# is the half a bare `die` would have cost.
PE_NO_TOOLS="${TMPROOT}/poweredge-no-tools-bin"
make_selfcontained_path "$PE_NO_TOOLS" pvcreate mkfs.xfs

run_layout_only "$PE_NO_TOOLS" --dry-run "$POWEREDGE"
PF_WD_OUT="$REPLY_OUT"
PF_WD_RC="$REPLY_RC"

if [ "$PF_WD_RC" -eq 0 ] \
   && printf '%s\n' "$PF_WD_OUT" | grep -qxF 'WOULD REFUSE: pvcreate absent (lvm2)' \
   && printf '%s\n' "$PF_WD_OUT" | grep -qxF 'WOULD REFUSE: mkfs.xfs absent (xfsprogs)' \
   && ! printf '%s\n' "$PF_WD_OUT" | grep -q '^+ apt-get'; then
  ok "H4  whole-device names each absent tool and its package as WOULD REFUSE, and installs nothing"
else
  no "H4  whole-device names each absent tool and its package as WOULD REFUSE, and installs nothing (rc=${PF_WD_RC})"
  printf '%s\n' "$PF_WD_OUT"
fi

PF_WD_PLANNED="$(printf '%s\n' "$PF_WD_OUT" | sed -n 's/^+ //p')"
if [ "$PF_WD_PLANNED" = "$POWEREDGE_EXPECTED" ]; then
  ok "H5  and still prints the full command sequence, byte-identical to the committed expected plan"
else
  no "H5  the whole-device plan is no longer printed in full:"
  printf '%s\n' "$POWEREDGE_EXPECTED" > "${TMPROOT}/pf-wd-expected"
  printf '%s\n' "$PF_WD_PLANNED" > "${TMPROOT}/pf-wd-planned"
  diff -u --label 'expected plan' --label 'planned' \
    "${TMPROOT}/pf-wd-expected" "${TMPROOT}/pf-wd-planned" | sed 's/^/        /'
fi

# The control, and the reason the two assertions above mean anything: on a node
# that HAS every tool the preflight is silent in both plans. `POWEREDGE_OUT` and
# `GM_OUT` are the §B and §G runs, whose fake PATHs carry all of them.
if ! printf '%s\n' "$POWEREDGE_OUT" | grep -q 'apt-get\|WOULD REFUSE' \
   && ! printf '%s\n' "$GM_OUT" | grep -q 'apt-get\|WOULD REFUSE'; then
  ok "H6  with every tool present, neither profile's plan carries an apt-get or a WOULD REFUSE line"
else
  no "H6  a plan carries an apt-get or WOULD REFUSE line with every tool present"
  printf '%s\n' "$POWEREDGE_OUT" "$GM_OUT" | grep -n 'apt-get\|WOULD REFUSE'
fi

# The LIVE refusal — the case the other three only describe. It is the one run
# in this suite that is not a dry run, so it is fenced twice: `id` is faked to
# report root (otherwise the run stops at the privilege check, one step BEFORE
# the preflight, and would pass this vacuously), and it gets its own tripwire
# file so §I1 still means what it says. Every mutating command on this PATH is a
# tripwire, so "exited before executing any sgdisk" is asserted against the
# tripwire rather than inferred from the exit code.
PE_LIVE="${TMPROOT}/poweredge-live-bin"
make_selfcontained_path "$PE_LIVE" pvcreate mkfs.xfs
mkfake "$PE_LIVE" id 'echo 0'
LIVE_TRIPWIRE="${TMPROOT}/live-tripwire"
: > "$LIVE_TRIPWIRE"
REPLY_OUT="$(TRIPWIRE="$LIVE_TRIPWIRE" PATH="$PE_LIVE" "$SCRIPT" "$POWEREDGE" 2>&1)"
REPLY_RC=$?

if [ "$REPLY_RC" -ne 0 ] \
   && printf '%s\n' "$REPLY_OUT" | grep -qF 'REFUSED' \
   && printf '%s\n' "$REPLY_OUT" | grep -qF 'pvcreate' \
   && printf '%s\n' "$REPLY_OUT" | grep -qF 'lvm2' \
   && ! printf '%s\n' "$REPLY_OUT" | grep -q '^+ ' \
   && [ ! -s "$LIVE_TRIPWIRE" ]; then
  ok "H7  a LIVE whole-device run with an absent tool exits non-zero having executed nothing"
else
  no "H7  a LIVE whole-device run with an absent tool exits non-zero having executed nothing (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
  cat "$LIVE_TRIPWIRE"
fi

# ---------------------------------------------------------------------------
echo
echo "== I. Still nothing ran =="
# ---------------------------------------------------------------------------
# D1 asserted this before section F existed; F, G and H drive several more dry
# runs, including three that plan a partition and two that plan a package
# install, so the tripwire is read again after them.
if [ ! -s "$TRIPWIRE" ]; then
  ok "I1  no mutating command ran in any dry run, sections F, G and H included"
else
  no "I1  a dry run EXECUTED a mutating command:"
  cat "$TRIPWIRE"
fi

echo
printf 'phase0 storage-layout: %d pass / %d fail\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
