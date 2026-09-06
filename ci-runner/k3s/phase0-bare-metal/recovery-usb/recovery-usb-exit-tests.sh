#!/usr/bin/env bash
# recovery-usb-exit-tests.sh — behavioral exit tests for the Recovery USB
# builder and its QEMU+OVMF boot harness.
#
# WHY FAKE BINARIES AND NOT A REAL STICK. The properties under test are what
# these scripts REFUSE to do and what they PLAN to do. Proving them against a
# real device would mean partitioning a real device to watch the guard fire —
# the exact destruction the guard exists to prevent — and proving the plan
# would mean a 20-minute debootstrap. So both scripts are exercised ONLY
# through `--dry-run`, against shim binaries first on PATH: a `blkid` that
# answers from an environment variable, and a shim for every mutating command
# (`wipefs`, `sgdisk`, `mkfs.*`, `debootstrap`, `chroot`, `qemu-system-x86_64`,
# …) that appends its argv to a log and exits 0. No device, no network, no
# host touched. Test 6 is the load-bearing one: after a dry run that log must
# be EMPTY, which is what "prints every command and executes none" means when
# it is measured rather than asserted.
#
# WHAT EACH TEST PROVES, one line each:
#
#    1  dry run on a clean target                -> exits 0
#    2  dry run emits the ESP kernel-copy step   (boot trap 1's fix)
#    3  dry run emits the ESP:/boot/grub/grub.cfg write (boot trap 2's fix)
#    4  the rendered menu loads the ESP copies   (/vmlinuz, /initrd.img)
#    5  the rendered menu never sends GRUB to the ext4 (/boot/vmlinuz…)
#    6  a dry run executes NOTHING               (mutator log empty)
#    7  populated target, no consent             -> REFUSES, names the device
#    8  populated target, consent names another  -> REFUSES, names both
#    9  populated target, consent names it       -> proceeds
#   10  a probe that cannot answer               -> REFUSES (fail-closed)
#   11  the archived package set survives the port, perccli included
#   12  --no-serial-console renders the proven kernel line exactly
#   13  no --device                              -> non-zero
#   14  boot test dry run renders qemu + both OVMF pflash drives
#   15  boot test dry run starts no qemu and states the PASS condition
#   16  boot test with no --image                -> non-zero
#
# Exit 0 iff every test passes. No arguments. Requires bash and nothing else.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="${HERE}/build-recovery-usb.sh"
BOOT_TEST="${HERE}/test-recovery-usb.sh"
[ -x "$BUILD" ] || {
  echo "FATAL: ${BUILD} not found or not executable" >&2
  exit 2
}
[ -x "$BOOT_TEST" ] || {
  echo "FATAL: ${BOOT_TEST} not found or not executable" >&2
  exit 2
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
SHIM_BIN="${WORK}/bin"
mkdir -p "$SHIM_BIN"
CMD_LOG="${WORK}/executed.log"
OUT_FILE="${WORK}/out"
ERR_FILE="${WORK}/err"

DEVICE=/dev/disk/by-id/usb-FAKE_RECOVERY_STICK-0:0
OTHER_DEVICE=/dev/disk/by-id/usb-SOME_OTHER_DISK-0:0

# ---------------------------------------------------------------------------
# The shims.
#
# `blkid` is the destruction gate's only source of truth, so it answers from
# FAKE_BLKID: `clean` (exit 2, blkid's "no signature found"), `populated`
# (a filesystem type on stdout), or `error` (an exit the gate cannot read).
# ---------------------------------------------------------------------------

cat >"${SHIM_BIN}/blkid" <<'SHIM'
#!/bin/sh
case "${FAKE_BLKID:-clean}" in
  populated) echo vfat; exit 0 ;;
  error)     echo "blkid: cannot open" >&2; exit 4 ;;
  *)         exit 2 ;;
esac
SHIM
chmod +x "${SHIM_BIN}/blkid"

# Every command either script would run against the host or the device. A dry
# run must invoke NONE of them; a shim that fires appends to CMD_LOG and test 6
# fails.
for cmd in wipefs sgdisk partprobe udevadm mkfs.vfat mkfs.ext4 mount umount \
  debootstrap chroot cp mkdir sync qemu-system-x86_64 sshpass ssh grub-install; do
  cat >"${SHIM_BIN}/${cmd}" <<SHIM
#!/bin/sh
echo "${cmd} \$*" >> "\${CMD_LOG:-/dev/null}"
exit 0
SHIM
  chmod +x "${SHIM_BIN}/${cmd}"
