#!/usr/bin/env bash
# install-storage-layout-exit-tests.sh — prove that ./install-storage-layout.sh
# BOOTSTRAPS a node rather than half-applying itself to one, WITHOUT touching
# any host:
#
#   A. FRESH HOST (labels resolve, nothing mounted): the plan mounts the cache
#      tier and creates the two tier mountpoints ON it BEFORE the first fstab
#      line and BEFORE findmnt --verify — the ordering whose absence wrote five
#      fstab lines with nothing mounted and exited 1 on gmktec-xubuntu
#      2026-09-07;
#   B. FOREIGN AUTOMOUNT: a tier volume that udisks parked under /run/media is
#      unmounted before the cache tier is mounted where it belongs;
#   C. RUNNING k3s: with `k3s-agent.service` active and content in the
#      containerd store, the plan stops the unit, rsyncs the store onto the
#      tier, mounts the binds and starts the unit again, in that order — a bind
#      laid over a live store would hide it;
#   D. LIVE TIERS: on a host where all five managed mountpoints are already
#      mounted the installer plans NO mutating command at all and exits 0. That
#      no-op is its stated contract and what lets migrate-tier.sh end every
#      procedure by running it;
#   E. EXECUTED, then RE-EXECUTED: a real run against a scratch host mounts
#      everything and writes the five lines, and a second run over the state the
#      first left is a byte-exact no-op;
#   F. HALF-APPLIED (the state gmktec-xubuntu was left in: the five lines in
#      fstab, nothing mounted): a real run mounts everything and neither
#      duplicates nor rewrites one byte of fstab;
#   G. the label probe's refusals, and an unknown argument, are each refused by
#      name.
#
# HOW IT STAYS OFF THE HOST. Every path the script touches is resolved under
# STORAGE_LAYOUT_ROOT, which every case points at a scratch directory, so even
# the cases that run for real (E, F) write only inside this suite's own
# mktemp -d. On top of that each case runs against a scratch PATH of FAKE
# tools: `lsblk`/`blkid` answer from a labels file this suite writes,
# `findmnt`/`mount`/`umount` from a mounts file it keeps, `systemctl` from an
# active-unit file — and every mutating tool records into a tripwire file that
# cases A-D assert is empty. The suite never runs as root: the two executing
# cases put a fake `id` on PATH ahead of the host's, and everything they do
# would work unprivileged anyway.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/install-storage-layout.sh"
DROPIN_SRC="${HERE}/10-requires-storage-mounts.conf"

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

# The scratch host. Every one of these mirrors a constant in the script under
# test, resolved under the same STORAGE_LAYOUT_ROOT it is handed.
ROOT="${TMPROOT}/root"
CACHE="${ROOT}/var/cache/ci-runner"
CSRC="${CACHE}/k3s-containerd"
SSRC="${CACHE}/k3s-storage"
CDIR="${ROOT}/var/lib/rancher/k3s/agent/containerd"
SDIR="${ROOT}/var/lib/rancher/k3s/storage"
FSTAB="${ROOT}/etc/fstab"
DROPIN_DST="${ROOT}/etc/systemd/system/k3s.service.d/10-requires-storage-mounts.conf"

# The fakes' own state, outside ROOT so that resetting the host leaves the
# suite's bookkeeping paths stable.
# The five lines the installer ensures, resolved under this suite's scratch
# root. A LITERAL, like the phase0 base-OS suite's copy of the same five: its
# whole job is to fail if the layout the installer writes ever changes silently.
FIVE_LINES=(
  "LABEL=ci-cache ${CACHE} ext4 defaults,noatime 0 2"
  "LABEL=ci-containerd ${CSRC} ext4 defaults,noatime,x-systemd.requires-mounts-for=${CACHE} 0 2"
  "LABEL=ci-workvols ${SSRC} xfs defaults,noatime,x-systemd.requires-mounts-for=${CACHE} 0 2"
  "${CSRC} ${CDIR} none bind,x-systemd.requires-mounts-for=${CSRC} 0 0"
  "${SSRC} ${SDIR} none bind,x-systemd.requires-mounts-for=${SSRC} 0 0"
)

STATE="${TMPROOT}/state"
mkdir -p "$STATE"
MOUNTS="${STATE}/mounts"      # one "TARGET SOURCE FSTYPE" per mounted filesystem
LABELS="${STATE}/labels"      # one "LABEL DEVICE" per labelled block device
ACTIVE="${STATE}/active"      # the one systemd unit `is-active` answers yes for
TRIPWIRE="${STATE}/tripwire"  # every mutating command any fake was asked to run
export MOUNTS LABELS ACTIVE TRIPWIRE

