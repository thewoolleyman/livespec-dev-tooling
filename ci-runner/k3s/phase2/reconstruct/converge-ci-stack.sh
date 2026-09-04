#!/usr/bin/env bash
# converge-ci-stack.sh — idempotently converge the ENTIRE CI CLUSTER stack
# on the single-node k3s host from this repository, with zero manual
# kubectl/helm steps. One run takes an EMPTY k3s datastore (the GitHub App
# installation secret assumed already present — see the fail-closed pre-gate
# below) to: the fleet-owned local-path provisioner Running, Kueue installed
# and its admission webhook SERVING, every per-repo queue applied, the ARC
# controller Running, all ten runner scale-set listeners Running, the
# hook-pod-template ConfigMap converged, the warm-cache CronJob present, and
# the Kueue-webhook probe's host credential re-rendered. A second run against
# an already-converged cluster makes no disruptive change (every operation is
# a `helm upgrade --install` or a `kubectl apply`).
#
# WHY THIS EXISTS: the k3s datastore is tmpfs (../datastore-tmpfs/), EMPTY on
# every boot, so the host is CATTLE only because this converge rebuilds the
# cluster from git on every boot. It is wired to boot by
# ./converge-ci-stack.service (installed by ./install-converge-unit.sh),
# After=k3s.service, After=/Wants= reapply-node-extended-resource.service
# and After=/Wants= inject-github-app-secret.service.
#
# ORDER MATTERS, and the order below was corrected against the first real
# reboot (2026-09-02 12:14Z, livespec plan ci-runner-pod-lifecycle-reliability):
#   - The churn-slot capacity assertion (step 1b) comes as soon as the node
#     is Ready, before any cluster object: every queue applied below is
#     denominated in ci-runner.io/churn-slot, and the 2026-09-04 boot showed
#     the node can reach this converge carrying none (item livespec-kgl3).
#   - The local-path provisioner comes FIRST among the cluster objects
#     because the bundled k3s copy is disabled (../k3s-config/) and every
#     runner pod needs a PVC from it.
#   - Kueue comes BEFORE ARC, and the converge WAITS for Kueue's mutating
#     webhook (`mpod.kb.io`, failurePolicy Fail, intercepting every pod
#     outside kube-system/kueue-system) to have a ready endpoint. On that
#     first reboot ARC was applied first: every listener-pod create failed
#     `no endpoints available for service "kueue-webhook-service"` for ~80 s
#     until Kueue was Ready, and only ARC's own retry backoff recovered it.
#     Once the webhook configuration exists, NO pod can be created until its
#     server answers, so the server must be up before anything creates pods.
#   - Warm-cache and the probe identity come LAST: they depend on nothing
#     above but nothing depends on them, so a failure there cannot hold up
#     the runners.
#
# SCOPE BOUNDARY — this converges CLUSTER-side state (everything that lives
# in the datastore) plus the ONE host file derived from it (the probe
# kubeconfig). It deliberately does NOT own the NODE-LOCAL machinery, each of
# which has its own installer and its own boot-durability story:
#   - the AppArmor profile            (../apparmor/install-apparmor-profile.sh;
#                                       /etc/apparmor.d survives reboot itself)
#   - the inotify sysctl budget       (../node-inotify-budget/)
#   - the churn-slot extended resource (../node-extended-resource/, its own
#                                       reapply unit + timer; step 1b ASSERTS
#                                       it is present at that unit's capacity
#                                       and re-runs the patch when not, but
#                                       decides no number)
#   - the k3s server config           (../k3s-config/)
#   - the orphaned-scratch sweep      (../storage-sweep/, Before=k3s)
#   - the host OTel collector's own cluster identity (the otel-collector
#     repository's otel-collector-identity.service)
# It also decides NO numbers: the scale-set ceilings live in ../arc/values-*.yaml,
# the queue quotas in ../kueue/cluster-queue-*.yaml, the provisioner tuning in
# ../local-path-provisioner/local-path-provisioner.yaml. This script only makes
# those ALREADY-DECIDED artifacts durable across a datastore wipe.
#
# It also does NOT create the GitHub App installation secret —
# ../../secret-reinjection/ re-injects it on boot; this script fail-closes if
# the secret is absent (step 2), exactly like install-arc.sh.
#
# Pinned chart/manifest versions are co-maintained with their canonical
# installers and README.md "Pinned versions" — keep in lockstep:
#   ARC controller + scale set chart : 0.14.2  (../../install-arc.sh)
#   Kueue                            : v0.19.1 (../../install-kueue.sh, and the
#                                       release URL pinned in
#                                       ../kueue/core/kustomization.yaml — step 4
#                                       asserts it agrees with KUEUE_VERSION)
#
# Requires: kubectl + helm on PATH (both at /usr/local/bin on the live host,
# which is in systemd's default PATH), and KUBECONFIG pointed at the k3s
# cluster (the .service sets KUBECONFIG=/etc/rancher/k3s/k3s.yaml). Runs as
# root (it writes the probe kubeconfig under /etc/ci-runner).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Where the applied artifact trees live. Resolved so ONE script works both
# from the repo checkout and from the self-contained install location:
#   - CONVERGE_ARTIFACT_DIR env override wins if set.
#   - INSTALLED layout: install-converge-unit.sh copies this script plus the
#     arc/, kueue/, local-path-provisioner/, warm-cache/ and observability/
#     artifacts into /usr/local/lib/ci-runner-k3s/, so they sit BESIDE this
#     script.
#   - REPO layout: this file is phase2/reconstruct/converge-ci-stack.sh, so the
#     phase2 artifacts are one level up, and observability/ is at
#     ci-runner/observability (../../../observability from here).
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
PROVISIONER_DIR="${ARTIFACT_DIR}/local-path-provisioner"
WARM_CACHE_DIR="${ARTIFACT_DIR}/warm-cache"
CRATES_PROXY_DIR="${ARTIFACT_DIR}/crates-proxy"
SCCACHE_DIR="${ARTIFACT_DIR}/sccache"
if [ -d "${ARTIFACT_DIR}/observability" ]; then
  OBSERVABILITY_DIR="${ARTIFACT_DIR}/observability"          # installed layout
