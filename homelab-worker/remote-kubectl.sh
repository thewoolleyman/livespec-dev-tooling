#!/usr/bin/env bash
# remote-kubectl.sh — run the K3s API server node's own kubectl over
# `tailscale ssh`, so a worker host with no kubeconfig can run join-worker.sh
# and prove-worker.sh against production. Two modes:
#
#   remote-kubectl.sh <kubectl args...>   installed as `kubectl` on PATH
#                                         (a symlink named kubectl works)
#   remote-kubectl.sh --shell '<command>' prove-worker.sh's PORT_FORWARD_SHELL:
#                                         runs <command> as root on the node,
#                                         where its kubectl port-forward and the
#                                         fetch from 127.0.0.1 meet
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes". Design: plan/homelab-k8s-worker-nodes/research/008 §5; written after
# the production join of 2026-11-06, where a hand-rolled shim let the remote
# shell re-split jsonpath arguments.
#
# `tailscale ssh` hands its command to the remote login shell as one string,
# so every argument is quoted with printf %q. Standard input passes through.
# `tailscale ssh` checks the node's host key against the tailnet's published
# keys, so no known_hosts entry or kubeconfig is installed on the worker host.
#
# REMOTE_KUBECTL_TARGET (required) is the ssh target, user@node.
# REMOTE_KUBECTL_COMMAND (default `k3s kubectl`) is the node's kubectl.
set -euo pipefail

prog="remote-kubectl"
die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

target="${REMOTE_KUBECTL_TARGET:-}"
[ -n "$target" ] || die "REMOTE_KUBECTL_TARGET is not set; set it to the API server node's ssh target, user@node"
remote_kubectl="${REMOTE_KUBECTL_COMMAND:-k3s kubectl}"

if [ "${1:-}" = "--shell" ]; then
  [ "$#" -eq 2 ] || die "usage: $prog --shell '<command>'"
  exec tailscale ssh "$target" "sudo -n bash -c $(printf '%q' "$2")"
fi
exec tailscale ssh "$target" "sudo -n $remote_kubectl $(printf '%q ' "$@")"