mkfake() {  # mkfake DIR NAME BODY
  # UNLINKED FIRST, as the phase0 suite's own mkfake is and for the reason its
  # comment records: a `>` redirect onto a symlink writes THROUGH it, so
  # overwriting a fake that happened to be a link to a host utility would
  # truncate the host's copy. Nothing here makes such links today; the ordering
  # is what keeps that true if anything ever does.
  rm -f "${1}/${2}"
  printf '#!/usr/bin/env bash\n%s\n' "$3" > "${1}/${2}"
  chmod +x "${1}/${2}"
}

# ---------------------------------------------------------------------------
# The fake host tools. Each is single-quoted on purpose: the body is the FAKE's
# source, expanded when the fake runs, not when this suite writes it.
# ---------------------------------------------------------------------------
FAKEBIN="${TMPROOT}/fakebin"
mkdir -p "$FAKEBIN"

# lsblk -rno PATH,TYPE — every labelled device, plus one unlabelled partition
# so the probe is proven to skip a device blkid has no LABEL for.
mkfake "$FAKEBIN" lsblk '
awk "{print \$2\" lvm\"}" "$LABELS"
printf "/dev/nvme0n1p1 part\n"
'

# blkid -p -s LABEL -o value DEVICE — the label of the LAST argument, exit 2
# (as the real one does) when that device carries none.
mkfake "$FAKEBIN" blkid '
for a in "$@"; do dev="$a"; done
label="$(awk -v d="$dev" "\$2==d{print \$1}" "$LABELS")"
[ -n "$label" ] || exit 2
printf "%s\n" "$label"
'

# findmnt — the four forms the script uses: --verify (always clean here),
# --source DEV (every target that device carries), and --target PATH with
# either -o TARGET or -o SOURCE,FSTYPE, answered from the longest mounted
# prefix of PATH. No match exits 1 with no output, which the script reads as
# "not a mountpoint".
mkfake "$FAKEBIN" findmnt '
out=TARGET; target=""; source_dev=""; verify=0
while [ $# -gt 0 ]; do
  case "$1" in
    --verify) verify=1 ;;
    --tab-file) shift ;;
    --target) target="$2"; shift ;;
    --source) source_dev="$2"; shift ;;
    -o) out="$2"; shift ;;
  esac
  shift
done
[ "$verify" -eq 0 ] || exit 0
if [ -n "$source_dev" ]; then
  awk -v d="$source_dev" "\$2==d{print \$1}" "$MOUNTS"
  exit 0