else
  OBSERVABILITY_DIR="$(cd "${ARTIFACT_DIR}/../../observability" && pwd)"   # repo layout
fi
RENDER_SA_KUBECONFIG="${SCRIPT_DIR}/render-sa-kubeconfig.sh"
for d in "$ARC_DIR" "$KUEUE_DIR" "$PROVISIONER_DIR" "$WARM_CACHE_DIR" "$OBSERVABILITY_DIR"; do
  [ -d "$d" ] || { echo "FATAL: artifact dir not found: ${d}" >&2; exit 1; }
done
[ -x "$RENDER_SA_KUBECONFIG" ] || { echo "FATAL: ${RENDER_SA_KUBECONFIG} not found or not executable" >&2; exit 1; }

ARC_CHART_VERSION="0.14.2"   # co-maintained with ../../install-arc.sh + README
KUEUE_VERSION="v0.19.1"      # co-maintained with ../../install-kueue.sh
CONTROLLER_NAMESPACE="arc-systems"
RUNNERS_NAMESPACE="arc-runners"
PROBE_KUBECONFIG="${CI_KUEUE_PROBE_KUBECONFIG:-/etc/ci-runner/kueue-webhook-probe.kubeconfig}"

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
log "1. Wait for the API server and the k3s node to report Ready"
# k3s.service being active does not mean the API is serving yet. Poll the
# readiness endpoint, then the node condition (copied from provision-k3s.sh).
api_ready=false
for _ in $(seq 1 60); do
  if kubectl get --raw /readyz >/dev/null 2>&1; then
    api_ready=true
    break
  fi
  sleep 2
