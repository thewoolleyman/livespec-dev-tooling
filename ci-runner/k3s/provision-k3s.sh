#!/usr/bin/env bash
# provision-k3s.sh — idempotently install this node's pinned k3s, in the ROLE
# its profile declares: the single-node control plane it has always installed,
# or an AGENT that joins an existing cluster.
#
# Authored to install ALONGSIDE the then-live podman/dockershim runner
# pool, touching NOTHING that pool owned: different binaries (k3s's
# bundled containerd, not podman), different systemd units (k3s.service,
# not runner@.service), different host-unique label (poweredge-xubuntu-k3s,
# not the pool's label). That pool was decommissioned 2026-08-21 and its
# source deleted under livespec-s43svm.19; the isolation this script keeps
# is recorded because it is why the cutover was safe, not because there is
# still a second pool.
#
# ROLE-AWARE (2026-09-06, livespec-dev-tooling-mj4zrr, livespec plan
# `k3s-on-gmktec-for-vps-usage` carrier R3), for the same reason
# `phase2/install-node.sh` is: the fleet is gaining a SECOND node, and a second
# node must be brought up by THIS script rather than by a second copy of it.
# The role, and every other node-specific value, is read from the node's
# `phase0-bare-metal/profiles/<node>.env` through the shared parser
# `phase0-bare-metal/profile.sh` — so a second node is a second profile and
# never a second script (SPECIFICATION/non-functional-requirements.md
# §"Runner-pool node rebuild recipe", "One profile per node").
#
#   server  runs the steps it ran before this change, in that order, with the
#           same k3s install command: the fleet config from phase2/k3s-config/,
#           the pinned k3s server, helm, the Ready wait, the cache-tier-carrier
#           label and the kubeconfig mode.
#   agent   runs ONE step — the pinned k3s AGENT install — and skips the five
#           that are the server's, each with a logged reason. It joins
#           CLUSTER_JOIN_ADDRESS, authenticates with the token k3s reads AT RUN
#           TIME out of CLUSTER_TOKEN_FILE (a PATH, never the token: this tree
#           carries no secret), pins --node-ip to NODE_ADDRESS, registers every
#           NODE_TAINTS taint, and carries the same k3s-role=arc-runner-host
#           label so the phase2 node pins still resolve.
#
# --dry-run PRINTS THE PLAN AND EXECUTES NOTHING: no installer is invoked, no
# k3s is downloaded, no root check is made. The plan carries the EXACT install
# command for the node's role, built from the same two variables the executor
# hands to the installer, which is what makes both role plans assertable
# off-host (./provision-k3s-exit-tests.sh).
#
# Pinned versions (do not float without re-running this script's
# version check and updating this comment + the ledger record):
#   k3s:   v1.36.2+k3s1  (stable channel)
#   ARC:   gha-runner-scale-set-controller / gha-runner-scale-set 0.14.2
#          (installed by install-arc.sh, not this script)
#   Kueue: v0.19.1        (installed by install-kueue.sh, not this script)
#
# Requires: run as a sudo-capable admin on the node. Outbound HTTPS only
# (get.k3s.io, GitHub releases) — no inbound reachability required, matching
# the existing host-requirements Network clause. An agent additionally needs
# outbound reach to CLUSTER_JOIN_ADDRESS.
#
# Usage: provision-k3s.sh --dry-run PROFILE
#        sudo provision-k3s.sh PROFILE
#   PROFILE  path to the node's phase0-bare-metal/profiles/<node>.env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "$0")"
K3S_VERSION="v1.36.2+k3s1"
HELM_VERSION="v3.21.4"        # co-maintained with README.md "Pinned versions"
NODE_LABEL="k3s-role=arc-runner-host"
# The pool's hostPath singletons — the sccache redis, the crates proxy, the
# PyPI files proxy and the warm-cache CronJob — mount directories on THIS
# node's storage tiers, so they pin to this label and not to NODE_LABEL above.
# NODE_LABEL is the RUNNER role: every node that joins the pool to execute
# workflow pods carries it, including a second node that carries no tier, so it
# cannot express "the node whose disks these directories are on". Set below
# (step 2b) rather than via --node-label, because --node-label applies only on
# a FRESH install and this script must be re-runnable on a provisioned node.
TIER_CARRIER_LABEL="ci-runner.io/cache-tier-carrier=true"
# The tier whose presence PROVES this node is the carrier (phase2/
# storage-layout/): the label is only set when it is actually mounted here.
CACHE_TIER_MOUNT="${CI_CACHE_TIER_MOUNT:-/var/cache/ci-runner}"

