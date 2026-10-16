#!/usr/bin/env bash
# vm.sh — the disposable Ubuntu 26.04 VM the docker_engine role's acceptance
# runs against before any converge on gmktec-xubuntu.
#
# WHY. docs/docker-engine-guard-design.md §"Acceptance before the gmktec
# converge", layer (b): the guard and the role are exercised by fault
# injection on a disposable host with real systemd, real dpkg, real
# iptables-nft and the real three packages, before gmktec — whose only remote
# access is Tailscale SSH and which nobody can reach physically. This script
# owns the VM's LIFECYCLE only: fetch-verify the cloud image, boot it, reach
# it, snapshot it, restore it, stop it. The fault-injection driver and the
# gmktec-shaped baseline (stub k3s agent, stub LLM health, the measured
# firewall and sysctls) sit on top of it.
#
# WHERE. The control node (vps). It has qemu-system-x86_64 and no /dev/kvm,
# so the guest runs under TCG and is SLOW: budget minutes per boot. hp-xubuntu
# has KVM but runs live factory work and is never used for this.
#
# STATE. Everything lives under $DOCKER_ENGINE_VM_DIR (default
# ~/.cache/docker-engine-guard-vm): the verified base image, a qcow2 overlay
# the guest writes, a throwaway SSH key, the NoCloud seed, logs, a pidfile.
# The base image is never written. `reset` discards the overlay; `snapshot`
# and `restore` name internal qcow2 snapshots of the overlay, taken and
# applied only while the VM is stopped.
#
# `--dry-run` prints every command it would run, in order, and executes none.

set -euo pipefail

VM_DIR="${DOCKER_ENGINE_VM_DIR:-$HOME/.cache/docker-engine-guard-vm}"
IMAGE_URL_BASE="https://cloud-images.ubuntu.com/releases/26.04/release"
IMAGE_NAME="ubuntu-26.04-server-cloudimg-amd64.img"
SSH_PORT="${DOCKER_ENGINE_VM_SSH_PORT:-2229}"
# The guest's LLM-health stub (baseline.sh, port 8080), forwarded so the
# role's CONTROLLER-SIDE probe, which runs on the control node, can reach it.
LLM_PORT="${DOCKER_ENGINE_VM_LLM_PORT:-2280}"
MEMORY="${DOCKER_ENGINE_VM_MEMORY:-4096}"
SMP="${DOCKER_ENGINE_VM_SMP:-4}"
DISK_SIZE="${DOCKER_ENGINE_VM_DISK:-20G}"
BOOT_TIMEOUT="${DOCKER_ENGINE_VM_BOOT_TIMEOUT:-2400}"
GUEST_USER="guard"
DRY_RUN=0

usage() {
  cat <<'EOF'
usage: vm.sh [--dry-run] <command> [args]

  fetch              download the 26.04 cloud image and verify it against SHA256SUMS
  up                 boot the VM (creating the overlay on first use) and wait for SSH
  ssh [cmd...]       run a command in the guest as the sudo-capable guard user
  down               power the guest off, then make sure qemu has exited
  snapshot <name>    record the stopped overlay as internal snapshot <name>
  restore <name>     return the stopped overlay to snapshot <name>
  reset              discard the overlay entirely (next `up` starts pristine)
  status             report whether the VM is running and reachable
EOF
}

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '+'
    printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

die() {
  printf 'vm.sh: %s\n' "$*" >&2
  exit 1
}

overlay() { printf '%s/overlay.qcow2' "$VM_DIR"; }
pidfile() { printf '%s/qemu.pid' "$VM_DIR"; }
key() { printf '%s/id_ed25519' "$VM_DIR"; }

qemu_running() {
  local pid
  [[ -f "$(pidfile)" ]] || return 1
  pid="$(cat "$(pidfile)")"
  # Match the live process by its executable, never by a command-line search
  # that could match this shell or an unrelated qemu.
  [[ -e "/proc/${pid}/exe" ]] && [[ "$(readlink "/proc/${pid}/exe")" == */qemu-system-x86_64 ]]
}

ssh_argv() {
  printf '%s\n' ssh -i "$(key)" -p "$SSH_PORT" \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o LogLevel=ERROR -o ConnectTimeout=10 -o BatchMode=yes \
    "${GUEST_USER}@127.0.0.1"
}

cmd_fetch() {
  run mkdir -p "$VM_DIR"
  run curl -sfL --max-time 60 -o "$VM_DIR/SHA256SUMS" "$IMAGE_URL_BASE/SHA256SUMS"
  if [[ "$DRY_RUN" -eq 0 ]] && [[ -f "$VM_DIR/$IMAGE_NAME" ]] &&
    (cd "$VM_DIR" && grep " \*\?${IMAGE_NAME}\$" SHA256SUMS | sha256sum -c --status); then
    printf 'vm.sh: %s already present and verified\n' "$IMAGE_NAME"
    return 0
  fi
  run curl -sfL --max-time 3600 -o "$VM_DIR/$IMAGE_NAME" "$IMAGE_URL_BASE/$IMAGE_NAME"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    (cd "$VM_DIR" && grep " \*\?${IMAGE_NAME}\$" SHA256SUMS | sha256sum -c) ||
      die "the downloaded image does not match SHA256SUMS; refusing to use it"
  fi
}

