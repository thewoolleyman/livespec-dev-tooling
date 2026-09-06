#!/usr/bin/env bash
# test-recovery-usb.sh — boot the Recovery USB under QEMU + OVMF and fail
# unless the kernel reaches a login prompt.
#
# PROVENANCE. Ported from the livespec repository's FROZEN plan archive:
#   plan/archive/poweredge-raid-array-maintenance/research/test-recovery-usb.sh
# read at livespec commit 20447b544829d8749c3f460406383f5afeaf7191 (that file's
# own last-touching commit there is 41795f742d21f4c73309f03f4c6d857abe93cc63).
# The archive is frozen and never edited; this is the maintained copy.
#
# WHY THIS HARNESS EXISTS. It is what caught BOTH boot traps recorded in
# `README.md` — the ext4-unreadable-by-GRUB trap and the CD-variant GRUB's
# single menu path — before anyone walked to a machine. A stick that fails
# here has never been walked to a rack; a stick that passes here still owes a
# physical boot, which is a human step (livespec work-item livespec-ifwnqj.4).
#
# WHAT "PASS" MEANS. The kernel reaching a login prompt on the serial console:
# firmware -> shim -> GRUB -> kernel -> userspace -> getty. Anything short of
# that — a bare `grub>` prompt, a kernel panic, an early QEMU exit, a timeout —
# is a FAIL. The serial console is reachable because `build-recovery-usb.sh`
# puts `console=ttyS0,115200` on the kernel line; a stick built with
# `--no-serial-console` renders the proven kernel line instead and CANNOT be
# proven by this harness.
#
# WHAT IT DOES NOT DO. It never unmounts anything behind the operator's back:
# given a block device with a partition still mounted on the host, it REFUSES
# and names the mount, because a host writing the bytes the guest is reading
# is a corrupt test, not a slow one. The OVMF variable store is a throwaway
# copy, so the firmware's own writes never reach the installed template.
#
# `--dry-run` prints every command it would run, in order, and executes none.

set -euo pipefail

exec 9>&1

IMAGE=""
DRY_RUN=0
TIMEOUT=600
POLL_SECONDS=10
MEMORY=4096
SMP=4
OVMF_CODE=""
OVMF_VARS=""
SSH_VERIFY=0
SSH_PORT=2222

# Login-prompt marker. agetty prints "<hostname> login: " on the console it
# owns; systemd spawns serial-getty@ttyS0 because the kernel line names it.
LOGIN_PROMPT_PATTERN='login: *$'

OVMF_CODE_CANDIDATES=(
  /usr/share/OVMF/OVMF_CODE_4M.fd
  /usr/share/OVMF/OVMF_CODE.fd
  /usr/share/edk2/ovmf/OVMF_CODE.fd
  /usr/share/qemu/edk2-x86_64-code.fd
)
OVMF_VARS_CANDIDATES=(
  /usr/share/OVMF/OVMF_VARS_4M.fd
  /usr/share/OVMF/OVMF_VARS.fd
  /usr/share/edk2/ovmf/OVMF_VARS.fd
  /usr/share/qemu/edk2-i386-vars.fd
)

usage() {
  cat <<'USAGE'
Usage: test-recovery-usb.sh --image=<path> [options]

Required:
  --image=<path>          The built stick: a raw image file, or the stick's
                          block device (address it by its /dev/disk/by-id/
                          path).

Options:
  --dry-run               Print every command that would run; run none.
  --timeout=<seconds>     Give up after this long (default: 600).
  --memory=<MiB>          Guest memory (default: 4096).
  --smp=<n>               Guest vCPUs (default: 4).
  --ovmf-code=<path>      OVMF firmware code image (default: autodetected).
  --ovmf-vars=<path>      OVMF variables template (default: autodetected).
  --ssh-verify            After the login prompt appears, ssh in as
                          root/password over the forwarded port and verify the
                          storage toolchain, perccli, and the stick README.
  --ssh-port=<n>          Host port forwarded to the guest's 22 (default: 2222).
  -h, --help              This text.

Exit status: 0 only if the kernel reached a login prompt.
USAGE
}

