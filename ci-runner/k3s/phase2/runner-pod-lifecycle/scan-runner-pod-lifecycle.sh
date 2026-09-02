#!/usr/bin/env bash
# scan-runner-pod-lifecycle.sh — detect the runner-pod LIFECYCLE stall on a k3s
# runner node: the pool has capacity, no runner is wedged, and yet pods do not
# come up. This is the THIRD "jobs queued, nothing starting" case (see
# ../README.md "Runner-pod lifecycle stall"), beside saturation and the wedged
# runner that ../wedged-runner/scan-wedged-runners.sh detects.
#
# THE FAILURE THIS DETECTS. On 2026-09-01 (livespec plan
# ci-runner-pod-lifecycle-reliability, epic livespec-ifwnqj, research/001-003)
# fleet CI queued for over an hour with the wedge scan clean, 8 of 64 churn
# slots allocated and Kueue admitting: runner pods were CREATED but each one's
# local-path work PVC took up to ~11 minutes to provision, the scheduler's
# 600 s volume-bind deadline expired 94 times in 20 minutes and re-queued the
# pods, and underneath that containerd had hit the kernel's inotify-instance
# cap (`failed to create inotify fd: too many open files`, 55 in 10 minutes) so
# every sandbox call timed out. On 2026-09-02 a different member of the same
# family: a workflow pod died in StartError (`failed to create shim task`)
# under two running jobs, because the previous release wave's teardown
# (88 StopPodSandbox deadlines / 3 min, 246 FailedKillPod / 15 min) was
# starving containerd on the saturated array. And the same day an ARC boot
# race left one scale set's listener holding a stale EphemeralRunnerSet
# reference — invisible while idle, a crash-loop on the first job, 31 minutes
# of that repository's CI queueing with nothing wrong on any capacity signal.
#
# In every case the CI consumer saw only a red check whose name misdirected
# (`check-format: FAILURE` for a check that never ran; the ARC hook's
# `Executing the custom container implementation failed`), discovered by a
# human, minutes to hours later. Nothing on the cluster said so. That is the
# gap this scan closes: it names the class, with the count, in the journal,
# every five minutes, so the condition is a reading instead of a diagnosis.
#
# SIX CLASSES, each read from the node-side observable that actually PERSISTS
# long enough for a five-minute sweep to see it:
#
#   pvc-pending          a PVC in the runners namespace Pending longer than
#                        PVC_PENDING_SECONDS — the provisioner is behind
#                        (2026-09-01: Pending PVCs 38 -> 57).
#   bind-deadline        kube-scheduler `binding volumes: context deadline
#                        exceeded` lines in the k3s journal inside the window
#                        (2026-09-01: 94 in 20 minutes).
#   inotify-emfile       containerd `failed to create inotify fd` lines in
#                        containerd.log inside the window — the 2026-09-01 root
#                        cause specifically (research/002; the budget is now
#                        8192, shipped by ../node-inotify-budget/).
#   containerd-deadline  a container in StartError now; or, inside the window,
#                        `Failed`/`FailedCreatePodSandBox` events carrying
#                        `context deadline exceeded` or `failed to create shim
#                        task`; or FailedKillPod events at or above KILLPOD_MIN
#                        — containerd's create path starved by teardown churn
#                        (2026-09-02 17:55Z).
#   hook-failure         the ARC Kubernetes hook's `Executing the custom
#                        container implementation failed` in a runner pod's log
#                        inside the window, or a `-workflow` pod Pending longer
#                        than WORKFLOW_PENDING_SECONDS — the CI-visible
#                        signature and its precursor (the hook gives up after
#                        ~13 minutes of the workflow pod not coming up).
#   stale-listener       a scale-set listener pod not Running (or waiting in a
#                        crash loop), or an AutoscalingListener whose
#                        spec.ephemeralRunnerSetName names no existing
#                        EphemeralRunnerSet (the ARC 0.14.2 boot race;
#                        converge-side fix livespec-bde2). Remedy the report
#                        names: delete the AutoscalingListener — the controller
#                        recreates it against the live set within ~30 s.
#
# WHY THESE OBSERVABLES AND NOT THE JOB LOG. The hook-failure string is
# written by the runner, which exits when its job fails, so the pod that
# carries it is usually gone before a sweep runs; the job log lives on
# GitHub, which a node-side scan does not read. Events in the runners
# namespace persist for an hour, a Pending PVC or pod persists until it is
# resolved or deleted, and a StartError container persists until its pod is
# reaped — those are the durable shadows of the same failures, so the scan
# reads them and treats the literal string as a bonus when a runner lingers.
#
# WHY A WINDOW, NOT A LIFETIME COUNT. containerd.log rotates (three gzipped
# generations sat beside a 33 MB live file on 2026-09-02), the k3s journal is
# days deep, and a count-since-forever would either miss rotated lines or
# alarm forever on a stall that ended. Every journal, log and event read here
# is bounded to the last WINDOW; a PVC or pod age is measured from its
# creationTimestamp against a threshold. The containerd.log read walks the
# file BACKWARDS and stops at the first line older than the window, so a
# large file costs only its tail.
#
# WHY REPORT-ONLY, WITH NO --clear. Nothing in this family is safe to delete
# automatically: a Pending PVC is a claim a runner is waiting on, a Pending
# workflow pod is a job in flight, a StartError'd pod is evidence, and the
# stale-listener delete — safe as it is — recreates the listener, which is a
# scale-set-level action an operator should take knowingly. The exit code is
# the interface: 1 with the classes named, so `systemctl is-failed` and the
# journal carry the signal exactly as the wedged-runner sweep's report mode
# does.
#
# FAIL-CLOSED ON ITS OWN INPUTS. A scan that cannot read the journal, the
# containerd log or the cluster exits 2 and says which, rather than reporting
# a clean node it did not look at — the same split the Kueue-webhook probe
# makes between "0 endpoints" (a reading) and "could not read" (not one).
#
# Recurrence is tracked like the wedge scan's: consecutive sweeps with
# findings are counted in STATE_FILE and an ESCALATION line appears once the
# streak reaches ESCALATE_AFTER, so a one-off blip stays quiet and a
# persisting stall gets louder.
#
# Requires: kubectl + KUBECONFIG for the k3s cluster, journalctl with access
# to the k3s unit's journal, and read access to containerd.log (root, on the
# live host — the service runs as root, like the wedge sweep).
set -euo pipefail

