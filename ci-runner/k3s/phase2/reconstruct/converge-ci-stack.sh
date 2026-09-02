#!/usr/bin/env bash
# converge-ci-stack.sh — idempotently converge the ENTIRE CI CLUSTER stack
# on the single-node k3s host from this repository, with zero manual
# kubectl/helm steps. One run takes an EMPTY k3s datastore (the GitHub App
# installation secret assumed already present — see the fail-closed pre-gate
# below) to: the ARC controller Running, all ten runner scale-set listeners
# Running, the hook-pod-template ConfigMap converged, and Kueue installed and
# admitting pods against every per-repo queue. A second run against an
# already-converged cluster makes no disruptive change (every operation is a
# `helm upgrade --install` or a `kubectl apply`).
#
# WHY THIS EXISTS: today none of the CI CLUSTER stack re-applies on boot — it
# lives only in the k3s datastore, applied once by hand via provision-k3s.sh
# -> install-arc.sh -> install-kueue.sh plus the phase-2 per-repo scale sets
# and queues. That makes the host a PET: wipe the datastore and the cluster is
# gone. This script is the reconstruct-on-boot converge that makes the host
# CATTLE — a prerequisite for later making the datastore volatile (tmpfs). It
# is wired to boot by ./converge-ci-stack.service (installed by
# ./install-converge-unit.sh), After=k3s.service.
#
# SCOPE BOUNDARY — this converges the CLUSTER stack only:
#   ARC controller + all runner scale sets + the hook-pod-template ConfigMap
#   + Kueue core + every ResourceFlavor/ClusterQueue/LocalQueue.
# It deliberately does NOT own the NODE-LOCAL machinery, each of which has its
# own installer + its own boot-durability story:
#   - the AppArmor profile            (../apparmor/install-apparmor-profile.sh;
#                                       /etc/apparmor.d survives reboot itself)
#   - the inotify sysctl budget       (../node-inotify-budget/)
#   - the churn-slot extended resource (../node-extended-resource/, its own
#                                       reapply timer)
#   - the warm uv cache               (../warm-cache/)
# It also decides NO numbers: the scale-set ceilings live in ../arc/values-*.yaml
# and the queue quotas in ../kueue/cluster-queue-*.yaml. This script only makes
# those ALREADY-DECIDED artifacts durable across a datastore wipe.
#
# It also does NOT create the GitHub App installation secret — a sibling
# work-item (livespec-qqzlek) automates that re-injection; this script
# fail-closes if the secret is absent (step 2), exactly like install-arc.sh.
#
# Pinned chart/manifest versions are co-maintained with their canonical
# installers and README.md "Pinned versions" — keep in lockstep:
#   ARC controller + scale set chart : 0.14.2  (../../install-arc.sh)
#   Kueue                            : v0.19.1 (../../install-kueue.sh)
#
# Requires: kubectl + helm on PATH (both at /usr/local/bin on the live host,
# which is in systemd's default PATH), and KUBECONFIG pointed at the k3s
# cluster (the .service sets KUBECONFIG=/etc/rancher/k3s/k3s.yaml).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Where the arc/ and kueue/ artifact trees live. Resolved so ONE script works
# both from the repo checkout and from the self-contained install location:
#   - CONVERGE_ARTIFACT_DIR env override wins if set.
#   - INSTALLED layout: install-converge-unit.sh copies this script plus the
#     arc/ and kueue/ artifacts into /usr/local/lib/ci-runner-k3s/, so they sit
#     BESIDE this script (${SCRIPT_DIR}/arc, ${SCRIPT_DIR}/kueue).
#   - REPO layout: this file is phase2/reconstruct/converge-ci-stack.sh, so the
#     phase2 artifacts are one level up (${SCRIPT_DIR}/../arc, /../kueue).
# Fail loudly rather than silently converging a partial set from the wrong dir.
if [ -n "${CONVERGE_ARTIFACT_DIR:-}" ]; then
  ARTIFACT_DIR="${CONVERGE_ARTIFACT_DIR}"
elif [ -d "${SCRIPT_DIR}/arc" ] && [ -d "${SCRIPT_DIR}/kueue" ]; then
  ARTIFACT_DIR="${SCRIPT_DIR}"            # installed layout (/usr/local/lib/ci-runner-k3s)
