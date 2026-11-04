#!/usr/bin/env bash
# publish-node-cpu-pressure.sh: publish THIS node's CPU pressure (PSI
# cpu some avg60) on its own Node object as the custom condition
# `LivespecCPUPressure`, so the server's placement reconciler
# (reconcile-factory-pressure-taint.sh, beside this file) can compare the
# factory nodes. Orchestrator work-item bd-ib-plon2p.
#
# THE CREDENTIAL IS THE ONE THIS NODE ALREADY HOLDS. A condition is part of
# `status`, so it is written through the `nodes/status` subresource, and the
# agent's scoped node-status credential (../node-status-credential/) grants
# exactly get+patch on `nodes/status` for this one named node. No new grant
# is minted. A SERVER patches through k3s's own admin kubeconfig, the same
# split ../node-extended-resource/patch-node-churn-capacity.sh uses, including
# its one refresh of a credential the API server rejects.
#
# WHY A CONDITION. A strategic-merge patch on `status.conditions` merges by
# `type`, so this writes its own condition and leaves the kubelet's Ready,
# MemoryPressure and the rest alone. The kubelet likewise patches only the
# condition types it owns, which is how node-problem-detector's custom
# conditions live beside it. The reading is in `message` and the freshness is
# in `lastHeartbeatTime`, which the reconciler checks.
#
# NEVER A FALSE ZERO. An absent or malformed avg60 is an ERROR, never 0: a
# false zero would mark this node the quietest and steer pods onto it. That is
# the same rule ../../../../ansible/roles/pressure_telemetry/files/pressure-telemetry.sh
# keeps. On an error this script exits non-zero and writes nothing, so the
# heartbeat goes stale and the reconciler stops steering.
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
USAGE="usage: ${SCRIPT_NAME} PROFILE   (PROFILE = phase0-bare-metal/profiles/<node>.env, which carries NODE_NAME, CLUSTER_ROLE and CHURN_KUBECONFIG_FILE)"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

PROFILE="${1:?$USAGE}"
[ -f "$PROFILE" ] || die "profile not found: ${PROFILE} -- ${USAGE}"
PSI_FILE="${FACTORY_PRESSURE_PSI_FILE:-/proc/pressure/cpu}"
CONDITION_TYPE=LivespecCPUPressure

profile_value() {  # profile_value KEY; parsed, never sourced
  sed -n "s/^$1=//p" "$PROFILE" | tail -n1 | sed 's/[[:space:]]*$//'
}

NODE_NAME="$(profile_value NODE_NAME)"
ROLE="$(profile_value CLUSTER_ROLE)"
CHURN_KUBECONFIG_FILE="$(profile_value CHURN_KUBECONFIG_FILE)"
[ -n "$NODE_NAME" ] || die "${PROFILE}: NODE_NAME is empty -- there is no node to publish for"
case "$ROLE" in
  server|agent) ;;
  *) die "${PROFILE}: CLUSTER_ROLE must be 'server' or 'agent', got '${ROLE}'" ;;
esac

if [ -z "${KUBECONFIG:-}" ]; then
  if [ "$ROLE" = server ]; then
    KUBECONFIG=/etc/rancher/k3s/k3s.yaml
  else
    [ -n "$CHURN_KUBECONFIG_FILE" ] || die "${PROFILE}: CLUSTER_ROLE is 'agent' but CHURN_KUBECONFIG_FILE is empty, so there is no node-status credential to publish with (../node-status-credential/README.md)"
    KUBECONFIG="$CHURN_KUBECONFIG_FILE"
  fi
fi
export KUBECONFIG
[ -f "$KUBECONFIG" ] || die "KUBECONFIG ${KUBECONFIG} not found"

[ -r "$PSI_FILE" ] || die "${PSI_FILE} is not readable -- this kernel exposes no CPU pressure, so there is no reading to publish"
AVG60="$(awk '
  $1 == "some" {
    for (i = 2; i <= NF; i++) { split($i, pair, "="); if (pair[1] == "avg60") value = pair[2] }
  }
  END { if (value ~ /^[0-9]+([.][0-9]+)?$/) print value; else exit 1 }
' "$PSI_FILE")" || die "no usable 'some avg60' field in ${PSI_FILE}; refusing to publish a false zero"

NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PATCH="$(printf '{"status":{"conditions":[{"type":"%s","status":"True","reason":"PSIReading","message":"cpu.some.avg60=%s","lastHeartbeatTime":"%s","lastTransitionTime":"%s"}]}}' \
  "$CONDITION_TYPE" "$AVG60" "$NOW" "$NOW")"

CREDENTIAL_REJECTED_RE='Unauthorized|asked for the client to provide credentials|You must be logged in|401'
CREDENTIAL_REFRESH_BIN="${NODE_STATUS_REFRESH_BIN:-/usr/local/bin/refresh-node-status-kubeconfig}"
patch_stderr="$(mktemp)"
trap 'rm -f "$patch_stderr"' EXIT

publish() {
  kubectl patch node "$NODE_NAME" --subresource=status --type=strategic -p "$PATCH" >/dev/null 2>"$patch_stderr"
}

if ! publish; then
  cat "$patch_stderr" >&2
  grep -qiE "$CREDENTIAL_REJECTED_RE" "$patch_stderr" || die "publishing ${CONDITION_TYPE} on ${NODE_NAME} failed (see above)"
  [ "$ROLE" = agent ] || die "the API server REJECTED the admin kubeconfig ${KUBECONFIG} on server ${NODE_NAME} -- investigate the API server, not the credential"
  [ -x "$CREDENTIAL_REFRESH_BIN" ] || die "the node-status credential was REJECTED and no refresh tool is executable at ${CREDENTIAL_REFRESH_BIN} (node_status_credential role)"
  echo "${SCRIPT_NAME}: the node-status credential was rejected; re-fetching it once via ${CREDENTIAL_REFRESH_BIN}" >&2
  "$CREDENTIAL_REFRESH_BIN" || die "refresh FAILED: ${CREDENTIAL_REFRESH_BIN} could not re-fetch the node-status credential for ${NODE_NAME}"
  publish || { cat "$patch_stderr" >&2; die "publishing ${CONDITION_TYPE} on ${NODE_NAME} failed again after one credential refresh"; }
fi

printf '%s: %s %s cpu.some.avg60=%s at %s\n' "$SCRIPT_NAME" "$NODE_NAME" "$CONDITION_TYPE" "$AVG60" "$NOW"