done
[ "$api_ready" = true ] || { echo "FATAL: API server did not answer /readyz within 120s"; exit 1; }
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
log "1b. Assert the node carries ci-runner.io/churn-slot at the installed reapply unit's capacity (self-healing)"
# WHY: every ClusterQueue applied in step 5 is denominated in this extended
# resource, and the resource is NOT kubelet-owned — it is a node-status patch
# that only ../node-extended-resource/ puts back (the reapply unit, ordered
# Before= this converge, and its 5-minute timer). On the 2026-09-04 06:31Z
# boot stale NVMe lines in /etc/fstab failed k3s's mount dependency, so EVERY
# After=k3s oneshot — the reapply unit included — failed by dependency. An
# operator then hand-started k3s and this converge, but not the reapply unit,
# and the timer's OnUnitActiveSec re-arms only from a SUCCESSFUL activation,
# so it had no next elapse either. The node carried NO churn-slot capacity
# while the nine queues advertised a quota sum of 32: every runner pod Kueue
# admitted would have been unschedulable, silently — no capacity signal and
# no sweep class said so — until a hand `systemctl start
# reapply-node-extended-resource.service` at 07:52Z (item livespec-kgl3).
#
# THE ASSERTION: every node the reapply targets (NODE_LABEL_SELECTOR — the
# label patch-node-churn-capacity.sh patches and kueue/resource-flavor.yaml
# selects) must report status.allocatable ci-runner.io/churn-slot equal to
# CAPACITY, where CAPACITY is the argument the INSTALLED reapply unit carries
# in its ExecStart — the one already-decided number on this host
# (install-reapply-unit.sh substitutes it in), read back through `systemctl
# show` so this converge decides no number of its own and no second copy
# exists to drift. CONVERGE_CHURN_CAPACITY overrides it for a run outside the
# installed layout.
#
# THE SELF-HEAL: re-run patch-node-churn-capacity.sh CAPACITY (idempotent —
# it is the reapply unit's own ExecStart target) and re-read. A node that is
# STILL wrong afterwards is reported as a WARN and the converge CONTINUES —
# the rule step 7b already applies, and it binds harder here: failing at 1b
# would skip the provisioner, Kueue, the queues, ARC and everything after
# them, so when the timer's OnCalendar fallback or an operator DID restore
# the capacity there would be no cluster stack for it to serve; continuing
# leaves a fully built stack that admits and schedules the instant the
# capacity lands. ../runner-pod-lifecycle/ reports the condition as
# capacity-absent every five minutes either way.
#
# The `churn-slot capacity: N/N node(s) at C (M self-healed)` line printed at
# the end is this step's boot-proof evidence.
NODE_LABEL_SELECTOR="k3s-role=arc-runner-host"   # matches patch-node-churn-capacity.sh and kueue/resource-flavor.yaml
REAPPLY_UNIT="reapply-node-extended-resource.service"
# The patch script sits beside this converge in the installed layout
# (install-reapply-unit.sh copies it into the same /usr/local/lib/ci-runner-k3s)
# and one directory over in the repo layout.
if [ -x "${SCRIPT_DIR}/patch-node-churn-capacity.sh" ]; then
  PATCH_CAPACITY="${SCRIPT_DIR}/patch-node-churn-capacity.sh"
else
  PATCH_CAPACITY="${ARTIFACT_DIR}/node-extended-resource/patch-node-churn-capacity.sh"
fi
# CAPACITY: the env override, else the installed unit's ExecStart argument
# (`systemctl show` renders it as `argv[]=<script> <CAPACITY> ;`).
capacity="${CONVERGE_CHURN_CAPACITY:-}"
if [ -z "$capacity" ] && command -v systemctl >/dev/null; then
  capacity="$(systemctl show "$REAPPLY_UNIT" -p ExecStart --value 2>/dev/null \
    | sed -n 's/.*argv\[\]=\([^;]*\) ;.*/\1/p' | tail -n1 | awk '{print $NF}')"
