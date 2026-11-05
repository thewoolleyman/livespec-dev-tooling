#!/usr/bin/env bash
# start-homelab-worker-node-container.sh <host> — provision and start the one
# homelab worker node of a declared host.
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes" (plan homelab-k8s-worker-nodes). This stage converges the host side:
#
#   1. <host> must be declared by homelab-worker/hosts/<host>.env, and is
#      refused, naming the declared hosts, before any host change.
#   2. The worker name is derived once: <host>-homelab-worker.
#   3. Lima is installed through Homebrew only when `limactl` is absent; an
#      installed Lima at or above lima/min-version is reused and never
#      upgraded, and an older one is refused by version.
#   4. A host already bound to a different *-homelab-worker VM is refused.
#   5. The named VZ VM is created only when absent, and an existing one is
#      started in place — never stopped, recreated or deleted. A VM whose
#      CPUs, memory or disk differ from the declaration is refused, naming
#      the setting, instead of being rebuilt. A new VM gets an XFS data disk,
#      hwdata (Lima labels it lima-hwdata; an XFS label holds at most 12
#      characters), for the worker's containerd store and caches.
#   6. The VM capability probe (probe-vm-capabilities.sh) runs inside the VM;
#      any missing capability stops the task, naming each with its remedy,
#      before the worker container starts. The report is kept beside the
#      worker's non-secret state.
#   7. The worker container is started or reconciled inside the VM from the
#      digest-pinned image in image/ref (vm/converge-worker-container.sh). It
#      joins the tailnet as <worker>, printing a login URL for the operator
#      while one is needed, and starts the kubelet once enrollment has been
#      delivered.
#   8. With HOMELAB_WORKER_ENROLLMENT=<dir> (the directory
#      enrollment/mint-bootstrap-token.sh wrote on the operator's side), its
#      bootstrap-kubeconfig and client-ca.crt are delivered into the worker's
#      enrollment state in the VM on stdin, never in an argument, before the
#      container step. The directory is checked before any host change.
#
# Every declared host runs this same code path; a host's .env carries data
# only. The script stays bash 3.2-compatible because a worker host is not a
# development box and may have only macOS's /bin/bash.
set -euo pipefail

prog="start-homelab-worker-node-container"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hosts_dir="$here/hosts"
template="$here/lima/worker.yaml"
probe="$here/probe-vm-capabilities.sh"
converge="$here/vm/converge-worker-container.sh"
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/livespec-homelab-worker"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

say() {
  printf '%s: %s\n' "$prog" "$*"
}

declared_hosts() {
  local f
  for f in "$hosts_dir"/*.env; do
    [ -e "$f" ] || continue
    f="${f##*/}"
    printf '%s ' "${f%.env}"
  done
}

# version_ge A B: true when dotted version A >= B (numeric fields, missing = 0).
version_ge() {
  local a="$1" b="$2" i x y
  local IFS=.
  # shellcheck disable=SC2206  # deliberate field split on '.'
  local av=($a) bv=($b)
  for i in 0 1 2; do
    x="${av[$i]:-0}"
    y="${bv[$i]:-0}"
    x="${x%%[!0-9]*}"
    y="${y%%[!0-9]*}"
    x="${x:-0}"
    y="${y:-0}"
    if [ "$x" -gt "$y" ]; then return 0; fi
    if [ "$x" -lt "$y" ]; then return 1; fi
  done
  return 0
}

host="${1:-}"
if [ -z "$host" ] || [ "$#" -ne 1 ]; then
  die "usage: $prog <host>; declared hosts: $(declared_hosts)"
fi
case "$host" in
  *[!a-z0-9-]* | -*) die "host '$host' is not a valid host name; declared hosts: $(declared_hosts)" ;;
esac
if [ ! -f "$hosts_dir/$host.env" ]; then
  die "host '$host' is not declared in homelab-worker/hosts/; declared hosts: $(declared_hosts)"
fi

WORKER_HOST_OS=""
WORKER_VM_CPUS=""
WORKER_VM_MEMORY_GIB=""
WORKER_VM_DISK_GIB=""
WORKER_DATA_DISK_GIB=""
# shellcheck disable=SC1090  # the declared host's data file
. "$hosts_dir/$host.env"
for key in WORKER_HOST_OS WORKER_VM_CPUS WORKER_VM_MEMORY_GIB WORKER_VM_DISK_GIB WORKER_DATA_DISK_GIB; do
  eval "val=\${$key}"
  # shellcheck disable=SC2154  # val is assigned by the eval above
  [ -n "$val" ] || die "homelab-worker/hosts/$host.env does not declare $key"
done

worker="$host-homelab-worker"
data_disk="hwdata"

enrollment="${HOMELAB_WORKER_ENROLLMENT:-}"
if [ -n "$enrollment" ]; then
  for f in bootstrap-kubeconfig client-ca.crt; do
    [ -s "$enrollment/$f" ] || die "HOMELAB_WORKER_ENROLLMENT '$enrollment' has no $f; mint it with homelab-worker/enrollment/mint-bootstrap-token.sh"
  done
fi

os="$(uname -s)"
if [ "$os" != "$WORKER_HOST_OS" ]; then
  die "host '$host' is declared for $WORKER_HOST_OS but this machine runs $os"