fi
[ -n "$target" ] || exit 1
best=""; bestlen=0
while read -r t s f; do
  [ -n "$t" ] || continue
  case "$target" in "$t"|"$t"/*) ;; *) continue ;; esac
  if [ "${#t}" -ge "$bestlen" ]; then best_t="$t"; best_s="$s"; best_f="$f"; bestlen="${#t}"; best=1; fi
done < "$MOUNTS"
[ -n "$best" ] || exit 1
case "$out" in
  TARGET) printf "%s\n" "$best_t" ;;
  *) printf "%s %s\n" "$best_s" "$best_f" ;;
esac
'

# mount TARGET | mount SPEC TARGET — recorded, and the scratch host remembers
# it, so the executing cases can be asserted on the state they leave.
mkfake "$FAKEBIN" mount '
printf "mount %s\n" "$*" >> "$TRIPWIRE"
operands=()
while [ $# -gt 0 ]; do
  case "$1" in
    -o|-t) shift ;;
    -*) ;;
    *) operands+=("$1") ;;
  esac
  shift
done
if [ "${#operands[@]}" -eq 1 ]; then
  t="${operands[0]}"; s="fstab"
else
  s="${operands[0]}"; t="${operands[1]}"
fi
printf "%s %s ext4\n" "$t" "$s" >> "$MOUNTS"
'

mkfake "$FAKEBIN" umount '
printf "umount %s\n" "$*" >> "$TRIPWIRE"
grep -v "^${1} " "$MOUNTS" > "${MOUNTS}.tmp" 2>/dev/null || true
mv "${MOUNTS}.tmp" "$MOUNTS"
'

# systemctl — `is-active` is a QUESTION and is never recorded; everything else
# is a mutation and is.
mkfake "$FAKEBIN" systemctl '
if [ "${1:-}" = "is-active" ]; then
  shift
  unit=""
  for a in "$@"; do case "$a" in --*) ;; *) unit="$a" ;; esac; done
  [ "$unit" = "$(cat "$ACTIVE" 2>/dev/null || true)" ]
  exit $?
fi
printf "systemctl %s\n" "$*" >> "$TRIPWIRE"
'

mkfake "$FAKEBIN" rsync 'printf "rsync %s\n" "$*" >> "$TRIPWIRE"'

# The tripwire-only overlay the DRY-RUN cases add ahead of the fakes: under
# --dry-run the script must reach neither of these by construction, so a
# non-empty tripwire in cases A-D is the assertion that it did not.
TRIPBIN="${TMPROOT}/tripbin"
mkdir -p "$TRIPBIN"
for tool in install cp; do
  mkfake "$TRIPBIN" "$tool" 'printf "%s %s\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"'
done

# The overlay the EXECUTING cases add instead: the script's root check reads
# `id -u`, and everything it then does under STORAGE_LAYOUT_ROOT works
# unprivileged. The suite therefore never needs to be run as root.
ROOTBIN="${TMPROOT}/rootbin"
mkdir -p "$ROOTBIN"
mkfake "$ROOTBIN" id 'echo 0'

# ---------------------------------------------------------------------------
# Scratch-host construction and the two invocation forms.
# ---------------------------------------------------------------------------
reset_world() {
  rm -rf "$ROOT"
  mkdir -p "${ROOT}/etc" "${ROOT}/var/lib/rancher/k3s"
  # An unrelated fstab line, present in every case: the installer manages five
  # mountpoints and must leave everything else exactly as it found it.
  printf '%s\n' '# scratch fstab' '/dev/disk/by-uuid/dead-beef /mnt/backup ext4 nofail 0 2' > "$FSTAB"
  : > "$TRIPWIRE"
  : > "$MOUNTS"
  : > "$ACTIVE"
  printf '%s\n' \
    'ci-cache /dev/mapper/nvmea-ci--cache' \
    'ci-containerd /dev/mapper/nvmea-ci--containerd' \
    'ci-workvols /dev/mapper/nvmea-ci--workvols' > "$LABELS"
}

add_mount() {  # add_mount TARGET [SOURCE]
  printf '%s %s ext4\n' "$1" "${2:-/dev/mapper/fake}" >> "$MOUNTS"
}

write_five_lines() { printf '%s\n' "${FIVE_LINES[@]}" >> "$FSTAB"; }

run_dry() {  # run_dry [EXTRA-ARG...] -> stdout+stderr in REPLY_OUT, code in REPLY_RC
  REPLY_OUT="$(PATH="${TRIPBIN}:${FAKEBIN}:${PATH}" STORAGE_LAYOUT_ROOT="$ROOT" \
    "$SCRIPT" --dry-run "$@" 2>&1)"
  REPLY_RC=$?
}

run_live() {  # run_live -> the same, executing for real under STORAGE_LAYOUT_ROOT
  REPLY_OUT="$(PATH="${ROOTBIN}:${FAKEBIN}:${PATH}" STORAGE_LAYOUT_ROOT="$ROOT" \
    "$SCRIPT" 2>&1)"
  REPLY_RC=$?
}

# plan_lines OUTPUT -> the `+ ` lines only, which ARE every mutating step.
plan_lines() { printf '%s\n' "$1" | grep -E '^\+ ' || true; }

# same DESCRIPTION EXPECTED ACTUAL — assert two multi-line blocks are equal and
# print the difference when they are not.
same() {
  local description="$1" expected="${2%$'\n'}" actual="$3"
  if [ "$expected" = "$actual" ]; then
    ok "$description"
  else
    no "$description"
    diff <(printf '%s\n' "$expected") <(printf '%s\n' "$actual") || true
  fi
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

exits_zero() {  # exits_zero DESCRIPTION
  if [ "$REPLY_RC" -eq 0 ]; then
    ok "$1"
  else
    no "${1} (got ${REPLY_RC})"
    printf '%s\n' "$REPLY_OUT"
  fi
}

tripwire_empty() {  # tripwire_empty DESCRIPTION
  if [ -s "$TRIPWIRE" ]; then
    no "$1"
    cat "$TRIPWIRE"
  else
    ok "$1"
  fi
}

# ---------------------------------------------------------------------------
# A. Fresh host: the whole bootstrap, in order, as an EQUALITY.
#
# A literal on purpose, and not an ordered subset: a step silently added,
# dropped or reworded between two asserted rungs is exactly what an ordered
# subset passes and this fails. The order it pins is the one the installer got
# wrong — mount the cache tier and make the two tier mountpoints on it FIRST,
# fstab SECOND, mount the rest THIRD, verify LAST.
# ---------------------------------------------------------------------------
printf '== A. fresh host: mounts and mountpoints precede the fstab write and the verify ==\n'
reset_world
run_dry
exits_zero "a fresh host's --dry-run exits 0"
FRESH_OUT="$REPLY_OUT"

IFS= read -r -d '' EXPECTED_FRESH_PLAN <<EOF
+ install -d -m 0755 ${CACHE}
+ install -d -m 0755 ${CDIR}
+ install -d -m 0755 ${SDIR}
+ mount -o defaults,noatime LABEL=ci-cache ${CACHE}
+ install -d -m 0755 ${CSRC}
+ install -d -m 0755 ${SSRC}
+ fstab append ${CACHE}
+ fstab append ${CSRC}
+ fstab append ${SSRC}
+ fstab append ${CDIR}
+ fstab append ${SDIR}
+ systemctl daemon-reload
+ mount ${CSRC}
+ mount ${SSRC}
+ mount ${CDIR}
+ mount ${SDIR}
+ install -D -m 0644 ${DROPIN_SRC} ${DROPIN_DST}
+ systemctl daemon-reload
EOF

same "the fresh-host plan is the bootstrap sequence, in that order" \
  "$EXPECTED_FRESH_PLAN" "$(plan_lines "$FRESH_OUT")"

# The acceptance condition said in its own words, so it survives a future
# rewording of the sequence above.
if order_ok "$FRESH_OUT" \
  "+ mount -o defaults,noatime LABEL=ci-cache ${CACHE}" \
  "+ install -d -m 0755 ${CSRC}" \
  "+ install -d -m 0755 ${SSRC}" \
  "+ fstab append ${CACHE}" \
  "findmnt --verify"; then
  ok "the cache mount and both tier mountpoints precede the first fstab line and the verify"
else
  no "the cache mount and both tier mountpoints precede the first fstab line and the verify"
fi

# The bootstrap mount happens BEFORE the fstab line exists, so its options are
# spelled on the command line. They have to be the same options — a tier
# mounted with the kernel's relatime until the next boot is precisely the kind
# of drift nobody rechecks on the one node that was just built.
BOOTSTRAP_OPTS="$(printf '%s\n' "$FRESH_OUT" | sed -n 's/^+ mount -o \([^ ]*\) LABEL=ci-cache .*/\1/p')"
FSTAB_CACHE_OPTS="$(printf '%s\n' "${FIVE_LINES[0]}" | awk '{print $4}')"
if [ -n "$BOOTSTRAP_OPTS" ] && [ "$BOOTSTRAP_OPTS" = "$FSTAB_CACHE_OPTS" ]; then
  ok "the bootstrap cache mount carries the same options as the fstab line it precedes"