write_seed() {
  local seed="$VM_DIR/seed"
  run mkdir -p "$seed"
  [[ -f "$(key)" ]] || run ssh-keygen -q -t ed25519 -N '' -C docker-engine-guard-vm -f "$(key)"
  [[ "$DRY_RUN" -eq 1 ]] && return 0
  printf 'instance-id: docker-engine-guard-vm\nlocal-hostname: guard-vm\n' >"$seed/meta-data"
  : >"$seed/vendor-data"
  cat >"$seed/user-data" <<EOF
#cloud-config
users:
  - name: ${GUEST_USER}
    groups: [sudo]
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - $(cat "$(key).pub")
ssh_pwauth: false
package_update: false
package_upgrade: false
EOF
}

cmd_up() {
  qemu_running && { printf 'vm.sh: already running\n'; return 0; }
  [[ -f "$VM_DIR/$IMAGE_NAME" ]] || [[ "$DRY_RUN" -eq 1 ]] || die "no base image; run: vm.sh fetch"
  [[ -f "$(overlay)" ]] ||
    run qemu-img create -q -f qcow2 -F qcow2 -b "$VM_DIR/$IMAGE_NAME" "$(overlay)" "$DISK_SIZE"
  write_seed

  # The NoCloud seed is served over HTTP from the control node's loopback,
  # which the guest reaches as 10.0.2.2 through QEMU's user-mode network.
  # This avoids needing an ISO tool on the control node.
  local seed_port
  seed_port="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    python3 -m http.server --bind 127.0.0.1 --directory "$VM_DIR/seed" "$seed_port" \
      >"$VM_DIR/seed-http.log" 2>&1 &
    printf '%s\n' "$!" >"$VM_DIR/seed-http.pid"
  fi

  run qemu-system-x86_64 \
    -machine q35 -accel tcg,thread=multi -cpu max \
    -m "$MEMORY" -smp "$SMP" \
    -drive "file=$(overlay),if=virtio,format=qcow2" \
    -netdev "user,id=net0,hostfwd=tcp:127.0.0.1:${SSH_PORT}-:22,hostfwd=tcp:127.0.0.1:${LLM_PORT}-:8080" \
    -device virtio-net-pci,netdev=net0 \
    -smbios "type=1,serial=ds=nocloud;s=http://10.0.2.2:${seed_port}/" \
    -display none -serial "file:$VM_DIR/serial.log" \
    -daemonize -pidfile "$(pidfile)"

  [[ "$DRY_RUN" -eq 1 ]] && return 0
  local -a ssh
  mapfile -t ssh < <(ssh_argv)
  local deadline=$((SECONDS + BOOT_TIMEOUT))
  until "${ssh[@]}" true 2>/dev/null; do
    qemu_running || die "qemu exited during boot; see $VM_DIR/serial.log"
    ((SECONDS < deadline)) || die "no SSH within ${BOOT_TIMEOUT}s; see $VM_DIR/serial.log"
    sleep 10
  done
  "${ssh[@]}" sudo cloud-init status --wait >/dev/null 2>&1 || true
  stop_seed_server
  printf 'vm.sh: up; ssh on 127.0.0.1:%s as %s\n' "$SSH_PORT" "$GUEST_USER"
}

stop_seed_server() {
  local pid
  [[ -f "$VM_DIR/seed-http.pid" ]] || return 0
  pid="$(cat "$VM_DIR/seed-http.pid")"
  [[ -e "/proc/${pid}/exe" ]] && kill "$pid" 2>/dev/null || true
  rm -f "$VM_DIR/seed-http.pid"
}

cmd_ssh() {
  local -a ssh
  mapfile -t ssh < <(ssh_argv)
  run "${ssh[@]}" "$@"
}

cmd_down() {
  if qemu_running; then
    local -a ssh
    mapfile -t ssh < <(ssh_argv)
    run "${ssh[@]}" sudo systemctl poweroff >/dev/null 2>&1 || true
    local deadline=$((SECONDS + 300))
    while [[ "$DRY_RUN" -eq 0 ]] && qemu_running && ((SECONDS < deadline)); do sleep 5; done
    if qemu_running; then run kill "$(cat "$(pidfile)")"; fi
  fi
  stop_seed_server
  run rm -f "$(pidfile)"
}

require_stopped() {
  qemu_running && die "the VM is running; run: vm.sh down"
  return 0
}

cmd_snapshot() {
  [[ $# -eq 1 ]] || die "usage: vm.sh snapshot <name>"
  require_stopped
  run qemu-img snapshot -d "$1" "$(overlay)" 2>/dev/null || true
  run qemu-img snapshot -c "$1" "$(overlay)"
}

cmd_restore() {
  [[ $# -eq 1 ]] || die "usage: vm.sh restore <name>"
  require_stopped
  run qemu-img snapshot -a "$1" "$(overlay)"
}

cmd_reset() {
  require_stopped
  run rm -f "$(overlay)"
}

cmd_status() {
  if qemu_running; then
    local -a ssh
    mapfile -t ssh < <(ssh_argv)
    if "${ssh[@]}" true 2>/dev/null; then echo "running, reachable"; else echo "running, not reachable"; fi
  else
    echo "stopped"
  fi
}

main() {
  if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
    shift
  fi
  local cmd="${1:-}"
  [[ -n "$cmd" ]] || {
    usage
    exit 2
  }
  shift
  case "$cmd" in
  fetch) cmd_fetch "$@" ;;
  up) cmd_up "$@" ;;
  ssh) cmd_ssh "$@" ;;
  down) cmd_down "$@" ;;
  snapshot) cmd_snapshot "$@" ;;
  restore) cmd_restore "$@" ;;
  reset) cmd_reset "$@" ;;
  status) cmd_status "$@" ;;
  -h | --help) usage ;;
  *)
    usage >&2
    exit 2
    ;;
  esac
}

main "$@"
