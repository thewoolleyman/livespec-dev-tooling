#!/usr/bin/env bash
# install-arc.sh — idempotently install GitHub's Actions Runner Controller (ARC)
# onto the k3s cluster provisioned by install-k3s.sh, plus ONE proof-of-life
# `AutoscalingRunnerSet`. Touches nothing belonging to the existing
# rootless-podman/dockershim runner pool.
#
# Run under the SAME credential wrapper the existing runner supervisors use, so
# the GitHub App credential is injected the established way rather than by a new
# mechanism:
#
#   sudo /usr/local/bin/with-github-ci-runners-env.sh -- \
#     ci-runner/k3s-arc-kueue/install-arc.sh
#
# Phase 1 of the k3s + ARC + Kueue migration (livespec work-item
# livespec-s43svm.14). Design record:
# livespec/plan/fleet-ci-runner-pool/research/k3s-arc-kueue-migration.md
#
# CREDENTIAL MODEL — unchanged from the podman path, deliberately
# ---------------------------------------------------------------
# ci-runner/README.md "Credential model" records the model: the
# `thewoolleyman-ci-runners` GitHub App's private key lives in a dedicated
# `github-ci-runners` 1Password environment, injected ONLY by
# `/usr/local/bin/with-github-ci-runners-env.sh`, and consumed by the
# `gate-runner-supervisor.service` unit (and, until it was decommissioned, the
# podman lane's `ci-runner-supervisor.service`). This
# script reuses exactly that wrapper and exactly those variable names. It
# invents no new secret store, hardcodes no credential, and writes no credential
# value to disk or to git — it pipes the wrapper-injected values straight into a
# Kubernetes Secret via stdin.
#
# ARC consumes App credentials natively, so no JIT-config minting equivalent to
# mint-jitconfig.sh is needed on this path: the controller itself calls the
# GitHub API to register and scale the runner set.
set -euo pipefail

# Pinned deliberately — never float `latest`. Both charts ship at one version.
ARC_CHART_VERSION="${ARC_CHART_VERSION:-0.14.2}"
ARC_CONTROLLER_CHART="oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller"
ARC_SCALE_SET_CHART="oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set"

CONTROLLER_NAMESPACE="${CONTROLLER_NAMESPACE:-arc-systems}"
RUNNER_NAMESPACE="${RUNNER_NAMESPACE:-arc-runners}"

# Must match `runnerScaleSetName` in arc-runner-scale-set-values.yaml: the Helm
# release name is what a workflow's `runs-on` resolves against.
SCALE_SET_NAME="${SCALE_SET_NAME:-poweredge-xubuntu-k3s}"

# Optional override so a first smoke test can register against a throwaway repo
# instead of the default in the values file. See that file's comment.
GITHUB_CONFIG_URL="${GITHUB_CONFIG_URL:-}"

src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
values_file="${src_dir}/arc-runner-scale-set-values.yaml"

log() { printf '%s\n' "install-arc: $*" >&2; }

[ "$(id -u)" -eq 0 ] || { log "must run as root (use sudo)"; exit 1; }
command -v helm >/dev/null 2>&1 || { log "helm not found on PATH"; exit 1; }
[ -r /etc/rancher/k3s/k3s.yaml ] || { log "no k3s kubeconfig; run install-k3s.sh first"; exit 1; }

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# --- App credential, from the established wrapper's variable names ---
: "${GITHUB_APP_ID_CI_RUNNER:?set by with-github-ci-runners-env.sh}"
: "${GITHUB_APP_INSTALLATION_ID_CI_RUNNER:?set by with-github-ci-runners-env.sh}"
: "${GITHUB_PRIVATE_KEY_CI_RUNNER:?set by with-github-ci-runners-env.sh}"

# --- controller ---
log "installing ARC controller ${ARC_CHART_VERSION} into ${CONTROLLER_NAMESPACE}"
helm upgrade --install arc \
  --namespace "${CONTROLLER_NAMESPACE}" \
  --create-namespace \
  --version "${ARC_CHART_VERSION}" \
  --wait \
  "${ARC_CONTROLLER_CHART}"

# --- runner-set namespace + App secret ---
kubectl create namespace "${RUNNER_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# `create --dry-run=client -o yaml | apply -f -` is the idempotent form: it
# converges an existing Secret instead of failing on AlreadyExists, and the key
# material reaches kubectl only via stdin — never an argv the process table
# would expose, and never a file.
log "converging Secret ${RUNNER_NAMESPACE}/arc-github-app from the wrapper's env"
kubectl create secret generic arc-github-app \
  --namespace "${RUNNER_NAMESPACE}" \
  --from-literal=github_app_id="${GITHUB_APP_ID_CI_RUNNER}" \
  --from-literal=github_app_installation_id="${GITHUB_APP_INSTALLATION_ID_CI_RUNNER}" \
  --from-file=github_app_private_key=/dev/stdin \
  --dry-run=client -o yaml <<<"${GITHUB_PRIVATE_KEY_CI_RUNNER}" \
  | kubectl apply -f -

# --- the proof-of-life scale set ---
log "installing AutoscalingRunnerSet ${SCALE_SET_NAME} (minRunners 0, maxRunners 2)"
set -- helm upgrade --install "${SCALE_SET_NAME}" \
  --namespace "${RUNNER_NAMESPACE}" \
  --version "${ARC_CHART_VERSION}" \
  --values "${values_file}" \
  --wait
if [ -n "${GITHUB_CONFIG_URL}" ]; then
  set -- "$@" --set "githubConfigUrl=${GITHUB_CONFIG_URL}"
fi
"$@" "${ARC_SCALE_SET_CHART}"

# --- verification ---
kubectl get pods -n "${CONTROLLER_NAMESPACE}"
kubectl get autoscalingrunnerset -n "${RUNNER_NAMESPACE}"

log "ARC installed. ZERO traffic is routed here: no fleet workflow carries"
log "  runs-on: ${SCALE_SET_NAME}"
log "next: ci-runner/k3s-arc-kueue/install-kueue.sh"