fi
# One line per targeted node: `<node>|<allocatable churn-slot, or empty>`.
churn_allocatable() {
  kubectl get nodes -l "$NODE_LABEL_SELECTOR" \
    -o jsonpath='{range .items[*]}{.metadata.name}{"|"}{.status.allocatable.ci-runner\.io/churn-slot}{"\n"}{end}' 2>/dev/null
}
# Prints one indented line per node (ok / MISSING / MISMATCH) followed by a
# final `WRONG:<n>` line counting the nodes that are not at CAPACITY.
check_capacity() {
  local wrong=0 node have
  while IFS='|' read -r node have; do
    [ -n "$node" ] || continue
    if [ -z "$have" ]; then
      printf '  %-32s MISSING (expected %s)\n' "$node" "$capacity"; wrong=$((wrong+1))
    elif [ "$have" != "$capacity" ]; then
      printf '  %-32s MISMATCH %s (expected %s)\n' "$node" "$have" "$capacity"; wrong=$((wrong+1))
    else
      printf '  %-32s ok (%s)\n' "$node" "$have"
    fi
  done < <(churn_allocatable)
  printf 'WRONG:%s\n' "$wrong"
}
if ! [[ "$capacity" =~ ^[0-9]+$ ]]; then
  echo "WARN: cannot learn the intended ci-runner.io/churn-slot capacity -- ${REAPPLY_UNIT} is not installed with a numeric ExecStart argument and CONVERGE_CHURN_CAPACITY is unset; skipping the assertion. The queues applied in step 5 are denominated in this resource; install the unit with node-extended-resource/install-reapply-unit.sh CAPACITY (../runner-pod-lifecycle/ reports capacity-absent every 5 min until the resource is present)"
else
  report="$(check_capacity)"
  node_count="$(printf '%s\n' "$report" | grep -cE '^  ' || true)"
  wrong="$(printf '%s\n' "$report" | sed -n 's/^WRONG://p')"
  healed=0
  if [ "$node_count" -eq 0 ]; then
    echo "WARN: no node matches ${NODE_LABEL_SELECTOR} -- nothing carries ci-runner.io/churn-slot and the ResourceFlavor selects no node; check the k3s --node-label (../../provision-k3s.sh)"
  elif [ "$wrong" -gt 0 ]; then
    # Log what was wrong before healing it, so the journal says WHAT, not
    # only that something was healed.
    printf '%s\n' "$report" | grep -v '^WRONG:' || true
    if [ -x "$PATCH_CAPACITY" ]; then
      echo "  self-heal: re-running ${PATCH_CAPACITY} ${capacity} (the ${REAPPLY_UNIT} ExecStart)"
      "$PATCH_CAPACITY" "$capacity" || echo "  self-heal: patch exited $? -- re-checking anyway"
      healed=1
      report="$(check_capacity)"
      wrong="$(printf '%s\n' "$report" | sed -n 's/^WRONG://p')"
    else
      echo "  self-heal: ${PATCH_CAPACITY} not found or not executable -- cannot re-apply; install it with node-extended-resource/install-reapply-unit.sh ${capacity}"
    fi
  fi
  if [ "$node_count" -gt 0 ]; then
    printf '%s\n' "$report" | grep -v '^WRONG:' || true
    ok_nodes="$(printf '%s\n' "$report" | grep -c ' ok (' || true)"
    if [ "$wrong" -eq 0 ]; then
      echo "churn-slot capacity: ${ok_nodes}/${node_count} node(s) at ${capacity} (${healed} self-healed)"
    else
      echo "WARN: churn-slot capacity: ${ok_nodes}/${node_count} node(s) at ${capacity} after ${healed} self-heal(s) -- every runner pod Kueue admits is unschedulable until this is fixed; the reapply timer re-tries every 5 min and ../runner-pod-lifecycle/ reports it as capacity-absent. By hand: systemctl start ${REAPPLY_UNIT}"
    fi
  fi
fi

# ---------------------------------------------------------------------------
log "2. Fail-closed pre-gate: the GitHub App installation secret must already exist"
# Mirrors install-arc.sh step 0. The secret's REQUIRED location is
# RUNNERS_NAMESPACE (arc-runners) — that is where every gha-runner-scale-set
# release resolves its githubConfigSecret. This script NEVER creates it;
# ../../secret-reinjection/ re-injects it on boot and the .service orders
# after that unit. On a genuinely empty datastore arc-runners may not exist
# yet — `kubectl get secret` reports the same not-found either way, which is
# the correct fail-closed behavior.
if ! kubectl get secret arc-github-app-installation -n "$RUNNERS_NAMESPACE" >/dev/null 2>&1; then
  cat <<EOF