elif [ -d "${SCRIPT_DIR}/../arc" ] && [ -d "${SCRIPT_DIR}/../kueue" ]; then
  ARTIFACT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"   # repo layout (phase2/)
else
  echo "FATAL: cannot locate the arc/ and kueue/ artifact trees relative to ${SCRIPT_DIR}" >&2
  echo "       set CONVERGE_ARTIFACT_DIR to the dir that CONTAINS arc/ and kueue/." >&2
  exit 1
fi
ARC_DIR="${ARTIFACT_DIR}/arc"
KUEUE_DIR="${ARTIFACT_DIR}/kueue"

ARC_CHART_VERSION="0.14.2"   # co-maintained with ../../install-arc.sh + README
KUEUE_VERSION="v0.19.1"      # co-maintained with ../../install-kueue.sh
CONTROLLER_NAMESPACE="arc-systems"
RUNNERS_NAMESPACE="arc-runners"

# Live release -> phase-2 values file. The SINGLE source of truth in this
# script for what gets applied; co-maintained with phase2/README.md
# "Applying a scale set's values" (three names diverge from a plain
# values-<repo>.yaml, all for reasons recorded there). Excludes
# arc/values-EXAMPLE-repo.yaml (a template, not a live release). NOTE the
# phase-1 install-arc.sh step 2 applies `poweredge-xubuntu-k3s` from the
# phase-1 file arc/values-host-unique.yaml; this converge SUPERSEDES that with
# the phase-2 captured file arc/values-poweredge-xubuntu-k3s.yaml for EVERY
# scale set, so it never touches values-host-unique.yaml and never calls
# install-arc.sh step 2.
declare -A SCALE_SETS=(
  [livespec-local-ci-k3s]="values-livespec.yaml"
  [livespec-console-beads-k3s]="values-livespec-console-beads-fabro.yaml"
  [livespec-orchestrator-git-k3s]="values-livespec-orchestrator-git-jsonl.yaml"
  [livespec-dev-tooling-k3s]="values-livespec-dev-tooling.yaml"
  [livespec-driver-claude-k3s]="values-livespec-driver-claude.yaml"
  [livespec-driver-codex-k3s]="values-livespec-driver-codex.yaml"
  [livespec-driver-pi-k3s]="values-livespec-driver-pi.yaml"
  [livespec-overseer-k3s]="values-livespec-overseer.yaml"
  [livespec-runtime-k3s]="values-livespec-runtime.yaml"
  [poweredge-xubuntu-k3s]="values-poweredge-xubuntu-k3s.yaml"
)