USAGE="usage: ${SCRIPT_NAME} [--dry-run] PROFILE   (PROFILE = phase0-bare-metal/profiles/<node>.env, which carries CLUSTER_ROLE and every other node-specific value)"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
DRY_RUN=0
PROFILE_PATH=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) printf '%s\n' "$USAGE"; exit 0 ;;
    # No `--` end-of-options case on purpose: no option here takes a value, so
    # `--` would only be a way to silently swallow the arguments after it.
    -*) die "unknown option '$1' -- ${USAGE}" ;;
    *)
      if [ -n "$PROFILE_PATH" ]; then
        die "more than one profile given ('${PROFILE_PATH}' and '$1') -- ${USAGE}"
      fi
      PROFILE_PATH="$1" ;;
  esac
  shift
done

[ -n "$PROFILE_PATH" ] || die "no profile given -- ${USAGE}"

# ---------------------------------------------------------------------------
# Profile: parsed, never sourced
#
# The parser lives in phase0-bare-metal/profile.sh and is shared with every
# bare-metal stage, so no two consumers can disagree about what a profile may
# contain — each of them REFUSES an unknown key, which a per-consumer key list
# would turn into "the key a later stage needs breaks the earlier one". It has
# already refused a CLUSTER_ROLE that is neither role, and an `agent` that
# names neither the address it joins nor the file it authenticates with, by the
# time it returns.
# ---------------------------------------------------------------------------
# shellcheck source=ci-runner/k3s/phase0-bare-metal/profile.sh
source "${SCRIPT_DIR}/phase0-bare-metal/profile.sh"
profile_load "$PROFILE_PATH"

ROLE="${CFG[CLUSTER_ROLE]}"

# ---------------------------------------------------------------------------
# The k3s install command, built ONCE
#
# INSTALL_EXEC is what both the printed plan and the executor below hand to
# get.k3s.io as INSTALL_K3S_EXEC, so the command a --dry-run prints cannot
# describe a different install from the one that happens.
# ---------------------------------------------------------------------------
INSTALL_EXEC=""

build_server_exec() {
  # --disable traefik/servicelb: this node carries no ingress traffic and no
  # LoadBalancer services are needed for the ARC + Kueue control plane.
  # --node-label distinguishes this k3s node from any future additional node
  # without colliding with the existing GitHub Actions runner labels (which
  # live on the runner registration, not the Kubernetes node — see
  # arc/values-host-unique.yaml).
  INSTALL_EXEC="server --disable traefik --disable servicelb --node-label ${NODE_LABEL}"
}

# node_ip_of ADDRESS — the bare address k3s wants from the profile's
# NODE_ADDRESS, which the base-OS stage states as a netplan CIDR
# (`192.168.1.156/24`). `auto` means the node pins nothing and prints empty.
node_ip_of() {
  case "$1" in
    auto) ;;
    *) printf '%s' "${1%%/*}" ;;
  esac
}

# require_join_token — the join token is a CLUSTER CREDENTIAL that lives on the
# node and nowhere in this tree. Both refusals below are evaluated in --dry-run
# too, on purpose: a plan that cannot be executed must not be printed as though
# it could, and an operator finding out at the console that the token was never
# placed has already rebuilt the node.
require_join_token() {
  local token_file="$1" mode
  [ -e "$token_file" ] || die "${PROFILE_PATH}: CLUSTER_ROLE=agent names CLUSTER_TOKEN_FILE '${token_file}', which does not exist on this node. Place the cluster's join token there (mode 0600, root:root) before provisioning; this tree carries no secret and cannot create it."
  [ -f "$token_file" ] || die "${PROFILE_PATH}: CLUSTER_TOKEN_FILE '${token_file}' is not a regular file"
  mode="$(stat -c '%a' "$token_file")" || die "${PROFILE_PATH}: cannot read the mode of CLUSTER_TOKEN_FILE '${token_file}'"
  if [ "$((8#${mode} & 8#077))" -ne 0 ]; then
    die "${PROFILE_PATH}: CLUSTER_TOKEN_FILE '${token_file}' is mode ${mode}, readable beyond its owner. The join token admits a node to the cluster, so it is owner-only (0600) or the run refuses."
  fi
}

