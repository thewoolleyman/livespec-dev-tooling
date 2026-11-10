#!/usr/bin/env bash
# prove-ci-installer.sh <host> <image> <installer> — prove a CI tool installer
# installs a working native binary on a joined homelab worker, BEFORE any CI
# queue is opened to that worker for the repository that runs the installer.
#
# One pod pinned to <host>-homelab-worker runs <image> (the repository's own CI
# container image). The local <installer> file is streamed into the pod and run
# as `bash <installer> /tmp/proved-tool`, the target-path convention of the
# fleet's CI installers (for example livespec-orchestrator-beads-fabro's
# dev-tooling/install-ci-fabro.sh). The proof checks:
#   - machine: `uname -m` names the worker's own architecture, so the image is
#     not running under emulation;
#   - installer-runs: the installer exits 0 in the pod;
#   - tool-runs: the installed binary's `--version` exits 0.
# It prints one `PROOF <check> PASS|FAIL <detail>` line per check, and
# PROOF-INFO lines naming the installer's sha256 and the pod's resolved image,
# so a proof record binds the exact bytes a later queue flip exposes. It exits
# non-zero when any check fails. The caller's `kubectl` decides the cluster.
#
# Written for plan homelab-k8s-worker-nodes (livespec-dev-tooling-ko26ez): the
# ordered move of livespec-orchestrator-beads-fabro's CI onto the arm64 worker
# (decision recorded on the epic 2026-11-10 ~11:20Z) needs this host proof
# through a committed route, never a hand-run `kubectl exec`.
#
# This is a proof, not a placement: the pod is pinned by nodeName, tolerates the
# worker's class taint and admission hold, lives in namespace
# hw-ci-installer-proof, and the namespace is deleted at the end unless KEEP=1.
# It writes nothing to the node and enrolls nothing.
set -euo pipefail

prog="prove-ci-installer"
hw="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$hw/hosts}"
ns="hw-ci-installer-proof"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

[ "$#" -eq 3 ] || die "usage: $prog <host> <image> <installer>"
host="$1"
image="$2"
installer="$3"
case "$host" in
  *[!a-z0-9-]* | -*) die "host '$host' is not a valid host name" ;;
esac
[ -f "$hosts_dir/$host.env" ] || die "host '$host' is not declared in homelab-worker/hosts/"
case "$image" in
  *[[:space:]]* | '' | -*) die "image '$image' is not an image reference" ;;
esac
[ -f "$installer" ] && [ -r "$installer" ] || die "installer '$installer' is not a readable file"
worker="$host-homelab-worker"
installer_sha="$(sha256sum "$installer" | cut -d' ' -f1)"

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
  name: installer
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
      command: [sh, -c, "exec sleep 900"]
EOF
kubectl wait --namespace "$ns" --for=condition=Ready pod/installer --timeout="${INSTALLER_READY_TIMEOUT:-600s}" >/dev/null ||
  die "the installer pod did not become Ready on $worker"

printf 'PROOF-INFO installer-sha256 %s\n' "$installer_sha"
printf 'PROOF-INFO image-id %s\n' \
  "$(kubectl get pod --namespace "$ns" installer -o 'jsonpath={.status.containerStatuses[0].imageID}' 2>&1 | tr -d '\r')"

failed=0
result() {
  printf 'PROOF %s %s %s\n' "$1" "$2" "$3"
  [ "$2" = "PASS" ] || failed=1
}
summary() {
  printf '%s' "$1" | tr '\n' ' ' | cut -c1-240
}

if out="$(kubectl exec --namespace "$ns" installer -- sh -c "m=\$(uname -m); echo \$m; [ \"\$m\" = $machine ]" 2>&1)"; then
  result machine PASS "$(summary "$out")"
else
  result machine FAIL "$(summary "$out")"
fi

if out="$(kubectl exec -i --namespace "$ns" installer -- sh -c 'cat > /tmp/proved-installer.sh && bash /tmp/proved-installer.sh /tmp/proved-tool' <"$installer" 2>&1)"; then
  result installer-runs PASS "$(summary "$out")"
  if out="$(kubectl exec --namespace "$ns" installer -- /tmp/proved-tool --version 2>&1)"; then
    result tool-runs PASS "$(summary "$out")"
  else
    result tool-runs FAIL "$(summary "$out")"
  fi
else
  result installer-runs FAIL "$(summary "$out")"
  result tool-runs FAIL "not run: the installer failed"
fi

[ "$failed" -eq 0 ] || die "the CI installer proof FAILED for $installer in $image on $worker"
printf '%s: %s installs a working %s binary in %s on %s\n' "$prog" "$installer" "$machine" "$image" "$worker"
