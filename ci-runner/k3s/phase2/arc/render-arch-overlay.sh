#!/usr/bin/env bash
# render-arch-overlay.sh — render one workload class's architecture selection
# from ../workload-arch.conf (plan homelab-k8s-worker-nodes,
# livespec-dev-tooling-ko26ez.6).
#
# Usage: render-arch-overlay.sh <kind> <name> <dst>
#   kind `release`: <dst> is a helm values overlay that gives the scale set's
#   runner pod a REQUIRED node affinity on kubernetes.io/arch In <arches>.
#   kind `gate` / `factory`: <dst> is the comma-separated arches alone.
#
# A name the list does not declare is refused: a class with no declared
# architecture must not fall back to "anywhere", which is exactly how an
# amd64-only image would land on an arm64 node.
# Env: WORKLOAD_ARCH_CONF overrides the list path (tests).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
conf="${WORKLOAD_ARCH_CONF:-$here/../workload-arch.conf}"
[ "$#" -eq 3 ] || { echo "usage: render-arch-overlay.sh <release|gate|factory> <name> <dst>" >&2; exit 2; }
kind="$1" name="$2" dst="$3"

arches="$(awk -v k="$kind" -v n="$name" '$1 == k && $2 == n { print $3; exit }' "$conf")"
[ -n "$arches" ] || { echo "render-arch-overlay: $kind '$name' is not declared in $conf; declare its architectures there" >&2; exit 1; }

if [ "$kind" != release ]; then
  printf '%s\n' "$arches" >"$dst"
  exit 0
fi
{
  printf 'template:\n  spec:\n    affinity:\n      nodeAffinity:\n'
  printf '        requiredDuringSchedulingIgnoredDuringExecution:\n          nodeSelectorTerms:\n'
  printf '            - matchExpressions:\n                - key: kubernetes.io/arch\n                  operator: In\n                  values:\n'
  printf '%s\n' "$arches" | tr ',' '\n' | sed 's/^/                    - /'
} >"$dst"