build_agent_exec() {
  local token_file="${CFG[CLUSTER_TOKEN_FILE]}" node_ip taint
  local -a taints=() exec_args=()

  require_join_token "$token_file"

  exec_args=(agent --server "${CFG[CLUSTER_JOIN_ADDRESS]}" --token-file "$token_file")

  # The node IP is PINNED rather than inferred wherever the profile states one:
  # a node whose wifi and wired interfaces share a subnet can otherwise register
  # the address the cluster cannot reach it on.
  node_ip="$(node_ip_of "${CFG[NODE_ADDRESS]}")"
  if [ -n "$node_ip" ]; then
    exec_args+=(--node-ip "$node_ip")
  fi

  read -r -a taints <<< "${CFG[NODE_TAINTS]}"
  for taint in ${taints[@]+"${taints[@]}"}; do
    case "$taint" in
      *=*:*) ;;
      *) die "${PROFILE_PATH}: NODE_TAINTS record '${taint}' is not <key>=<value>:<Effect>" ;;
    esac
    exec_args+=(--node-taint "$taint")
  done

  # The RUNNER role label, so the phase2 node pins resolve on this node too.
  # Like the server's, it applies only on a FRESH install.
  exec_args+=(--node-label "$NODE_LABEL")

  INSTALL_EXEC="${exec_args[*]}"
}

case "$ROLE" in
  server) build_server_exec ;;
  agent) build_agent_exec ;;
  # profile.sh has already refused any other value; this arm exists so a future
  # third role cannot reach the executor with an empty install command.
  *) die "${PROFILE_PATH}: CLUSTER_ROLE must be 'server' or 'agent', got '${ROLE}'" ;;
esac

k3s_install_command() {
  printf "curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION='%s' INSTALL_K3S_EXEC='%s' sh -s -" \
    "$K3S_VERSION" "$INSTALL_EXEC"
}

# ---------------------------------------------------------------------------
# The step plan — ONE table, read by both --dry-run and the executor, so the
# printed plan can never describe a different run from the one that happens.
# The step numbering is the historical server numbering, kept verbatim so the
# two role plans are comparable line by line.
#
# STEP_SKIP[id] set  => the AGENT role skips that step, and the reason is
#                       logged in its place. An unset entry runs on both roles.
# STEP_AGENT_LABEL   => the step runs on both roles but does something
#                       different on an agent, and says so.
# ---------------------------------------------------------------------------
STEP_IDS=(
  k3s-config
  k3s-install
  helm
  node-ready
  tier-label
  kubeconfig-mode
)

declare -A STEP_LABEL=()
declare -A STEP_AGENT_LABEL=()
declare -A STEP_SKIP=()

STEP_LABEL[k3s-config]="0. Install the fleet's k3s server config BEFORE the first k3s start"
STEP_LABEL[k3s-install]="1. Install k3s ${K3S_VERSION} (idempotent — skip if already at this version)"
STEP_LABEL[helm]="1b. Install helm ${HELM_VERSION} (idempotent — skip if already at this version)"
STEP_LABEL[node-ready]="2. Wait for the node to report Ready"
STEP_LABEL[tier-label]="2b. Label this node as the cache-tier carrier (idempotent)"
STEP_LABEL[kubeconfig-mode]="3. Make kubectl usable for the provisioning admin (read access to KUBECONFIG)"

STEP_AGENT_LABEL[k3s-install]="1. Install k3s ${K3S_VERSION} AGENT joining ${CFG[CLUSTER_JOIN_ADDRESS]} (idempotent — skip if already at this version)"

STEP_SKIP[k3s-config]="phase2/k3s-config/config.yaml is the SERVER configuration — 'disable: local-storage', 'write-kubeconfig-mode' and 'tls-san' are server-only keys. An agent takes no server-only config; its kubelet arguments arrive with the node-local runbook, phase2/install-node.sh."
STEP_SKIP[helm]="helm is installed here for the reconstruct-on-boot converge (phase2/reconstruct/converge-ci-stack.sh), which applies cluster-scoped objects with the admin kubeconfig and is a step an agent skips."
STEP_SKIP[node-ready]="reads the cluster through /etc/rancher/k3s/k3s.yaml, the admin kubeconfig an agent does not hold. The SERVER is where this node's registration becomes visible."
STEP_SKIP[tier-label]="labels a node through the API with that same admin kubeconfig, and the label it sets marks the node whose disks the pool's hostPath singletons live on — which is the tier carrier, not every node that joins."
STEP_SKIP[kubeconfig-mode]="there is no /etc/rancher/k3s/k3s.yaml on an agent to widen."

step_label() {  # step_label ID
  if [ "$ROLE" = agent ] && [ -n "${STEP_AGENT_LABEL[$1]:-}" ]; then
    printf '%s' "${STEP_AGENT_LABEL[$1]}"
  else
    printf '%s' "${STEP_LABEL[$1]}"
  fi
}