else
  no "the bootstrap cache mount options '${BOOTSTRAP_OPTS}' differ from the fstab line's '${FSTAB_CACHE_OPTS}'"
fi

if printf '%s\n' "$FRESH_OUT" | grep -qi 'BEFORE k3s'; then
  no "the fresh-host path is no longer a hand step told to run BEFORE k3s"
else
  ok "the fresh-host path is no longer a hand step told to run BEFORE k3s"
fi
tripwire_empty "the fresh-host dry run executed no host-mutating command"

# ---------------------------------------------------------------------------
# B. A tier volume udisks parked somewhere else.
# ---------------------------------------------------------------------------
printf '\n== B. a foreign automount of a tier volume is unmounted first ==\n'
reset_world
AUTOMOUNT="${ROOT}/run/media/cwoolley/ci-cache"
add_mount "$AUTOMOUNT" /dev/mapper/nvmea-ci--cache
run_dry
exits_zero "the automount case's --dry-run exits 0"
if order_ok "$REPLY_OUT" \
  "+ umount ${AUTOMOUNT}" \
  "+ mount -o defaults,noatime LABEL=ci-cache ${CACHE}"; then
  ok "the /run/media automount is unmounted before the cache tier is mounted"
else
  no "the /run/media automount is unmounted before the cache tier is mounted"
fi
if [ "$(plan_lines "$REPLY_OUT" | head -1)" = "+ umount ${AUTOMOUNT}" ]; then
  ok "the umount is the FIRST mutating step of the run"