log() { printf '\n== %s ==\n' "$*"; }

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
command -v helm >/dev/null || { echo "FATAL: helm not found on PATH"; exit 1; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"

# ---------------------------------------------------------------------------
log "1. Wait for the k3s node to report Ready"
# Copied from ../../provision-k3s.sh step 2. On a fresh boot k3s.service is up
# (Requires=/After= in the unit) but the node may still be registering.
ready=false
for _ in $(seq 1 60); do
  if kubectl get nodes --no-headers 2>/dev/null | grep -q ' Ready'; then
    ready=true
    break
  fi
  sleep 2
done
[ "$ready" = true ] || { echo "FATAL: k3s node did not become Ready within 120s"; exit 1; }
kubectl get nodes -o wide

# ---------------------------------------------------------------------------
log "2. Fail-closed pre-gate: the GitHub App installation secret must already exist"
# Mirrors install-arc.sh step 0. The secret's REQUIRED location is
# RUNNERS_NAMESPACE (arc-runners) — that is where every gha-runner-scale-set
# release resolves its githubConfigSecret. This script NEVER creates it; a
# sibling work-item (livespec-qqzlek) automates the re-injection, and the
# .service takes an After= on that unit once it exists. On a genuinely empty
# datastore arc-runners may not exist yet — `kubectl get secret` reports the
# same not-found either way, which is the correct fail-closed behavior.
if ! kubectl get secret arc-github-app-installation -n "$RUNNERS_NAMESPACE" >/dev/null 2>&1; then
  cat <<EOF
FATAL: secret arc-github-app-installation not found in ${RUNNERS_NAMESPACE}.
Create it from the fleet's least-privilege GitHub App installation token
BEFORE this converge runs (README.md "Credential separation" documents the
exact scope; sibling work-item livespec-qqzlek automates it). This script
never handles or persists that credential itself. If the ${RUNNERS_NAMESPACE}
namespace does not exist yet, create it first:
  kubectl create namespace ${RUNNERS_NAMESPACE}
EOF
  exit 1
fi

# ---------------------------------------------------------------------------
log "3. Install/upgrade the ARC controller (idempotent via helm upgrade --install)"
# Inlined from install-arc.sh step 1 rather than invoked, because install-arc.sh
# is not decomposed into a controller-only entry point and its step 2 applies
# the SUPERSEDED phase-1 values-host-unique.yaml (see the SCALE_SETS note).
helm upgrade --install arc \
  --namespace "$CONTROLLER_NAMESPACE" --create-namespace \
  --version "$ARC_CHART_VERSION" \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller
kubectl -n "$CONTROLLER_NAMESPACE" rollout status deployment \
  -l app.kubernetes.io/name=gha-rs-controller --timeout=120s

# ---------------------------------------------------------------------------
log "4. Install/upgrade all ${#SCALE_SETS[@]} runner scale sets from phase-2 values files"
for release in $(printf '%s\n' "${!SCALE_SETS[@]}" | sort); do
  values_file="${ARC_DIR}/${SCALE_SETS[$release]}"
  [ -f "$values_file" ] || { echo "FATAL: values file not found: ${values_file}"; exit 1; }
  log "4.${release}: helm upgrade --install ${release}"
  helm upgrade --install "$release" \
    --namespace "$RUNNERS_NAMESPACE" --create-namespace \
    --version "$ARC_CHART_VERSION" \
    -f "$values_file" \
    oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set
done

# ---------------------------------------------------------------------------
log "5. Converge the arc-hook-pod-template ConfigMap"
# Reuse the existing idempotent converge (KUBECONFIG-driven, create|apply). It
# reads its sibling hook-pod-template.yaml, so the installer copies both into
# ARC_DIR together.
"${ARC_DIR}/converge-hook-pod-template.sh"

# ---------------------------------------------------------------------------
log "6. Install/upgrade Kueue core (${KUEUE_VERSION})"
# Inlined from install-kueue.sh steps 1 (NOT invoked), because install-kueue.sh
# also applies the PHASE-1 kueue/resources.yaml, whose phase1-proof objects are
# declared at v1beta1. The phase-2 tree carries the SAME objects at v1beta2
# (../kueue/cluster-queue-phase1-proof.yaml), applied in step 7 below, so
# invoking install-kueue.sh would apply them a second time at a second API
# version. This converge uses the phase-2 kueue tree exclusively — mirroring
# how it uses the phase-2 values files rather than phase-1 values-host-unique.
kubectl apply --server-side --force-conflicts -f \
  "https://github.com/kubernetes-sigs/kueue/releases/download/${KUEUE_VERSION}/manifests.yaml"
kubectl -n kueue-system rollout status deployment/kueue-controller-manager --timeout=180s
# The CRDs ship in the same manifest; wait for the ones step 7 applies to be
# Established before applying instances, so a fast boot cannot race them.
kubectl wait --for=condition=established --timeout=60s \
  crd/resourceflavors.kueue.x-k8s.io \
  crd/clusterqueues.kueue.x-k8s.io \
  crd/localqueues.kueue.x-k8s.io

# ---------------------------------------------------------------------------
log "7. Apply all per-repo Kueue resources (ResourceFlavor first, then queues)"
kubectl apply -f "${KUEUE_DIR}/resource-flavor.yaml"
for f in "${KUEUE_DIR}"/cluster-queue-*.yaml; do
  [ -e "$f" ] || { echo "FATAL: no cluster-queue-*.yaml found in ${KUEUE_DIR}"; exit 1; }
  kubectl apply -f "$f"
done

# ---------------------------------------------------------------------------
log "8. Verify (informational — non-fatal reads of the converged state)"
kubectl -n "$CONTROLLER_NAMESPACE" get deployment -l app.kubernetes.io/name=gha-rs-controller
kubectl -n "$RUNNERS_NAMESPACE" get autoscalingrunnersets.actions.github.com
kubectl -n kueue-system get pods
kubectl get clusterqueue

log "DONE. CI cluster stack converged: ARC controller + ${#SCALE_SETS[@]} scale sets + hook ConfigMap + Kueue + all queues."