USAGE="usage: scan-runner-pod-lifecycle.sh [--window DURATION] [--pvc-pending-seconds N] [--workflow-pending-seconds N] [--killpod-min N] [--containerd-log PATH] [--state-file PATH] [--escalate-after N] [--namespace NS] [--systems-namespace NS]
  DURATION is <N>s, <N>m or <N>h. REPORT-ONLY: prints every lifecycle-stall
  class found on the node with its count and exits 1 if any; exits 0 on a
  clean node; exits 2 when it cannot read one of its inputs."

NAMESPACE="${RPL_NAMESPACE:-arc-runners}"
SYSTEMS_NAMESPACE="${RPL_SYSTEMS_NAMESPACE:-arc-systems}"
# The look-back for journal, log and event reads. Five minutes matches the
# timer, so consecutive sweeps tile the timeline without double-counting.
WINDOW="${RPL_WINDOW:-5m}"
# A healthy provisioner binds a PVC in seconds; 120 s is the provisioner's own
# helper-pod ceiling, past which it has already given up once.
PVC_PENDING_SECONDS="${RPL_PVC_PENDING_SECONDS:-120}"
# The ARC hook abandons a workflow pod after ~13 minutes Pending; 480 s flags
# the precursor while the job can still be saved by the host recovering.
WORKFLOW_PENDING_SECONDS="${RPL_WORKFLOW_PENDING_SECONDS:-480}"
# A few FailedKillPod events per window are ordinary churn on this array; a
# burst is teardown starvation deep enough to reach the create path.
# Calibrated live 2026-09-02: 7-14 in 5 min while the backlog tail drained
# with nothing failing (must stay quiet), 25-27 alongside a PVC Pending 209 s
# (must fire), ~80 when a workflow pod died in StartError at 17:55Z.
KILLPOD_MIN="${RPL_KILLPOD_MIN:-20}"
CONTAINERD_LOG="${RPL_CONTAINERD_LOG:-/var/lib/rancher/k3s/agent/containerd/containerd.log}"
STATE_FILE="${RPL_STATE_FILE:-/var/lib/ci-runner-k3s/runner-pod-lifecycle-streak}"
ESCALATE_AFTER="${RPL_ESCALATE_AFTER:-2}"