die() {
  printf 'ABORT: %s\n' "$*" >&2
  exit 1
}

# Print an argv as a copy-pasteable command line: shell-safe words verbatim,
# anything else through printf %q. `%q` on everything would escape the commas
# in QEMU's `-drive` values into `\,`, which is valid but unreadable.
trace_argv() {
  local word
  {
    printf '+'
    for word in "$@"; do
      if [[ $word =~ ^[A-Za-z0-9_@%+=:,./-]+$ ]]; then
        printf ' %s' "$word"
      else
        printf ' %q' "$word"
      fi
    done
    printf '\n'
  } >&9
}

run() {
  trace_argv "$@"
  if [ "$DRY_RUN" -eq 1 ]; then
    return 0
  fi
  "$@"
}

note() {
  printf '%s\n' "$*" >&9
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --image=*) IMAGE="${1#*=}" ;;
      --image)
        [ "$#" -ge 2 ] || die "--image needs a value"
        IMAGE="$2"
        shift
        ;;
      --dry-run) DRY_RUN=1 ;;
      --timeout=*) TIMEOUT="${1#*=}" ;;
      --memory=*) MEMORY="${1#*=}" ;;
      --smp=*) SMP="${1#*=}" ;;
      --ovmf-code=*) OVMF_CODE="${1#*=}" ;;
      --ovmf-vars=*) OVMF_VARS="${1#*=}" ;;
      --ssh-verify) SSH_VERIFY=1 ;;
      --ssh-port=*) SSH_PORT="${1#*=}" ;;
      -h | --help)
        usage
        exit 0
        ;;
      *) die "unknown argument: $1" ;;
    esac
    shift
  done
  [ -n "$IMAGE" ] || die "--image=<path> is required (see --help)"
}

# First existing candidate, or the first candidate as a documented default so
# that --dry-run renders a complete command on a host with no OVMF installed.
first_existing() {
  local candidate
  for candidate in "$@"; do
    if [ -f "$candidate" ]; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  printf '%s' "$1"
}

resolve_firmware() {
  [ -n "$OVMF_CODE" ] || OVMF_CODE="$(first_existing "${OVMF_CODE_CANDIDATES[@]}")"
  [ -n "$OVMF_VARS" ] || OVMF_VARS="$(first_existing "${OVMF_VARS_CANDIDATES[@]}")"
  if [ "$DRY_RUN" -eq 0 ]; then
    [ -f "$OVMF_CODE" ] || die "OVMF firmware code not found at ${OVMF_CODE} (pass --ovmf-code=<path>)"
    [ -f "$OVMF_VARS" ] || die "OVMF variables template not found at ${OVMF_VARS} (pass --ovmf-vars=<path>)"
  fi
}

# Refuse rather than unmount: a mounted partition means the host is writing to
# the very bytes the guest is about to read, and unmounting it behind the
# operator is not this harness's call to make.
refuse_if_host_mounted() {
  if [ "$DRY_RUN" -eq 1 ] || [ ! -b "$IMAGE" ]; then
    return 0
  fi
  local real mounted
  real="$(readlink -f "$IMAGE")"
  mounted="$(lsblk -lno NAME,MOUNTPOINT "$real" 2>/dev/null | awk 'NF>1 {print $1" on "$2}' || true)"
  if [ -n "$mounted" ]; then
    die "refusing to boot ${IMAGE}: the host still has it mounted (${mounted}). Unmount it first"
  fi
}

kvm_args() {
  if [ -e /dev/kvm ]; then
    printf '%s' "-enable-kvm -cpu host"
  fi
}