FATAL: secret arc-github-app-installation not found in ${RUNNERS_NAMESPACE}.
Create it from the fleet's least-privilege GitHub App installation token
BEFORE this converge runs (README.md "Credential separation" documents the
exact scope; ../../secret-reinjection/ automates it at boot). This script
never handles or persists that credential itself. If the ${RUNNERS_NAMESPACE}
namespace does not exist yet, create it first:
  kubectl create namespace ${RUNNERS_NAMESPACE}
EOF
  exit 1
fi

# ---------------------------------------------------------------------------
log "3. Apply the fleet-owned local-path provisioner (the bundled copy is disabled)"
# ../k3s-config/ disables k3s's packaged local-storage component, so without
# this step no PVC on the node can bind. Applied before anything that creates
# pods. The manifest is the bundled one plus the pool's tuning; see its header.
kubectl apply -f "${PROVISIONER_DIR}/local-path-provisioner.yaml"
kubectl -n kube-system rollout status deployment/local-path-provisioner --timeout=120s

# ---------------------------------------------------------------------------
log "4. Install/upgrade Kueue core (${KUEUE_VERSION}) with the fleet HA overlay, and wait for its webhook to serve"
# Inlined from install-kueue.sh step 1 (NOT invoked), because install-kueue.sh
# also applies the PHASE-1 kueue/resources.yaml, whose phase1-proof objects are
# declared at v1beta1. The phase-2 tree carries the SAME objects at v1beta2
# (../kueue/cluster-queue-phase1-proof.yaml), applied in step 5 below, so
# invoking install-kueue.sh would apply them a second time at a second API
# version. This converge uses the phase-2 kueue tree exclusively — mirroring
# how it uses the phase-2 values files rather than phase-1 values-host-unique.
#
# Applied as ONE kustomize overlay (../kueue/core/: the upstream release
# manifest plus the fleet's HA patches — two replicas, probe timeouts,
# leader-election tolerances; each patch file carries its why). One apply of
# the MERGED set, rather than upstream-then-patch, is what keeps a warm converge
# a no-op: two applies would flip the ConfigMap back and forth on every run.
# The overlay pins the release URL itself; assert it agrees with KUEUE_VERSION
# so the two cannot drift apart silently.
KUEUE_CORE_DIR="${KUEUE_DIR}/core"
grep -q "kueue/releases/download/${KUEUE_VERSION}/manifests.yaml" "${KUEUE_CORE_DIR}/kustomization.yaml" \
  || { echo "FATAL: ${KUEUE_CORE_DIR}/kustomization.yaml does not pin ${KUEUE_VERSION}; bump KUEUE_VERSION and the overlay together" >&2; exit 1; }
# The manager reads its ConfigMap once, at start, so a CHANGED config needs a
# rollout — but an UNCHANGED one must not restart anything (warm converge is a
# no-op), and a boot from an empty datastore needs no restart either (the
# Deployment is created against the new ConfigMap). Detect change by CONTENT,
# before vs after the apply, not by resourceVersion.
cm_hash() {
  kubectl -n kueue-system get configmap kueue-manager-config \
    -o jsonpath='{.data.controller_manager_config\.yaml}' 2>/dev/null | sha256sum | cut -d' ' -f1
}
cm_existed=false
cm_before=""
if kubectl -n kueue-system get configmap kueue-manager-config >/dev/null 2>&1; then
  cm_existed=true
  cm_before="$(cm_hash)"
fi
kubectl apply --server-side --force-conflicts -k "${KUEUE_CORE_DIR}"
if [ "$cm_existed" = true ] && [ "$(cm_hash)" != "$cm_before" ]; then
  echo "kueue-manager-config changed; rolling the manager so it re-reads its config"
  kubectl -n kueue-system rollout restart deployment/kueue-controller-manager
fi
kubectl -n kueue-system rollout status deployment/kueue-controller-manager --timeout=180s
# The CRDs ship in the same manifest; wait for the ones step 5 applies to be
# Established before applying instances, so a fast boot cannot race them.
kubectl wait --for=condition=established --timeout=60s \
  crd/resourceflavors.kueue.x-k8s.io \
  crd/clusterqueues.kueue.x-k8s.io \
  crd/localqueues.kueue.x-k8s.io