step_skipped() {  # step_skipped ID -> true when THIS role skips it
  [ "$ROLE" = agent ] && [ -n "${STEP_SKIP[$1]:-}" ]
}

print_plan() {
  local id
  printf '== %s step plan ==\n' "$SCRIPT_NAME"
  printf 'profile:  %s\n' "$PROFILE_PATH"
  printf 'node:     %s\n' "${CFG[NODE_NAME]}"
  printf 'role:     %s\n' "$ROLE"
  printf 'join:     %s\n' "${CFG[CLUSTER_JOIN_ADDRESS]:-(none — this node forms its own cluster)}"
  printf '\n'
  for id in "${STEP_IDS[@]}"; do
    if step_skipped "$id"; then
      printf 'SKIP [%s] %s\n' "$ROLE" "${STEP_LABEL[$id]}"
      printf '     reason: %s\n' "${STEP_SKIP[$id]}"
      continue
    fi
    printf 'RUN  [%s] %s\n' "$ROLE" "$(step_label "$id")"
    if [ "$id" = k3s-install ]; then
      printf '     + %s\n' "$(k3s_install_command)"
    fi
  done
}

# ---------------------------------------------------------------------------
# The steps
# ---------------------------------------------------------------------------
step_k3s_config() {
  # /etc/rancher/k3s/config.yaml (kubelet max-pods, the bundled local-storage
  # disable) is read by k3s on every start; installing it first means a fresh
  # node's very first start already carries it, and a rebuilt node cannot lose
  # the hand-set values this replaced (livespec-a6lxuv, livespec-sernfh). The
  # installer is idempotent and never restarts k3s.
  "${SCRIPT_DIR}/phase2/k3s-config/install-k3s-config.sh"
}

step_k3s_install() {
  local current
  if command -v k3s >/dev/null 2>&1; then
    # `k3s --version` prints `k3s version v1.36.2+k3s1 (01b6f04a)`: field 3
    # already carries the leading `v`. Compare with and without it, since the
    # original test only compared against a stripped form and a re-prefixed
    # form ("vv1.36…") and so REFUSED every re-run on an installed host — found
    # 2026-09-02 the first time this script was re-run live for idempotency.
    current="$(k3s --version | head -1 | awk '{print $3}')"
    if [ "$current" = "$K3S_VERSION" ] || [ "$current" = "${K3S_VERSION#v}" ] || [ "v${current}" = "$K3S_VERSION" ]; then
      echo "k3s already installed at ${K3S_VERSION} — leaving the ${ROLE} alone"
    else
      echo "FATAL: k3s installed at v${current}, expected ${K3S_VERSION}. Uninstall first (see README) or update this pin deliberately."
      exit 1
    fi
  else
    curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="$K3S_VERSION" \
      INSTALL_K3S_EXEC="$INSTALL_EXEC" \
      sh -s -
  fi
}

step_helm() {
  # The reconstruct-on-boot converge (phase2/reconstruct/converge-ci-stack.sh)
  # fails closed without helm on PATH, and until 2026-09-02 nothing in git
  # installed it — the live /usr/local/bin/helm was hand-placed, so a rebuilt
  # host would boot into a cluster the converge could not rebuild. Pinned and
  # checksum-verified against the release's published .sha256sum.
  local arch helm_arch tarball tmp
  if command -v helm >/dev/null 2>&1 && helm version --short 2>/dev/null | grep -q "^${HELM_VERSION}+"; then
    echo "helm already installed at ${HELM_VERSION} — skipping install"
  else
    arch="$(uname -m)"
    case "$arch" in
      x86_64) helm_arch=amd64 ;;
      aarch64) helm_arch=arm64 ;;
      *) echo "FATAL: unsupported arch for helm: ${arch}"; exit 1 ;;
    esac
    tarball="helm-${HELM_VERSION}-linux-${helm_arch}.tar.gz"
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    curl -fsSL --retry 3 -o "${tmp}/${tarball}" "https://get.helm.sh/${tarball}"
    curl -fsSL --retry 3 -o "${tmp}/${tarball}.sha256sum" "https://get.helm.sh/${tarball}.sha256sum"
    (cd "$tmp" && sha256sum -c "${tarball}.sha256sum")
    tar -xzf "${tmp}/${tarball}" -C "$tmp" "linux-${helm_arch}/helm"
    install -o root -g root -m 0755 "${tmp}/linux-${helm_arch}/helm" /usr/local/bin/helm
  fi
  echo "helm: $(helm version --short)"
}