fi

min_version="$(tr -d '[:space:]' <"$here/lima/min-version")"
if ! command -v limactl >/dev/null 2>&1; then
  command -v brew >/dev/null 2>&1 ||
    die "limactl is absent and Homebrew is not on PATH; install Homebrew (https://brew.sh), then rerun"
  say "installing Lima through Homebrew (limactl is absent)"
  brew install lima
  command -v limactl >/dev/null 2>&1 || die "brew install lima finished but limactl is still not on PATH"
fi
lima_version="$(limactl --version | awk '{print $NF}')"
lima_version="${lima_version#v}"
if ! version_ge "$lima_version" "$min_version"; then
  die "installed Lima $lima_version is older than the minimum $min_version; this task never upgrades Lima — upgrade it yourself (brew upgrade lima), then rerun"
fi
say "reusing Lima $lima_version (minimum $min_version)"

instances="$(limactl list --format '{{.Name}}' 2>/dev/null || true)"
other="$(printf '%s\n' "$instances" | grep -- '-homelab-worker$' | grep -vx -- "$worker" | head -n 1 || true)"
if [ -n "$other" ]; then
  die "this host is already bound to worker $other; refusing to create a second worker $worker"
fi

if printf '%s\n' "$instances" | grep -qx -- "$worker"; then
  read -r status cpus memory disk <<EOF_LIST
$(limactl list --format '{{.Status}} {{.CPUs}} {{.Memory}} {{.Disk}}' "$worker")
EOF_LIST
  gib=$((1024 * 1024 * 1024))
  [ "$cpus" = "$WORKER_VM_CPUS" ] ||
    die "VM $worker has cpus=$cpus but homelab-worker/hosts/$host.env declares WORKER_VM_CPUS=$WORKER_VM_CPUS; refusing to rebuild the VM — change it with 'limactl edit $worker' or revert the declaration"
  [ "$memory" = "$((WORKER_VM_MEMORY_GIB * gib))" ] ||
    die "VM $worker has memory=$memory bytes but homelab-worker/hosts/$host.env declares WORKER_VM_MEMORY_GIB=$WORKER_VM_MEMORY_GIB; refusing to rebuild the VM — change it with 'limactl edit $worker' or revert the declaration"
  [ "$disk" = "$((WORKER_VM_DISK_GIB * gib))" ] ||
    die "VM $worker has disk=$disk bytes but homelab-worker/hosts/$host.env declares WORKER_VM_DISK_GIB=$WORKER_VM_DISK_GIB; refusing to rebuild the VM — revert the declaration"
  if [ "$status" = "Running" ]; then
    say "VM $worker is already running; keeping it"
  else
    say "starting existing VM $worker (status $status); its disk is kept"
    limactl start --tty=false "$worker"
  fi
else
  if limactl disk list --json 2>/dev/null | grep -q "\"name\":\"$data_disk\""; then
    say "reusing data disk $data_disk"
  else
    say "creating data disk $data_disk (${WORKER_DATA_DISK_GIB} GiB)"
    limactl disk create "$data_disk" --size="${WORKER_DATA_DISK_GIB}GiB" --format=raw
  fi
  say "creating VM $worker (vz, ${WORKER_VM_CPUS} CPUs, ${WORKER_VM_MEMORY_GIB} GiB memory, ${WORKER_VM_DISK_GIB} GiB disk)"
  limactl create --name="$worker" --vm-type=vz --cpus="$WORKER_VM_CPUS" \
    --memory="$WORKER_VM_MEMORY_GIB" --disk="$WORKER_VM_DISK_GIB" \
    --set=".additionalDisks=[{\"name\":\"$data_disk\",\"format\":true,\"fsType\":\"xfs\"}]" \
    --tty=false "$template"
  limactl start --tty=false "$worker"
fi

mkdir -p "$state_dir/$worker"
report="$state_dir/$worker/vm-capabilities.txt"
say "probing VM $worker capabilities"
if limactl shell --workdir / "$worker" sudo bash -s -- "/mnt/lima-$data_disk" <"$probe" >"$report.tmp" 2>&1; then
  mv "$report.tmp" "$report"
  say "VM $worker has every required capability (report: $report)"
else
  mv "$report.tmp" "$report"
  printf '%s: VM %s is missing required capabilities; the worker container was not started:\n' "$prog" "$worker" >&2
  grep '^MISSING ' "$report" >&2 || cat "$report" >&2
  exit 1
fi

worker_root="/mnt/lima-$data_disk/worker"
if [ -n "$enrollment" ]; then
  limactl shell --workdir / "$worker" sudo mkdir -p -m 0700 "$worker_root/enrollment"
  for f in bootstrap-kubeconfig client-ca.crt; do
    limactl shell --workdir / "$worker" sudo install -m 0600 /dev/stdin "$worker_root/enrollment/$f" <"$enrollment/$f"
  done
  say "enrollment delivered to $worker_root/enrollment in VM $worker"
fi

image="$(grep -v '^#' "$here/image/ref" | head -n 1)"
say "converging worker container $worker in VM $worker"
limactl shell --workdir / "$worker" sudo bash -s -- "$worker" "$host" "$image" "$worker_root" <"$converge"

say "worker $worker converged for host $host"