HOOK_SIGNATURE='Executing the custom container implementation failed'
BIND_SIGNATURE='binding volumes: context deadline exceeded'
EMFILE_SIGNATURE='failed to create inotify fd'
CREATE_SIGNATURE='context deadline exceeded|failed to create shim task'

while [ $# -gt 0 ]; do
  case "$1" in
    --window)                   WINDOW="${2:?$USAGE}"; shift 2 ;;
    --pvc-pending-seconds)      PVC_PENDING_SECONDS="${2:?$USAGE}"; shift 2 ;;
    --workflow-pending-seconds) WORKFLOW_PENDING_SECONDS="${2:?$USAGE}"; shift 2 ;;
    --killpod-min)              KILLPOD_MIN="${2:?$USAGE}"; shift 2 ;;
    --containerd-log)           CONTAINERD_LOG="${2:?$USAGE}"; shift 2 ;;
    --state-file)               STATE_FILE="${2:?$USAGE}"; shift 2 ;;
    --escalate-after)           ESCALATE_AFTER="${2:?$USAGE}"; shift 2 ;;
    --namespace)                NAMESPACE="${2:?$USAGE}"; shift 2 ;;
    --systems-namespace)        SYSTEMS_NAMESPACE="${2:?$USAGE}"; shift 2 ;;
    -h|--help)                  echo "$USAGE"; exit 0 ;;
    *)                          echo "FATAL: unknown argument '$1'"$'\n'"$USAGE" >&2; exit 2 ;;
  esac
done

for v in PVC_PENDING_SECONDS WORKFLOW_PENDING_SECONDS KILLPOD_MIN ESCALATE_AFTER; do
  [[ "${!v}" =~ ^[0-9]+$ ]] || { echo "FATAL: ${v} must be a non-negative integer, got '${!v}'" >&2; exit 2; }
done
case "$WINDOW" in
  *s) WINDOW_SECONDS="${WINDOW%s}" ;;
  *m) WINDOW_SECONDS=$(( ${WINDOW%m} * 60 )) ;;
  *h) WINDOW_SECONDS=$(( ${WINDOW%h} * 3600 )) ;;
  *)  echo "FATAL: --window must be <N>s, <N>m or <N>h, got '${WINDOW}'" >&2; exit 2 ;;
esac
[[ "$WINDOW_SECONDS" =~ ^[0-9]+$ ]] || { echo "FATAL: --window must be <N>s, <N>m or <N>h, got '${WINDOW}'" >&2; exit 2; }

# Preconditions, fail-closed: a scan that cannot read an input must not report
# a clean node it did not look at.
command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH" >&2; exit 2; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"
command -v journalctl >/dev/null || { echo "FATAL: journalctl not found on PATH" >&2; exit 2; }
journalctl -u k3s -n 1 -q --no-pager >/dev/null 2>&1 || { echo "FATAL: cannot read the k3s unit's journal (run as root or a member of systemd-journal)" >&2; exit 2; }
[ -r "$CONTAINERD_LOG" ] || { echo "FATAL: cannot read ${CONTAINERD_LOG} (run as root, or pass --containerd-log)" >&2; exit 2; }
kubectl get --raw /readyz >/dev/null 2>&1 || { echo "FATAL: the API server is not answering /readyz via ${KUBECONFIG}" >&2; exit 2; }

log() { printf '\n== %s ==\n' "$*"; }

