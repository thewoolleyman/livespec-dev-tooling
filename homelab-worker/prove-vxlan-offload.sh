#!/usr/bin/env bash
# prove-vxlan-offload.sh <host> --peer-node <node> — sweep the NIC offload
# settings of a homelab WORKER node one at a time and time VXLAN-inbound
# throughput under each, so a receive-path offload fault is named by
# measurement rather than by guess.
#
# Written for plan homelab-k8s-worker-nodes (livespec-dev-tooling-ko26ez). On
# 2026-11-11 prove-worker.sh measured the M4 worker at 228 KiB/s for pod-network
# (VXLAN) traffic INTO it against 33.4 MB/s for the same transfer over the
# underlay (node IPs): only VXLAN-encapsulated traffic arriving at the worker VM
# collapses, MTU is ruled out, and peer-to-peer VXLAN between fleet nodes is
# healthy.
#
# SCOPE (binding, legacy-coordinator-agent 2026-11-11): every privileged action
# runs ONLY on a homelab worker node. The tuning pod is placed by nodeSelector
# homelab-worker.livespec.dev/class=worker AND kubernetes.io/hostname=
# <host>-homelab-worker, and the script refuses before creating anything when
# the named Node does not carry homelab-worker.livespec.dev/class=worker. The
# peer side runs only an unprivileged pod-network file server.
#
# THE SWEEP. One privileged hostNetwork pod on the worker (the worker node image,
# which ships ethtool) reads `ethtool -k` for every setting below. Then, for the
# baseline and for each candidate ALONE, a pod-network client on the worker
# times a 32 MiB download from a pod-network server on --peer-node (in-pod, with
# /proc/uptime), printing `PROOF-INFO offload <candidate> <KiB/s> ...`. Each
# candidate is restored to its recorded value before the next one runs, so no
# two toggles are ever stacked. A setting ethtool reports as [fixed] or absent
# is printed `unsupported` and never touched.
#
# RECEIPTS (binding). Every setting the sweep may touch is read BEFORE the run
# and read AGAIN after the final restore, which an EXIT trap performs whatever
# happens. One `PROOF-RECEIPT <iface> <feature> before=<v> after=<v> ok|MISMATCH`
# line is printed per setting; any MISMATCH, or any setting that cannot be read
# back, fails the proof loudly and leaves the tuning pod in place for repair.
#
# Candidates are <iface> <ethtool -K key> <ethtool -k feature name>:
#   lima0 rx rx-checksumming; lima0 gro generic-receive-offload;
#   lima0 rx-udp-gro-forwarding; lima0 rx-gro-list;
#   flannel.1 tx-checksum-ip-generic; flannel.1 gro generic-receive-offload.
# The underlay interface is read from ConfigMap homelab-worker-cluster
# (flannel-iface); OFFLOAD_IFACE overrides it. The caller's `kubectl` decides
# the cluster. Pods live in namespace hw-offload-proof, deleted at the end
# after a clean receipt unless KEEP=1.
set -euo pipefail

prog="prove-vxlan-offload"
hw="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$hw/hosts}"
ns="hw-offload-proof"
busybox="docker.io/library/busybox:1.37.0@sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec"
class_label="homelab-worker.livespec.dev/class"
transfer_kib=32768

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

usage="usage: $prog <host> --peer-node <node>"
[ "$#" -ge 1 ] || die "$usage"
host="$1"
shift
peer=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --peer-node)
      [ "$#" -ge 2 ] || die "--peer-node needs a value; $usage"
      peer="$2"
      shift 2
      ;;
    *) die "unknown argument '$1'; $usage" ;;
  esac
done
case "$host" in
  *[!a-z0-9-]* | -*) die "host '$host' is not a valid host name" ;;
esac
[ -f "$hosts_dir/$host.env" ] || die "host '$host' is not declared in homelab-worker/hosts/"
[ -n "$peer" ] || die "--peer-node is required; $usage"
worker="$host-homelab-worker"
image="$(grep -v '^#' "$hw/image/ref" | sed -n 1p)"
[ -n "$image" ] || die "homelab-worker/image/ref names no image"

class="$(kubectl get node "$worker" -o "jsonpath={.metadata.labels.homelab-worker\.livespec\.dev/class}")" ||
  die "could not read Node $worker through kubectl; nothing was created"
[ "$class" = "worker" ] ||
  die "Node $worker does not carry $class_label=worker; this sweep runs only on homelab worker nodes; nothing was created"
underlay="${OFFLOAD_IFACE:-$(kubectl get configmap --namespace kube-system homelab-worker-cluster -o 'jsonpath={.data.flannel-iface}')}"
[ -n "$underlay" ] || die "no underlay interface: ConfigMap homelab-worker-cluster has no flannel-iface and OFFLOAD_IFACE is unset"

# candidate rows: <iface> <ethtool -K key> <ethtool -k feature>
candidates=(
  "$underlay rx rx-checksumming"
  "$underlay gro generic-receive-offload"
  "$underlay rx-udp-gro-forwarding rx-udp-gro-forwarding"
  "$underlay rx-gro-list rx-gro-list"
  "flannel.1 tx-checksum-ip-generic tx-checksum-ip-generic"
  "flannel.1 gro generic-receive-offload"
)

worker_placement() {
  cat <<EOF
  nodeSelector:
    $class_label: worker
    kubernetes.io/hostname: $worker
  tolerations:
    - key: $class_label
      operator: Exists
      effect: NoSchedule
    - key: homelab-worker.livespec.dev/admission
      operator: Exists
      effect: NoSchedule
EOF
}