# The mutating webhook's Service must have a READY endpoint before any step
# creates a pod outside kube-system/kueue-system, or that create fails
# `no endpoints available for service "kueue-webhook-service"` (seen live
# for ~80 s on the 2026-09-02 reboot when ARC preceded Kueue). Rollout
# status above says the pod is Ready; this confirms the Service sees it.
webhook_ready=false
for _ in $(seq 1 60); do
  ready_addrs="$(kubectl -n kueue-system get endpointslices \
    -l kubernetes.io/service-name=kueue-webhook-service \
    -o jsonpath='{range .items[*]}{range .endpoints[?(@.conditions.ready==true)]}{.addresses[*]}{" "}{end}{end}' 2>/dev/null || true)"
  if [ -n "${ready_addrs// /}" ]; then
    webhook_ready=true
    echo "kueue-webhook-service ready endpoints: ${ready_addrs}"
    break
  fi
  sleep 2
done
[ "$webhook_ready" = true ] || { echo "FATAL: kueue-webhook-service had no ready endpoint within 120s"; exit 1; }

# ---------------------------------------------------------------------------
log "5. Apply all per-repo Kueue resources (ResourceFlavor first, then queues)"
kubectl apply -f "${KUEUE_DIR}/resource-flavor.yaml"
for f in "${KUEUE_DIR}"/cluster-queue-*.yaml; do
  [ -e "$f" ] || { echo "FATAL: no cluster-queue-*.yaml found in ${KUEUE_DIR}"; exit 1; }
  kubectl apply -f "$f"
done

# ---------------------------------------------------------------------------
log "6. Install/upgrade the ARC controller (idempotent via helm upgrade --install)"
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
log "7. Install/upgrade all ${#SCALE_SETS[@]} runner scale sets from phase-2 values files"
for release in $(printf '%s\n' "${!SCALE_SETS[@]}" | sort); do
  values_file="${ARC_DIR}/${SCALE_SETS[$release]}"
  [ -f "$values_file" ] || { echo "FATAL: values file not found: ${values_file}"; exit 1; }
  log "7.${release}: helm upgrade --install ${release}"
  helm upgrade --install "$release" \
    --namespace "$RUNNERS_NAMESPACE" --create-namespace \
    --version "$ARC_CHART_VERSION" \
    -f "$values_file" \
    oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set
done

# ---------------------------------------------------------------------------
log "7b. Assert every scale-set listener references its scale set's CURRENT EphemeralRunnerSet (self-healing)"
# WHY: ARC 0.14.2 can create two EphemeralRunnerSets for one scale set within
# seconds of the helm apply — a transient one, then the live one — and a
# listener created in that window captures the TRANSIENT name. Nothing
# corrects it: the AutoscalingListener carries no ownerReference to the set
# and only patches it when it must scale. So the listener pod shows Running
# and an "N listeners Running" checklist passes, while the FIRST job assigned
# to that repository makes the listener fail `could not patch ephemeral
# runner set ... not found`, exit, and crash-loop — that repository's jobs
# queue forever with every capacity signal healthy. Seen live on the
# 2026-09-02 boot 5 (livespec-overseer, 31 minutes; livespec plan
# ci-runner-pod-lifecycle-reliability, item livespec-bde2). Boots 2-4 simply
# did not lose the race, which is why a passing checklist proved nothing.
#
# THE ASSERTION: for every AutoscalingListener, spec.ephemeralRunnerSetName
# must equal the CURRENT set of its scale set — the EphemeralRunnerSet owned
# by that AutoscalingRunnerSet, not being deleted, newest by creation time.
# A mere "the referenced set exists" test would miss a listener pointing at
# a superseded set that has not been deleted yet.
#
# THE SELF-HEAL: delete the stale AutoscalingListener; the ARC controller
# recreates it against the live set within ~30 s (the hand remedy applied on
# 2026-09-02 15:50Z). Then re-verify. A listener that is STILL inconsistent
# after that is reported as a WARN and the converge CONTINUES — failing here
# would skip the hook ConfigMap, warm cache and probe identity that every job
# depends on, and the runner-pod-lifecycle sweep (../runner-pod-lifecycle/)
# reports the class every five minutes anyway.
#
# The `listener->EphemeralRunnerSet: N/N consistent` line printed at the end
# is this step's boot-proof evidence; "N listeners Running" is not (README
# "Reconstruct-on-boot").