NOW_EPOCH="$(date -u +%s)"
CUTOFF_EPOCH=$(( NOW_EPOCH - WINDOW_SECONDS ))
# RFC 3339 to the second, in UTC: what containerd's `time="..."` field and the
# API's timestamps both sort against lexicographically.
CUTOFF_ISO="$(date -u -d "@${CUTOFF_EPOCH}" +%Y-%m-%dT%H:%M:%S)"

# Seconds since an RFC 3339 timestamp, or the literal `unknown` when it does
# not parse — a missing age must never read as "just now".
age_seconds() {
  local ts="$1" epoch
  [ -n "$ts" ] || { printf 'unknown'; return 0; }
  epoch="$(date -u -d "$ts" +%s 2>/dev/null)" || { printf 'unknown'; return 0; }
  printf '%s' "$(( NOW_EPOCH - epoch ))"
}

# Streak persistence, fail-soft (see ../wedged-runner/scan-wedged-runners.sh):
# losing the escalation signal is a smaller harm than losing the sweep.
read_streak() {
  local value
  if value="$(cat "$STATE_FILE" 2>/dev/null)" && [[ "$value" =~ ^[0-9]+$ ]]; then printf '%s' "$value"; else printf '0'; fi
}
write_streak() {
  mkdir -p "$(dirname "$STATE_FILE")" 2>/dev/null || return 0
  printf '%s\n' "$1" > "$STATE_FILE" 2>/dev/null || return 0
}

# Findings accumulate as `class=count` tokens; DETAIL holds the per-class lines
# printed under the summary. Records use `|` as the field separator for the
# same reason the wedge scan does: empty fields must survive positionally.
FINDINGS=""
DETAIL=""
add_finding() { FINDINGS="${FINDINGS}${1}=${2} "; }
add_detail()  { DETAIL="${DETAIL}${1}
"; }

# ---------------------------------------------------------------------------
log "1. pvc-pending: PVCs in ${NAMESPACE} Pending > ${PVC_PENDING_SECONDS}s"
pvc_hits=0
while IFS='|' read -r name created; do
  [ -n "$name" ] || continue
  age="$(age_seconds "$created")"
  if [ "$age" != unknown ] && [ "$age" -ge "$PVC_PENDING_SECONDS" ]; then
    pvc_hits=$((pvc_hits+1)); add_detail "    pvc=${name} pending_for=${age}s"
  fi
done < <(kubectl -n "$NAMESPACE" get pvc -o jsonpath='{range .items[?(@.status.phase=="Pending")]}{.metadata.name}|{.metadata.creationTimestamp}{"\n"}{end}' 2>/dev/null || true)
echo "  ${pvc_hits} PVC(s) Pending longer than ${PVC_PENDING_SECONDS}s"
[ "$pvc_hits" -gt 0 ] && add_finding pvc-pending "$pvc_hits"

# ---------------------------------------------------------------------------
log "2. bind-deadline: scheduler volume-bind expiries in the k3s journal, last ${WINDOW}"
bind_hits="$(journalctl -u k3s --since "@${CUTOFF_EPOCH}" --no-pager -q 2>/dev/null | grep -c "$BIND_SIGNATURE" || true)"
echo "  ${bind_hits} '${BIND_SIGNATURE}' line(s)"
[ "$bind_hits" -gt 0 ] && add_finding bind-deadline "$bind_hits"

# ---------------------------------------------------------------------------
log "3. inotify-emfile: '${EMFILE_SIGNATURE}' in ${CONTAINERD_LOG}, last ${WINDOW}"
# Walk backwards; stop at the first line whose time= field is older than the
# cutoff. Lines without a time field are neither counted nor treated as old.
# awk's early exit closes the pipe under tac, which then dies of SIGPIPE
# (status 141); that is the bounded read working as intended, not a failure,
# so tac's status is absorbed — otherwise `pipefail` + `set -e` would abort
# the whole sweep on any log longer than the window (it did, live, on a 33 MB
# file on 2026-09-02).
emfile_hits="$({ tac "$CONTAINERD_LOG" 2>/dev/null || true; } | awk -v cut="$CUTOFF_ISO" -v sig="$EMFILE_SIGNATURE" '
  {
    if (match($0, /time="[^"]+"/)) {
      t = substr($0, RSTART + 6, 19)
      if (t < cut) exit
      if (index($0, sig) > 0) c++
    }
  }
  END { print c + 0 }')"
echo "  ${emfile_hits} line(s)"
[ "$emfile_hits" -gt 0 ] && add_finding inotify-emfile "$emfile_hits"

# ---------------------------------------------------------------------------
log "4. containerd-deadline: StartError containers now; create-path deadline events and FailedKillPod bursts, last ${WINDOW}"
starterror_hits=0
while IFS='|' read -r name reasons; do
  [ -n "$name" ] || continue
  case " $reasons " in *" StartError "*) starterror_hits=$((starterror_hits+1)); add_detail "    pod=${name} container StartError";; esac