server_cmd="mkdir -p /www && dd if=/dev/zero of=/www/huge bs=1024 count=$transfer_kib 2>/dev/null && exec httpd -f -p 8080 -h /www"
# Until the settings are recorded nothing has been toggled, so an early exit
# only removes the pods; the restore-and-receipt trap replaces this below.
early_cleanup() {
  if [ "${KEEP:-0}" != "1" ]; then
    kubectl delete namespace "$ns" --wait=false >/dev/null 2>&1 || true
  fi
}
trap early_cleanup EXIT
{
  printf 'apiVersion: v1\nkind: Namespace\nmetadata:\n  name: %s\n' "$ns"
  cat <<EOF
---
apiVersion: v1
kind: Pod
metadata:
  name: tune
  namespace: $ns
spec:
  hostNetwork: true
$(worker_placement)
  containers:
    - name: main
      image: $image
      command: [sleep, "7200"]
      securityContext:
        privileged: true
---
apiVersion: v1
kind: Pod
metadata:
  name: client
  namespace: $ns
spec:
$(worker_placement)
  containers:
    - name: main
      image: $busybox
      command: [sh, -c, "exec sleep 7200"]
---
apiVersion: v1
kind: Pod
metadata:
  name: server
  namespace: $ns
spec:
  nodeName: $peer
  containers:
    - name: main
      image: $busybox
      command: [sh, -c, "$server_cmd"]
EOF
} | kubectl apply -f - >/dev/null
kubectl wait --namespace "$ns" --for=condition=Ready pod --all --timeout="${OFFLOAD_READY_TIMEOUT:-600s}" >/dev/null ||
  die "the sweep pods did not become Ready"

tune() {
  kubectl exec --namespace "$ns" tune -- "$@"
}

# read_feature <iface> <feature>: prints on, off, fixed or absent.
read_feature() {
  local line
  line="$(tune ethtool -k "$1" 2>/dev/null | grep -E "^[[:space:]]*$2:" | head -n 1 || true)"
  case "$line" in
    "") echo absent ;;
    *"[fixed]"*) echo fixed ;;
    *": on"*) echo on ;;
    *": off"*) echo off ;;
    *) echo absent ;;
  esac
}

declare -A before=()
for row in "${candidates[@]}"; do
  read -r iface _key feature <<<"$row"
  before["$iface $feature"]="$(read_feature "$iface" "$feature")"
  printf 'PROOF-INFO before %s %s %s\n' "$iface" "$feature" "${before["$iface $feature"]}"
done

restore_and_receipt() {
  local rc=$? mismatch=0 row iface key feature want got
  for row in "${candidates[@]}"; do
    read -r iface key feature <<<"$row"
    want="${before["$iface $feature"]}"
    case "$want" in on | off) tune ethtool -K "$iface" "$key" "$want" >/dev/null 2>&1 || true ;; esac
  done
  for row in "${candidates[@]}"; do
    read -r iface key feature <<<"$row"
    want="${before["$iface $feature"]}"
    got="$(read_feature "$iface" "$feature")"
    if [ "$got" = "$want" ]; then
      printf 'PROOF-RECEIPT %s %s before=%s after=%s ok\n' "$iface" "$feature" "$want" "$got"
    else
      printf 'PROOF-RECEIPT %s %s before=%s after=%s MISMATCH\n' "$iface" "$feature" "$want" "$got"
      mismatch=1
    fi
  done
  if [ "$mismatch" -ne 0 ]; then
    printf '%s: RESTORE MISMATCH: an offload setting on %s did not return to its recorded value; the tuning pod hw-offload-proof/tune is LEFT IN PLACE for repair\n' "$prog" "$worker" >&2
    exit 1
  fi
  if [ "${KEEP:-0}" != "1" ]; then
    kubectl delete namespace "$ns" --wait=false >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap restore_and_receipt EXIT

server_ip="$(kubectl get pod --namespace "$ns" server -o 'jsonpath={.status.podIP}')"
[ -n "$server_ip" ] || die "the server pod on $peer has no pod IP"
url="http://$server_ip:8080/huge"

# measure <label>: time the 32 MiB pod-network download into the worker.
measure() {
  local label="$1" out start end extra
  if out="$(kubectl exec --namespace "$ns" client -- sh -c \
    "a=\$(cut -d' ' -f1 /proc/uptime); wget -qO /dev/null -T 600 '$url' || exit 1; b=\$(cut -d' ' -f1 /proc/uptime); echo \"\$a \$b\"" 2>&1)" &&
    read -r start end extra <<<"$out" && [ -n "$end" ] && [ -z "$extra" ]; then
    awk -v a="$start" -v b="$end" -v kib="$transfer_kib" -v l="$label" 'BEGIN {
      s = b - a; if (s <= 0) s = 0.01
      printf "PROOF-INFO offload %s %d KiB/s (%d KiB in %.2f s)\n", l, kib / s, kib, s }'
  else
    printf 'PROOF-INFO offload %s unmeasured %s\n' "$label" "$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-120)"
  fi
}

measure baseline
for row in "${candidates[@]}"; do
  read -r iface key feature <<<"$row"
  label="$iface:$key=off"
  was="${before["$iface $feature"]}"
  case "$was" in
    on) ;;
    off)
      printf 'PROOF-INFO offload %s already-off\n' "$label"
      continue
      ;;
    *)
      printf 'PROOF-INFO offload %s unsupported (%s)\n' "$label" "$was"
      continue
      ;;
  esac
  tune ethtool -K "$iface" "$key" off >/dev/null 2>&1 || {
    printf 'PROOF-INFO offload %s unsupported (ethtool -K refused)\n' "$label"
    continue
  }
  measure "$label"
  tune ethtool -K "$iface" "$key" on >/dev/null 2>&1 || true
done
printf '%s: sweep complete on %s against %s\n' "$prog" "$worker" "$peer"