# One line per scale set: `<AutoscalingRunnerSet>|<its current EphemeralRunnerSet>`.
current_sets() {
  kubectl -n "$RUNNERS_NAMESPACE" get ephemeralrunnerset \
    -o jsonpath='{range .items[*]}{.metadata.ownerReferences[0].name}{"|"}{.metadata.name}{"|"}{.metadata.creationTimestamp}{"|"}{.metadata.deletionTimestamp}{"\n"}{end}' 2>/dev/null \
    | awk -F'|' '$1 != "" && $4 == ""' \
    | sort -t'|' -k1,1 -k3,3r \
    | awk -F'|' '!seen[$1]++ {print $1 "|" $2}'
}
# One line per listener: `<AutoscalingListener>|<its AutoscalingRunnerSet>|<referenced EphemeralRunnerSet>`.
listeners() {
  kubectl -n "$CONTROLLER_NAMESPACE" get autoscalinglistener \
    -o jsonpath='{range .items[*]}{.metadata.name}{"|"}{.spec.autoscalingRunnerSetName}{"|"}{.spec.ephemeralRunnerSetName}{"\n"}{end}' 2>/dev/null
}
# Prints one indented line per listener (ok / STALE / PENDING) followed by a
# final `STALE:<a>,<b>` line naming the stale ones. A listener is PENDING when
# its scale set has no live EphemeralRunnerSet yet (the controller is still
# reconciling) — waited for, never healed.
check_listeners() {
  local sets lst stale="" name ars ref cur
  sets="$(current_sets)"
  lst="$(listeners)"
  while IFS='|' read -r name ars ref; do
    [ -n "$name" ] || continue
    cur="$(printf '%s\n' "$sets" | awk -F'|' -v a="$ars" '$1 == a {print $2; exit}')"
    if [ -z "$cur" ]; then
      printf '  %-48s PENDING (no live EphemeralRunnerSet for %s yet)\n' "$name" "$ars"
    elif [ "$ref" = "$cur" ]; then
      printf '  %-48s ok (%s)\n' "$name" "$ref"
    else
      printf '  %-48s STALE -> %s (current for %s: %s)\n' "$name" "${ref:-<empty>}" "$ars" "$cur"
      stale="${stale}${name},"
    fi
  done <<< "$lst"
  printf 'STALE:%s\n' "${stale%,}"
}

# Listeners are created asynchronously by the controller after the helm
# applies (on a boot from empty they appear within ~35 s), and a deleted one
# takes ~30 s to come back — so the check is polled, bounded to 150 s, and
# counts as done only when EVERY scale set has a listener and none is stale
# or pending. Each stale listener is deleted at most once.
expected_listeners="$(kubectl -n "$RUNNERS_NAMESPACE" get autoscalingrunnerset -o name 2>/dev/null | grep -c . || true)"
healed_names=","
healed_count=0
listeners_consistent=false
report=""
for _ in $(seq 1 75); do
  report="$(check_listeners)"
  present="$(printf '%s\n' "$report" | grep -cE '^  ' || true)"
  pending="$(printf '%s\n' "$report" | grep -c ' PENDING ' || true)"
  stale_csv="$(printf '%s\n' "$report" | sed -n 's/^STALE://p')"
  if [ "$present" -ge "$expected_listeners" ] && [ "$pending" -eq 0 ] && [ -z "$stale_csv" ]; then
    listeners_consistent=true
    break
  fi
  IFS=',' read -ra stale_list <<< "$stale_csv"
  for name in "${stale_list[@]}"; do
    [ -n "$name" ] || continue
    case "$healed_names" in *",${name},"*) continue ;; esac
    # Log the stale reference itself before it is destroyed, so the journal
    # says WHAT was wrong, not only that something was healed.
    printf '%s\n' "$report" | grep -F "  ${name} " || true
    echo "  self-heal: deleting stale AutoscalingListener ${name}; the controller recreates it against the live set"
    kubectl -n "$CONTROLLER_NAMESPACE" delete autoscalinglistener "$name" --wait=false || true
    healed_names="${healed_names}${name},"
    healed_count=$((healed_count+1))
  done
  sleep 2