step_node_ready() {
  export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
  for _ in $(seq 1 60); do
    if k3s kubectl get nodes --no-headers 2>/dev/null | grep -q ' Ready'; then
      break
    fi
    sleep 2
  done
  k3s kubectl get nodes -o wide || { echo "FATAL: k3s node did not become Ready within 120s"; exit 1; }
}

step_tier_label() {
  # k3s defaults --node-name to the lowercased hostname; K3S_NODE_NAME overrides
  # it for a host whose k3s node name was set otherwise.
  local node_name="${K3S_NODE_NAME:-$(hostname | tr '[:upper:]' '[:lower:]')}"
  if findmnt -no TARGET "${CACHE_TIER_MOUNT}" >/dev/null 2>&1; then
    # `kubectl label --overwrite` IS the idempotent form: on a re-run it patches
    # the same value and reports "not labeled" instead of failing the way a bare
    # `kubectl label` does once the key exists.
    k3s kubectl label node "${node_name}" "${TIER_CARRIER_LABEL}" --overwrite
    echo "${node_name} carries ${CACHE_TIER_MOUNT}; labelled ${TIER_CARRIER_LABEL}"
  else
    # Not fatal: a node may legitimately join the pool to run workflow pods
    # without carrying a tier. It simply must not attract the hostPath
    # singletons, and an absent label is exactly how it does not.
    echo "WARN: ${CACHE_TIER_MOUNT} is not a mountpoint on ${node_name} — NOT labelling it ${TIER_CARRIER_LABEL}; the hostPath singletons (sccache redis, crates proxy, PyPI proxy, warm-cache CronJob) will not schedule here"
  fi
}

step_kubeconfig_mode() {
  # k3s.yaml is 0600 root:root by default. Widen to 0644 — the documented k3s
  # convention for non-root kubectl use, not a security relaxation of the
  # runner containment model above, which governs job execution identity, not
  # admin access.
  #
  # THIS COMMENT USED TO REST THE WIDENING on the claim that nothing off this
  # host could reach its API server. That premise is GONE as of 2026-09-07:
  # phase2/k3s-config/config.yaml declares a `tls-san` carrying this node's
  # tailnet name and tailnet address, so the API server IS reached from off
  # this host — over the TAILNET, to TAILNET MEMBERS ONLY (the LAN address
  # answers nothing off-LAN, and nothing is published to the public internet).
  # The old claim must not be revived as the justification for this mode.
  #
  # 0644 nonetheless stands, on a different argument, weighed in full beside
  # that `write-kubeconfig-mode` entry in phase2/k3s-config/config.yaml: the
  # mode never defended against a local uid (127.0.0.1:6443 has always answered
  # every local process, so a reader of this file already held cluster-admin),
  # and the pool's root-free operator converge paths depend on it. Tightening
  # is earned by first giving those readers a scoped, non-admin credential —
  # the shape observability/ci-kueue-webhook-probe.sh already uses — not by a
  # chmod here.
  chmod 0644 /etc/rancher/k3s/k3s.yaml
  printf 'k3s ready. export KUBECONFIG=/etc/rancher/k3s/k3s.yaml for kubectl/helm.\n'
}

run_step() {  # run_step ID
  case "$1" in
    k3s-config) step_k3s_config ;;
    k3s-install) step_k3s_install ;;
    helm) step_helm ;;
    node-ready) step_node_ready ;;
    tier-label) step_tier_label ;;
    kubeconfig-mode) step_kubeconfig_mode ;;
    *) die "no runner for step '$1' (the step table and run_step have drifted)" ;;
  esac
}

# ---------------------------------------------------------------------------
# --dry-run stops here, having touched nothing at all.
# ---------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  print_plan
  printf '\n-- --dry-run: the plan above was printed and NOTHING was executed --\n'
  exit 0
fi

print_plan

for step_id in "${STEP_IDS[@]}"; do
  if step_skipped "$step_id"; then
    log "[${ROLE}] SKIP ${STEP_LABEL[$step_id]} — ${STEP_SKIP[$step_id]}"
    continue
  fi
  log "[${ROLE}] $(step_label "$step_id")"
  run_step "$step_id"
done

if [ "$ROLE" = agent ]; then
  log "DONE. Next: sudo phase2/install-node.sh ${PROFILE_PATH} (see README.md)."
  printf 'This node registered with the cluster at %s; confirm it from the SERVER with: k3s kubectl get nodes -o wide\n' "${CFG[CLUSTER_JOIN_ADDRESS]}"
else
  log "DONE. Next: install-arc.sh, then install-kueue.sh (see README.md)."
fi