done

# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

PASSED=0
FAILED=0
RC=0
OUT=""
ERR=""

ok() {
  PASSED=$((PASSED + 1))
  printf 'ok    %s\n' "$*"
}

bad() {
  FAILED=$((FAILED + 1))
  printf 'FAIL  %s\n' "$*"
}

assert_contains() {
  local label="$1" haystack="$2" needle="$3"
  case "$haystack" in
    *"$needle"*) ok "$label" ;;
    *) bad "${label} — expected to find: ${needle}" ;;
  esac
}

assert_absent() {
  local label="$1" haystack="$2" needle="$3"
  case "$haystack" in
    *"$needle"*) bad "${label} — expected NOT to find: ${needle}" ;;
    *) ok "$label" ;;
  esac
}

assert_rc() {
  local label="$1" want="$2" got="$3"
  if [ "$got" -eq "$want" ]; then
    ok "$label"
  else
    bad "${label} — expected exit ${want}, got ${got}"
  fi
}

assert_nonzero() {
  local label="$1" got="$2"
  if [ "$got" -ne 0 ]; then
    ok "$label"
  else
    bad "${label} — expected a non-zero exit, got 0"
  fi
}

# run_script <blkid-state> <script> [args...]
run_script() {
  local state="$1" script="$2"
  shift 2
  : >"$CMD_LOG"
  FAKE_BLKID="$state" CMD_LOG="$CMD_LOG" PATH="${SHIM_BIN}:${PATH}" \
    "$script" "$@" >"$OUT_FILE" 2>"$ERR_FILE"
  RC=$?
  OUT="$(cat "$OUT_FILE")"
  ERR="$(cat "$ERR_FILE")"
}

# Pull the body of the `cat > <path-containing-marker> <<'EOF' … EOF` block a
# dry run printed, so the rendered file can be asserted on as a file rather
# than as a substring of the plan.
rendered_file() {
  local marker="$1"
  awk -v marker="$marker" '
    index($0, "+ cat > ") == 1 && index($0, marker) > 0 { inblock = 1; next }
    inblock && $0 == "EOF" { inblock = 0; next }
    inblock { print }
  ' "$OUT_FILE"
}

# ---------------------------------------------------------------------------
# Tests 1–6, 11–12: the plan a dry run renders for a clean target.
# ---------------------------------------------------------------------------

run_script clean "$BUILD" --dry-run "--device=${DEVICE}"
assert_rc "1  dry run on a clean target exits 0" 0 "$RC"

# shellcheck disable=SC2016  # `$KVER` is guest-side text being matched, not expanded.
assert_contains "2  dry run emits the ESP kernel copy (trap 1's fix)" \
  "$OUT" 'cp -f "/boot/vmlinuz-$KVER" /boot/efi/vmlinuz'
# shellcheck disable=SC2016  # Ditto.
assert_contains "2b dry run emits the ESP initrd copy (trap 1's fix)" \
  "$OUT" 'cp -f "/boot/initrd.img-$KVER" /boot/efi/initrd.img'

assert_contains "3  dry run writes the menu at ESP:/boot/grub/grub.cfg (trap 2's fix)" \
  "$OUT" '+ cat > /mnt/recovery-usb/boot/efi/boot/grub/grub.cfg'
# The CD-variant GRUB reads ESP:/boot/grub/grub.cfg and nothing else, so a menu
# written under the ESP's EFI/ tree would be a silently ignored second source
# of truth. Match the WRITE, not the word: step 8's own commentary names both
# ignored paths.
assert_absent "3b no menu is written under the ESP's EFI/ tree, where GRUB ignores it" \
  "$OUT" '+ cat > /mnt/recovery-usb/boot/efi/EFI'

GRUB_CFG="$(rendered_file '/boot/efi/boot/grub/grub.cfg')"
assert_contains "4  the rendered menu loads the ESP kernel copy" \
  "$GRUB_CFG" 'linux /vmlinuz '
assert_contains "4b the rendered menu loads the ESP initrd copy" \
  "$GRUB_CFG" 'initrd /initrd.img'
assert_contains "4c the rendered menu finds the ESP by its own UUID" \
  "$GRUB_CFG" 'search.fs_uuid '
assert_absent "5  the rendered menu never sends GRUB to the ext4 kernel" \
  "$GRUB_CFG" 'linux /boot/vmlinuz'