done
printf '%s\n' "$report" | grep -v '^STALE:' || true
ok_count="$(printf '%s\n' "$report" | grep -c ' ok (' || true)"
if [ "$listeners_consistent" = true ]; then
  echo "listener->EphemeralRunnerSet: ${ok_count}/${expected_listeners} consistent (${healed_count} self-healed)"
else
  echo "WARN: listener->EphemeralRunnerSet: ${ok_count}/${expected_listeners} consistent after ${healed_count} self-heal(s) and 150 s -- a scale set may be unable to dispatch; the runner-pod-lifecycle sweep reports it as stale-listener every 5 min. By hand: kubectl -n ${CONTROLLER_NAMESPACE} delete autoscalinglistener <name>"
fi

# ---------------------------------------------------------------------------
log "8. Converge the arc-hook-pod-template ConfigMap"
# Reuse the existing idempotent converge (KUBECONFIG-driven, create|apply). It
# reads its sibling hook-pod-template.yaml, so the installer copies both into
# ARC_DIR together.
"${ARC_DIR}/converge-hook-pod-template.sh"

# ---------------------------------------------------------------------------
log "8b. Converge the crates proxy (Namespace, nginx ConfigMap, Deployment, Service)"
# Before the warm cache: its populator pre-warms this proxy. Bounded wait
# inside; a proxy not yet Ready only means jobs fetch from crates.io directly
# until it is (the hook template's postStart probes before opting in).
"${CRATES_PROXY_DIR}/converge-crates-proxy.sh"

# ---------------------------------------------------------------------------
log "8c. Converge the shared compilation cache (writer credential, ACL Secret, redis Deployment, Service)"
# Also before the warm cache: its populator is the cache's one writer and
# reads the credential Secret this converge projects into ci-warm-cache. The
# cache is RAM-resident and empty after a boot; the next populate refills it.
"${SCCACHE_DIR}/converge-sccache-redis.sh"

# ---------------------------------------------------------------------------
log "9. Converge the warm uv cache's cluster objects (Namespace, CronJob, ConfigMaps)"
# No populate Job here: the on-disk lower survives a reboot and the CronJob
# refreshes it on its schedule. install-warm-cache.sh is the attended path
# that also runs one populate immediately.
WARM_CACHE_VALUES_DIR="${ARC_DIR}" "${WARM_CACHE_DIR}/converge-warm-cache.sh"

# ---------------------------------------------------------------------------
log "10. Re-apply the Kueue-webhook probe's cluster identity and re-render its kubeconfig"
# The probe (../../observability/ci-kueue-webhook-probe.sh) authenticates
# with a ServiceAccount token; the account lives in the datastore and is
# wiped on every boot. Re-create it from the committed RBAC and re-render
# the host-side kubeconfig it reads (root-only; the probe runs as root).
kubectl apply -f "${OBSERVABILITY_DIR}/kueue-webhook-probe-rbac.yaml"
"${RENDER_SA_KUBECONFIG}" \
  --namespace kueue-system \
  --secret kueue-webhook-probe-token \
  --user kueue-webhook-probe \
  --dest "${PROBE_KUBECONFIG}" \
  --group root --mode 0600

# ---------------------------------------------------------------------------
log "11. Verify (informational — non-fatal reads of the converged state)"
kubectl -n kube-system get deployment local-path-provisioner
kubectl -n "$CONTROLLER_NAMESPACE" get deployment -l app.kubernetes.io/name=gha-rs-controller
kubectl -n "$RUNNERS_NAMESPACE" get autoscalingrunnersets.actions.github.com
kubectl -n kueue-system get pods
kubectl get clusterqueue
kubectl -n ci-warm-cache get cronjob
kubectl get nodes -l "$NODE_LABEL_SELECTOR" \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}ci-runner.io/churn-slot={.status.allocatable.ci-runner\.io/churn-slot}{"\n"}{end}'

log "DONE. CI cluster stack converged: churn-slot capacity asserted + provisioner + Kueue + all queues + ARC controller + ${#SCALE_SETS[@]} scale sets + hook ConfigMap + warm-cache CronJob + probe identity."