else
  no "the umount is the FIRST mutating step of the run"
fi
tripwire_empty "the automount dry run executed no host-mutating command"

# A tier already mounted where it belongs is left alone whatever else its
# device carries: on a live node the workvols device carries one kubelet
# per-pod bind for every running runner.
reset_world
add_mount "$CACHE" /dev/mapper/nvmea-ci--cache
add_mount "$CSRC" /dev/mapper/nvmea-ci--containerd
add_mount "$SSRC" /dev/mapper/nvmea-ci--workvols
add_mount "${ROOT}/var/lib/kubelet/pods/abc/volumes/kubernetes.io~local-volume/pvc-1" /dev/mapper/nvmea-ci--workvols
run_dry
if printf '%s\n' "$REPLY_OUT" | grep -q '^+ umount '; then
  no "a kubelet per-pod bind on a live tier device is never unmounted"
  printf '%s\n' "$REPLY_OUT" | grep '^+ umount '
else
  ok "a kubelet per-pod bind on a live tier device is never unmounted"
fi

# ---------------------------------------------------------------------------
# C. k3s already running, with a store the binds would otherwise hide.
# ---------------------------------------------------------------------------
printf '\n== C. a running k3s: stop, copy onto the tier, bind, start ==\n'
reset_world
printf 'k3s-agent.service\n' > "$ACTIVE"
add_mount "$CACHE" /dev/mapper/nvmea-ci--cache
mkdir -p "$CDIR/io.containerd.content.v1.content"
printf 'layers\n' > "$CDIR/io.containerd.content.v1.content/blob"
write_five_lines
run_dry
exits_zero "the running-k3s case's --dry-run exits 0"
if order_ok "$REPLY_OUT" \
  "+ systemctl stop k3s-agent.service" \
  "+ rsync -aHAX ${CDIR}/ ${CSRC}/" \
  "+ mount ${CDIR}" \
  "+ mount ${SDIR}" \
  "+ systemctl start k3s-agent.service"; then
  ok "the plan stops the agent, copies the store onto its tier, binds, then starts it"
else
  no "the plan stops the agent, copies the store onto its tier, binds, then starts it"
fi
if printf '%s\n' "$REPLY_OUT" | grep -qF -- "+ rsync -aHAX ${SDIR}/"; then
  no "the empty local-path root is not copied — only a store with content is"
else
  ok "the empty local-path root is not copied — only a store with content is"
fi
tripwire_empty "the running-k3s dry run executed no host-mutating command"

# The same host with the containerd TIER already holding a store: the tier is
# the store, so nothing is copied over it and the unit is never stopped. This
# is the state migrate-tier.sh hands the installer.
reset_world
printf 'k3s-agent.service\n' > "$ACTIVE"
add_mount "$CACHE" /dev/mapper/nvmea-ci--cache
add_mount "$CSRC" /dev/mapper/nvmea-ci--containerd
mkdir -p "$CDIR" "$CSRC"
printf 'stale\n' > "$CDIR/leftover"
printf 'layers\n' > "$CSRC/blob"
write_five_lines
run_dry
if printf '%s\n' "$REPLY_OUT" | grep -qE '^\+ (rsync|systemctl (stop|start)) '; then
  no "a tier that already holds a store is never copied over, and k3s is never stopped"
  printf '%s\n' "$REPLY_OUT" | grep -E '^\+ (rsync|systemctl (stop|start)) '
else
  ok "a tier that already holds a store is never copied over, and k3s is never stopped"
fi

# ---------------------------------------------------------------------------
# D. Live tiers: the no-op contract.
# ---------------------------------------------------------------------------
printf '\n== D. every managed mountpoint already live: not one mutating command ==\n'
converged_world() {
  reset_world
  mkdir -p "$CACHE" "$CSRC" "$SSRC" "$CDIR" "$SDIR" "$(dirname "$DROPIN_DST")"
  cp "$DROPIN_SRC" "$DROPIN_DST"
  add_mount "$CACHE" /dev/mapper/nvmea-ci--cache
  add_mount "$CSRC" /dev/mapper/nvmea-ci--containerd
  add_mount "$SSRC" /dev/mapper/nvmea-ci--workvols
  add_mount "$CDIR" /dev/mapper/nvmea-ci--containerd
  add_mount "$SDIR" /dev/mapper/nvmea-ci--workvols
  write_five_lines
}
converged_world
run_dry
exits_zero "the converged host's --dry-run exits 0"
same "the converged host plans no mutating command at all" "" "$(plan_lines "$REPLY_OUT")"
tripwire_empty "the converged dry run executed no host-mutating command"