main() {
  parse_args "$@"
  resolve_firmware
  refuse_if_host_mounted

  local workdir vars_copy serial_log qemu_log kvm
  workdir="${TMPDIR:-/tmp}/recovery-usb-boot-test.$$"
  vars_copy="${workdir}/OVMF_VARS.fd"
  serial_log="${workdir}/serial.log"
  qemu_log="${workdir}/qemu.log"
  kvm="$(kvm_args)"

  if [ "$DRY_RUN" -eq 1 ]; then
    note "=== DRY RUN — every command below is printed and none is executed ==="
  fi
  note "=== boot-testing ${IMAGE} under QEMU + OVMF (${OVMF_CODE}) ==="
  note "=== PASS requires the kernel to reach a login prompt within ${TIMEOUT}s ==="

  run mkdir -p "$workdir"
  run cp "$OVMF_VARS" "$vars_copy"

  # Built as one argv so the dry run prints the exact invocation.
  local -a qemu_argv=(
    qemu-system-x86_64
    -machine q35
    -m "$MEMORY"
    -smp "$SMP"
    -drive "if=pflash,format=raw,readonly=on,file=${OVMF_CODE}"
    -drive "if=pflash,format=raw,file=${vars_copy}"
    -drive "file=${IMAGE},format=raw,if=virtio,cache=none"
    -netdev "user,id=n0,hostfwd=tcp:127.0.0.1:${SSH_PORT}-:22"
    -device "virtio-net-pci,netdev=n0"
    -display none
    -serial "file:${serial_log}"
  )
  if [ -n "$kvm" ]; then
    qemu_argv+=(-enable-kvm -cpu host)
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    trace_argv "${qemu_argv[@]}"
    note "=== [poll] grep -E '${LOGIN_PROMPT_PATTERN}' ${serial_log} every ${POLL_SECONDS}s until ${TIMEOUT}s ==="
    if [ "$SSH_VERIFY" -eq 1 ]; then
      note "=== [verify] ssh -p ${SSH_PORT} root@127.0.0.1 — toolchain, perccli, stick README ==="
    fi
    note "=== DRY RUN COMPLETE — no QEMU was started ==="
    return 0
  fi

  trace_argv "${qemu_argv[@]}"
  "${qemu_argv[@]}" >"$qemu_log" 2>&1 &
  local qpid=$!
  note "=== qemu pid=${qpid} (kvm: ${kvm:-none}) serial: ${serial_log} ==="

  local result=FAIL elapsed=0
  while [ "$elapsed" -lt "$TIMEOUT" ]; do
    sleep "$POLL_SECONDS"
    elapsed=$((elapsed + POLL_SECONDS))
    if [ -f "$serial_log" ] && grep -Eq "$LOGIN_PROMPT_PATTERN" "$serial_log"; then
      result=PASS
      break
    fi
    if ! kill -0 "$qpid" 2>/dev/null; then
      note "=== qemu exited after ~${elapsed}s without reaching a login prompt ==="
      break
    fi
  done

  if [ "$result" = PASS ] && [ "$SSH_VERIFY" -eq 1 ]; then
    verify_over_ssh || result=FAIL
  fi

  kill "$qpid" 2>/dev/null || true
  sleep 3
  kill -9 "$qpid" 2>/dev/null || true

  note "=== boot-probe: ${result} after ~${elapsed}s ==="
  if [ "$result" != PASS ]; then
    note "=== serial tail ==="
    tail -n 40 "$serial_log" >&9 2>/dev/null || true
    die "the kernel did not reach a login prompt; serial log kept at ${serial_log}"
  fi
  note "TEST_RESULT=PASS"
}

verify_over_ssh() {
  command -v sshpass >/dev/null 2>&1 || die "--ssh-verify needs sshpass on PATH"
  # shellcheck disable=SC2016  # The expansions below must happen in the GUEST.
  sshpass -p password ssh -p "$SSH_PORT" \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5 \
    root@127.0.0.1 '
      set -e
      echo "hostname: $(hostname)"
      echo "kernel: $(uname -r)"
      sudo -n true && echo "sudo-nopasswd: yes"
      for t in lvm mdadm sgdisk smartctl nvme ipmitool rsync debootstrap; do
        command -v "$t" >/dev/null || { echo "tool $t: MISSING"; exit 1; }
      done
      echo "tools: ok"
      test -x /opt/MegaRAID/perccli/perccli64 && echo "perccli: ok"
      test -s /root/README-RECOVERY.md && echo "readme: ok"
      cmp -s /boot/efi/vmlinuz "/boot/vmlinuz-$(uname -r)" && echo "esp-kernel: current"
    ' >&9
}

main "$@"
