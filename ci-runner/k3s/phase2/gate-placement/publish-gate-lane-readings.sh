#!/usr/bin/env bash
# publish-gate-lane-readings.sh: publish THIS node's two gate-placement readings
# on its own Node object as the custom condition `LivespecGateLaneCPU`, so the
# server's gate placement reconciler (reconcile-gate-lane-order.sh, beside this
# file) can tell a saturated gate lane from one with room.
# Work item livespec-dev-tooling-gvo7fa; contract: SPECIFICATION/contracts.md
# "Delegated pre-push gate", the "Placement by node pressure" bullet.
#
# THE TWO READINGS (the pool's node-saturation rule, .ai/ci-node-capacity-reads.md):
#   cpu.idle60            the node's CPU idle share, in percent, over the last
#                         60 seconds, from /proc/stat deltas.
#   ci.slice.some.avg60   `some avg60` of the BestEffort slice that holds the CI
#                         runner pods (kubepods.slice/kubepods-besteffort.slice
#                         cpu.pressure).
# They are NOT the node-level PSI that ../factory-pressure-placement/
# publish-node-cpu-pressure.sh publishes: on a mixed node that figure counts
# throttled factory sandboxes and reads high with cores idle.
#
# THE CREDENTIAL IS THE ONE THIS NODE ALREADY HOLDS, exactly as in the factory
# publisher: a condition is `status`, written through `nodes/status` with the
# scoped node-status credential (get+patch on this one node), or with the admin
# kubeconfig on the server, with one refresh of a rejected credential.
#
# NEVER A FALSE ZERO. A reading this script cannot take is published as the word
# `unreadable`, never as 0: a false idle of 0 would mark the node saturated and a
# false pressure of 0 would mark it free. The reconciler treats `unreadable`, an
# absent condition and a stale heartbeat alike: it falls back to the static lane
# order and logs the node and the reading.
#
# THE IDLE WINDOW. Each run appends "<epoch> <idle> <total>" to a small state
# file and computes the share against the NEWEST earlier sample that is at least
# GATE_LANE_WINDOW_MIN_SECONDS (55) and at most GATE_LANE_WINDOW_MAX_SECONDS
# (180) old. On the first run there is no such sample, so idle is `unreadable`.
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
USAGE="usage: ${SCRIPT_NAME} PROFILE   (PROFILE = phase0-bare-metal/profiles/<node>.env, which carries NODE_NAME, CLUSTER_ROLE and CHURN_KUBECONFIG_FILE)"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

PROFILE="${1:?$USAGE}"
[ -f "$PROFILE" ] || die "profile not found: ${PROFILE} -- ${USAGE}"
STAT_FILE="${GATE_LANE_STAT_FILE:-/proc/stat}"
SLICE_PRESSURE_FILE="${GATE_LANE_SLICE_PRESSURE_FILE:-/sys/fs/cgroup/kubepods.slice/kubepods-besteffort.slice/cpu.pressure}"
STATE_DIR="${GATE_LANE_STATE_DIR:-/var/lib/livespec/gate-placement}"
WINDOW_MIN="${GATE_LANE_WINDOW_MIN_SECONDS:-55}"
WINDOW_MAX="${GATE_LANE_WINDOW_MAX_SECONDS:-180}"
NOW_EPOCH="${GATE_LANE_NOW:-$(date -u +%s)}"
CONDITION_TYPE=LivespecGateLaneCPU

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

mkdir -p "$STATE_DIR"

# --- cpu.idle60 -------------------------------------------------------------
IDLE60=unreadable
IDLE_WHY=""
if [ -r "$STAT_FILE" ] && sample="$(awk '
      $1 == "cpu" { idle = $5; total = 0; for (i = 2; i <= 9 && i <= NF; i++) total += $i; print idle, total; found = 1 }
      END { if (!found) exit 1 }' "$STAT_FILE")"; then
  state="${STATE_DIR}/cpu-samples"
  IDLE60="$( { [ ! -f "$state" ] || awk -v now="$NOW_EPOCH" -v min="$WINDOW_MIN" -v max="$WINDOW_MAX" -v cur="$sample" '
      BEGIN { split(cur, c, " ") }
      NF == 3 && (now - $1) >= min && (now - $1) <= max { base_idle = $2; base_total = $3; have = 1 }
      END {
        dt = c[2] - base_total
        if (!have || dt <= 0) { print "unreadable"; exit }
        printf "%.1f\n", 100 * (c[1] - base_idle) / dt
      }' "$state"; } 2>/dev/null | tail -n1 || true)"
  : "${IDLE60:=unreadable}"
  [ "$IDLE60" != unreadable ] || IDLE_WHY="no usable /proc/stat sample ${WINDOW_MIN}-${WINDOW_MAX}s old"
  {
    [ ! -f "$state" ] || awk -v now="$NOW_EPOCH" -v max="$WINDOW_MAX" 'NF == 3 && (now - $1) <= max + 120 && (now - $1) >= 0' "$state"
    printf '%s %s\n' "$NOW_EPOCH" "$sample"
  } >"${state}.tmp"
  mv "${state}.tmp" "$state"
else
  IDLE_WHY="${STAT_FILE} is not readable or has no cpu line"
fi

# --- ci.slice.some.avg60 ----------------------------------------------------
SLICE60=unreadable
SLICE_WHY=""
if [ -r "$SLICE_PRESSURE_FILE" ]; then
  SLICE60="$(awk '
    $1 == "some" {
      for (i = 2; i <= NF; i++) { split($i, pair, "="); if (pair[1] == "avg60") value = pair[2] }
    }
    END { if (value ~ /^[0-9]+([.][0-9]+)?$/) print value; else print "unreadable" }
  ' "$SLICE_PRESSURE_FILE")"
  [ "$SLICE60" != unreadable ] || SLICE_WHY="no usable 'some avg60' field in ${SLICE_PRESSURE_FILE}"
else
  SLICE_WHY="${SLICE_PRESSURE_FILE} is not readable"
fi

[ -z "$IDLE_WHY" ] || echo "${SCRIPT_NAME}: ${NODE_NAME}: cpu.idle60 unreadable: ${IDLE_WHY}" >&2
[ -z "$SLICE_WHY" ] || echo "${SCRIPT_NAME}: ${NODE_NAME}: ci.slice.some.avg60 unreadable: ${SLICE_WHY}" >&2

MESSAGE="cpu.idle60=${IDLE60} ci.slice.some.avg60=${SLICE60}"
NOW="$(date -u -d "@${NOW_EPOCH}" +%Y-%m-%dT%H:%M:%SZ)"
PATCH="$(printf '{"status":{"conditions":[{"type":"%s","status":"True","reason":"GateLaneReading","message":"%s","lastHeartbeatTime":"%s","lastTransitionTime":"%s"}]}}' \
  "$CONDITION_TYPE" "$MESSAGE" "$NOW" "$NOW")"

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

printf '%s: %s %s %s at %s\n' "$SCRIPT_NAME" "$NODE_NAME" "$CONDITION_TYPE" "$MESSAGE" "$NOW"