# ---------------------------------------------------------------------------
# E. Executed for real against the scratch host, then executed again.
# ---------------------------------------------------------------------------
printf '\n== E. a real run bootstraps the host, and a second run is a byte-exact no-op ==\n'
reset_world
run_live
exits_zero "the executed fresh run exits 0"
missing=""
for m in "$CACHE" "$CSRC" "$SSRC" "$CDIR" "$SDIR"; do
  grep -qE "^${m} " "$MOUNTS" || missing="${missing}
        ${m}"
done
if [ -z "$missing" ]; then
  ok "all five managed mountpoints are mounted when the run returns"
else
  no "all five managed mountpoints are mounted when the run returns:${missing}"
fi
absent=""
for line in "${FIVE_LINES[@]}"; do
  grep -qxF -- "$line" "$FSTAB" || absent="${absent}
        ${line}"
done
if [ -z "$absent" ]; then
  ok "the five lines are in fstab, byte-exact"
else
  no "the five lines are in fstab, byte-exact:${absent}"
fi
if grep -qxF -- '/dev/disk/by-uuid/dead-beef /mnt/backup ext4 nofail 0 2' "$FSTAB"; then
  ok "the unrelated fstab line is untouched"
else
  no "the unrelated fstab line is untouched"
fi

FSTAB_AFTER_FIRST="$(cat "$FSTAB")"
: > "$TRIPWIRE"
run_live
exits_zero "the second executed run exits 0"
same "the second run plans no mutating command at all" "" "$(plan_lines "$REPLY_OUT")"
same "the second run left fstab byte-identical" "$FSTAB_AFTER_FIRST" "$(cat "$FSTAB")"
tripwire_empty "the second run executed no host-mutating command"

# ---------------------------------------------------------------------------
# F. The half-applied state gmktec-xubuntu was left in, re-run for real.
# ---------------------------------------------------------------------------
printf '\n== F. fstab already carries the five lines and nothing is mounted ==\n'
reset_world
write_five_lines
FSTAB_BEFORE="$(cat "$FSTAB")"
run_live
exits_zero "the half-applied host's executed run exits 0"
same "no fstab line is duplicated or rewritten" "$FSTAB_BEFORE" "$(cat "$FSTAB")"
if printf '%s\n' "$REPLY_OUT" | grep -q '^+ fstab '; then
  no "the run plans no fstab change at all"
  printf '%s\n' "$REPLY_OUT" | grep '^+ fstab '
else
  ok "the run plans no fstab change at all"
fi
if compgen -G "${FSTAB}.pre-storage-layout-*" >/dev/null; then
  no "no fstab backup is taken when no line is replaced"
else
  ok "no fstab backup is taken when no line is replaced"
fi
missing=""
for m in "$CACHE" "$CSRC" "$SSRC" "$CDIR" "$SDIR"; do
  grep -qE "^${m} " "$MOUNTS" || missing="${missing}
        ${m}"
done
if [ -z "$missing" ]; then
  ok "the half-applied host ends with every mountpoint live"
else
  no "the half-applied host ends with every mountpoint live:${missing}"
fi

# ---------------------------------------------------------------------------
# G. Refusals.
# ---------------------------------------------------------------------------
printf '\n== G. refusals ==\n'
refuses() {  # refuses DESCRIPTION EXPECTED-FRAGMENT
  if [ "$REPLY_RC" -eq 0 ]; then
    no "${1} (exited 0)"
    return
  fi
  case "$REPLY_OUT" in
    *"$2"*) ok "$1" ;;
    *) no "${1} (message did not name it: ${REPLY_OUT})" ;;
  esac
}

reset_world
run_dry --force
refuses "an unknown argument is refused with the usage line" "unknown argument '--force'"

reset_world
grep -v '^ci-workvols ' "$LABELS" > "${LABELS}.tmp" && mv "${LABELS}.tmp" "$LABELS"
run_dry
refuses "a label no block device carries is refused, naming the label" \
  "no block device carries LABEL=ci-workvols"

reset_world
printf 'ci-cache /dev/mapper/old-cache\n' >> "$LABELS"
run_dry
refuses "two devices carrying one role label are refused as a half-done media swap" \
  "2 block devices carry LABEL=ci-cache"

# ---------------------------------------------------------------------------
printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