assert_absent "5b the rendered menu never sends GRUB to the ext4 initrd" \
  "$GRUB_CFG" 'initrd /boot/initrd.img'

if [ -s "$CMD_LOG" ]; then
  bad "6  a dry run executed nothing — but these ran: $(tr '\n' ';' <"$CMD_LOG")"
else
  ok "6  a dry run executed nothing (mutator log empty)"
fi

assert_contains "11 the archived storage toolchain survives the port" \
  "$OUT" 'lvm2 mdadm gdisk parted dosfstools smartmontools nvme-cli ipmitool rsync'
assert_contains "11b the archived desktop/sshd package set survives the port" \
  "$OUT" 'ubuntu-desktop-minimal'
assert_contains "11c perccli is copied onto the stick" \
  "$OUT" '+ cp -a /opt/MegaRAID /mnt/recovery-usb/opt/'

run_script clean "$BUILD" --dry-run "--device=${DEVICE}" --no-serial-console
PROVEN_CFG="$(rendered_file '/boot/efi/boot/grub/grub.cfg')"
assert_absent "12 --no-serial-console renders the proven kernel line exactly" \
  "$PROVEN_CFG" 'console='
assert_contains "12b --no-serial-console still loads the ESP kernel copy" \
  "$PROVEN_CFG" 'linux /vmlinuz '

# ---------------------------------------------------------------------------
# Tests 7–10, 13: the destruction gate.
# ---------------------------------------------------------------------------

run_script populated "$BUILD" --dry-run "--device=${DEVICE}"
assert_nonzero "7  a populated target without consent is refused" "$RC"
assert_contains "7b the refusal names the device" "$ERR" "$DEVICE"
if [ -s "$CMD_LOG" ]; then
  bad "7c the refusal ran nothing — but these ran: $(tr '\n' ';' <"$CMD_LOG")"
else
  ok "7c the refusal ran nothing"
fi

run_script populated "$BUILD" --dry-run "--device=${DEVICE}" \
  "--i-consent-to-destroy=${OTHER_DEVICE}"
assert_nonzero "8  consent naming a different device is refused" "$RC"
assert_contains "8b that refusal names the device being written" "$ERR" "$DEVICE"
assert_contains "8c that refusal names the device consent did name" "$ERR" "$OTHER_DEVICE"

run_script populated "$BUILD" --dry-run "--device=${DEVICE}" \
  "--i-consent-to-destroy=${DEVICE}"
assert_rc "9  consent naming the target lets the build proceed" 0 "$RC"
assert_contains "9b the gate records the consent it accepted" "$OUT" 'destruction consent names'

run_script error "$BUILD" --dry-run "--device=${DEVICE}"
assert_nonzero "10 a probe that cannot answer is refused (fail-closed)" "$RC"
assert_contains "10b the fail-closed refusal names the device" "$ERR" "$DEVICE"

run_script clean "$BUILD" --dry-run
assert_nonzero "13 a build with no --device is refused" "$RC"

# ---------------------------------------------------------------------------
# Tests 14–16: the boot harness.
# ---------------------------------------------------------------------------

run_script clean "$BOOT_TEST" --dry-run "--image=${WORK}/recovery.img"
assert_rc "14 boot-test dry run exits 0" 0 "$RC"
assert_contains "14b it renders a qemu-system-x86_64 invocation" \
  "$OUT" '+ qemu-system-x86_64'
assert_contains "14c it attaches the OVMF firmware code as pflash" \
  "$OUT" 'if=pflash,format=raw,readonly=on,file='
assert_contains "14d it attaches a writable OVMF variable store as pflash" \
  "$OUT" 'OVMF_VARS.fd'
assert_contains "14e it attaches the image under test as the boot drive" \
  "$OUT" "file=${WORK}/recovery.img,format=raw"

assert_contains "15 it states the login-prompt PASS condition" \
  "$OUT" 'PASS requires the kernel to reach a login prompt'
if [ -s "$CMD_LOG" ]; then
  bad "15b the boot-test dry run started nothing — but these ran: $(tr '\n' ';' <"$CMD_LOG")"
else
  ok "15b the boot-test dry run started nothing (no qemu, mutator log empty)"
fi

run_script clean "$BOOT_TEST" --dry-run
assert_nonzero "16 a boot test with no --image is refused" "$RC"

# ---------------------------------------------------------------------------

printf '\n%s passed, %s failed\n' "$PASSED" "$FAILED"
[ "$FAILED" -eq 0 ] || exit 1
