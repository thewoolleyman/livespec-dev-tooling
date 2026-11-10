#!/usr/bin/env bash
# prove-agent-image.sh <host> <image> — prove a factory agent image runs natively
# on a joined homelab worker: one pod pinned to <host>-homelab-worker runs
# <image>, and the proof checks the four things a factory sandbox needs there
# (livespec-dev-tooling-a3brdf, plan homelab-k8s-worker-nodes research/010):
#   - machine: `uname -m` names the worker's own architecture (aarch64 on an
#     arm64 node, x86_64 on amd64), so the image is not running under emulation;
#   - claude-agent-acp: the Claude ACP adapter is on PATH;
#   - codex-acp: the Codex ACP adapter is baked at /opt/livespec/codex-acp;
#   - bwrap: bubblewrap runs;
#   - claude-cli-runs: the Claude CLI the ACP adapter spawns starts (--version);
#   - pyright-runs: pyright runs as the factory's type gate runs it.
# It also prints the kernel page size as a PROOF-INFO line.
# It prints one `PROOF <check> PASS|FAIL <detail>` line per check and exits
# non-zero when any check fails. The caller's `kubectl` decides the cluster.
#
# This is a proof, not a placement: the pod is pinned by nodeName, tolerates the
# worker's class taint and admission hold, lives in namespace hw-agent-proof,
# and the namespace is deleted at the end unless KEEP=1. It writes nothing to
# the node and enrolls nothing.
set -euo pipefail

prog="prove-agent-image"
hw="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$hw/hosts}"
ns="hw-agent-proof"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

[ "$#" -eq 2 ] || die "usage: $prog <host> <image>"
host="$1"
image="$2"
case "$host" in
  *[!a-z0-9-]* | -*) die "host '$host' is not a valid host name" ;;
esac
[ -f "$hosts_dir/$host.env" ] || die "host '$host' is not declared in homelab-worker/hosts/"
case "$image" in
  *[[:space:]]* | '' | -*) die "image '$image' is not an image reference" ;;
esac
worker="$host-homelab-worker"

arch="$(kubectl get node "$worker" -o 'jsonpath={.metadata.labels.kubernetes\.io/arch}')" ||
  die "could not read Node $worker through kubectl; nothing was created"
case "$arch" in
  arm64) machine=aarch64 ;;
  amd64) machine=x86_64 ;;
  *) die "Node $worker reports architecture '$arch', which this proof does not map to a machine name" ;;
esac

cleanup() {
  if [ "${KEEP:-0}" != "1" ]; then
    kubectl delete namespace "$ns" --wait=false >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

kubectl apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: $ns
---
apiVersion: v1
kind: Pod
metadata:
  name: agent
  namespace: $ns
spec:
  nodeName: $worker
  restartPolicy: Never
  tolerations:
    - key: homelab-worker.livespec.dev/class
      operator: Exists
      effect: NoSchedule
    - key: homelab-worker.livespec.dev/admission
      operator: Exists
      effect: NoSchedule
  containers:
    - name: main
      image: $image
      command: [sh, -c, "exec sleep 600"]
EOF
kubectl wait --namespace "$ns" --for=condition=Ready pod/agent --timeout="${AGENT_READY_TIMEOUT:-600s}" >/dev/null ||
  die "the agent pod did not become Ready on $worker"

failed=0
result() {
  printf 'PROOF %s %s %s\n' "$1" "$2" "$3"
  [ "$2" = "PASS" ] || failed=1
}
# check <name> <shell command run in the pod>: PASS when it exits 0.
check() {
  local out
  if out="$(kubectl exec --namespace "$ns" agent -- sh -c "$2" 2>&1)"; then
    result "$1" PASS "$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-160)"
  else
    result "$1" FAIL "$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-160)"
  fi
}

check machine "m=\$(uname -m); echo \$m; [ \"\$m\" = $machine ]"
check claude-agent-acp "command -v claude-agent-acp"
check codex-acp "ls -d /opt/livespec/codex-acp"
check bwrap "bwrap --version"
# The Claude CLI the ACP adapter spawns for each session, not just the adapter on
# PATH: on the M4's second factory run (2026-11-09, livespec-dev-tooling-ko26ez.9)
# the adapter was present but "The Claude Agent process exited unexpectedly".
check claude-cli-runs "c=\$(find / -path '*claude-agent-sdk-linux-*/claude' -type f 2>/dev/null | head -n 1); [ -n \"\$c\" ] || { echo 'no claude-agent-sdk native CLI'; exit 1; }; \"\$c\" --version"
# pyright as the factory's type gate runs it (pyright-python fetching its node
# package on first use); the same run failed "Cannot find module .../pyright/package.json".
check pyright-runs "cd /tmp && uvx --from pyright==${PYRIGHT_VERSION:-1.1.391} pyright --version"
# Informational, not a check: the kernel's page size, which a Bun-compiled
# binary such as the Claude CLI does not tolerate above 4 KiB.
printf 'PROOF-INFO page-size %s\n' "$(kubectl exec --namespace "$ns" agent -- getconf PAGESIZE 2>&1 | tr -d '\r')"

[ "$failed" -eq 0 ] || die "the agent image proof FAILED for $image on $worker"
printf '%s: %s runs natively on %s (%s) with both ACP adapters and bwrap\n' "$prog" "$image" "$worker" "$machine"