done < <(kubectl -n "$NAMESPACE" get pods -o jsonpath='{range .items[*]}{.metadata.name}|{range .status.containerStatuses[*]}{.state.terminated.reason}{" "}{end}{"\n"}{end}' 2>/dev/null || true)
create_hits=0; killpod_hits=0
while IFS='|' read -r last_ts event_ts reason object message; do
  [ -n "$reason" ] || continue
  ts="${last_ts:-$event_ts}"
  age="$(age_seconds "$ts")"
  [ "$age" != unknown ] && [ "$age" -le "$WINDOW_SECONDS" ] || continue
  case "$reason" in
    Failed|FailedCreatePodSandBox)
      if printf '%s' "$message" | grep -qE "$CREATE_SIGNATURE"; then
        create_hits=$((create_hits+1)); add_detail "    event=${reason} pod=${object} age=${age}s: $(printf '%s' "$message" | cut -c1-120)"
      fi ;;
    FailedKillPod) killpod_hits=$((killpod_hits+1)) ;;
  esac
done < <(kubectl -n "$NAMESPACE" get events -o jsonpath='{range .items[*]}{.lastTimestamp}|{.eventTime}|{.reason}|{.involvedObject.name}|{.message}{"\n"}{end}' 2>/dev/null || true)
echo "  ${starterror_hits} StartError container(s); ${create_hits} create-path deadline event(s); ${killpod_hits} FailedKillPod event(s) (burst threshold ${KILLPOD_MIN})"
if [ "$starterror_hits" -gt 0 ] || [ "$create_hits" -gt 0 ] || [ "$killpod_hits" -ge "$KILLPOD_MIN" ]; then
  add_finding containerd-deadline "$(( starterror_hits + create_hits + killpod_hits ))"
  [ "$killpod_hits" -ge "$KILLPOD_MIN" ] && add_detail "    FailedKillPod=${killpod_hits} in ${WINDOW} (teardown starvation)"
fi

# ---------------------------------------------------------------------------
log "5. hook-failure: '${HOOK_SIGNATURE}' in runner logs, last ${WINDOW}; -workflow pods Pending > ${WORKFLOW_PENDING_SECONDS}s"
hook_hits=0
for pod in $(kubectl -n "$NAMESPACE" get pods -l app.kubernetes.io/component=runner -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true); do
  # A pod can vanish between the listing and the read; that is churn, not error.
  if kubectl -n "$NAMESPACE" logs "$pod" -c runner --since="$WINDOW" 2>/dev/null | grep -q "$HOOK_SIGNATURE"; then
    hook_hits=$((hook_hits+1)); add_detail "    runner=${pod} logged the ARC hook failure"
  fi
done
wf_hits=0
while IFS='|' read -r name created; do
  [ -n "$name" ] || continue
  case "$name" in *-workflow) ;; *) continue ;; esac
  age="$(age_seconds "$created")"
  if [ "$age" != unknown ] && [ "$age" -ge "$WORKFLOW_PENDING_SECONDS" ]; then
    wf_hits=$((wf_hits+1)); add_detail "    workflow-pod=${name} pending_for=${age}s"
  fi
done < <(kubectl -n "$NAMESPACE" get pods --field-selector=status.phase=Pending -o jsonpath='{range .items[*]}{.metadata.name}|{.metadata.creationTimestamp}{"\n"}{end}' 2>/dev/null || true)
echo "  ${hook_hits} runner log(s) with the hook failure; ${wf_hits} workflow pod(s) Pending longer than ${WORKFLOW_PENDING_SECONDS}s"
[ $(( hook_hits + wf_hits )) -gt 0 ] && add_finding hook-failure "$(( hook_hits + wf_hits ))"

# ---------------------------------------------------------------------------
log "6. stale-listener: listener pods in ${SYSTEMS_NAMESPACE} not Running; AutoscalingListener -> EphemeralRunnerSet references"
listener_hits=0
while IFS='|' read -r name phase waiting; do
  [ -n "$name" ] || continue
  case "$name" in *-listener*) ;; *) continue ;; esac
  if [ "$phase" != Running ] || [ -n "${waiting// /}" ]; then
    listener_hits=$((listener_hits+1)); add_detail "    listener-pod=${name} phase=${phase} waiting=${waiting:-none}"
  fi
done < <(kubectl -n "$SYSTEMS_NAMESPACE" get pods -o jsonpath='{range .items[*]}{.metadata.name}|{.status.phase}|{range .status.containerStatuses[*]}{.state.waiting.reason}{" "}{end}{"\n"}{end}' 2>/dev/null || true)
ers=" $(kubectl -n "$NAMESPACE" get ephemeralrunnerset -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true) "
stale_hits=0
while IFS='|' read -r name ref; do
  [ -n "$name" ] || continue
  case "$ers" in *" ${ref} "*) ;; *)
    stale_hits=$((stale_hits+1)); add_detail "    AutoscalingListener=${name} references EphemeralRunnerSet=${ref:-<empty>} which does not exist (delete the listener; the controller recreates it)";;
  esac
done < <(kubectl -n "$SYSTEMS_NAMESPACE" get autoscalinglistener -o jsonpath='{range .items[*]}{.metadata.name}|{.spec.ephemeralRunnerSetName}{"\n"}{end}' 2>/dev/null || true)
echo "  ${listener_hits} listener pod(s) not Running/healthy; ${stale_hits} stale EphemeralRunnerSet reference(s)"
[ $(( listener_hits + stale_hits )) -gt 0 ] && add_finding stale-listener "$(( listener_hits + stale_hits ))"

# ---------------------------------------------------------------------------
if [ -z "$FINDINGS" ]; then
  write_streak 0
  log "CLEAN. No runner-pod lifecycle stall class present on this node."
  exit 0
fi

STREAK=$(( $(read_streak) + 1 ))
write_streak "$STREAK"

log "RUNNER-POD LIFECYCLE STALL: ${FINDINGS}(consecutive sweeps with findings: ${STREAK})"
printf '%s' "$DETAIL"

if [ "$ESCALATE_AFTER" -gt 0 ] && [ "$STREAK" -ge "$ESCALATE_AFTER" ]; then
  printf '\nESCALATION: lifecycle-stall findings on %s CONSECUTIVE sweeps. The host is failing to bring pods up; this is neither saturation nor a wedged runner, and neither of those remedies applies (see ../README.md "Runner-pod lifecycle stall").\n' "$STREAK"
fi

cat <<'EOF'

REPORT-ONLY. Nothing was changed. What each class means, and where it is
worked: pvc-pending / bind-deadline = the provisioner path (fleet-owned
local-path-provisioner tuning, livespec-sernfh); inotify-emfile = the kernel
watch budget (node-inotify-budget/, ratified in livespec core v216);
containerd-deadline / hook-failure = containerd starved on the storage array
(interim churn-slot cap, NVMe tiering livespec-e2vcqf); stale-listener =
delete the named AutoscalingListener in arc-systems (the controller recreates
it within ~30 s; converge-side fix livespec-bde2). A job that failed with the
ARC hook's "custom container implementation failed" is re-run on the SAME
commit once the class has cleared — it is not a test failure.
EOF
exit 1
