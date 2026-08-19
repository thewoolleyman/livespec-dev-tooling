#!/usr/bin/env bash
# scan-wedged-runners.sh — find ARC runner pods that are alive to Kubernetes
# but permanently dead to GitHub, and (opt-in) delete them.
#
# THE FAILURE THIS DETECTS. A `gha-runner-scale-set` runner pod can reach a
# state where its GitHub registration has been invalidated server-side while
# the process keeps running. The runner does not exit; it loops forever:
#
#     [RUNNER ... INFO BrokerMessageListener] Retriable exception:
#       Registration <uuid> was not found.
#     [RUNNER ... INFO BrokerMessageListener] Reload credentials.
#     [RUNNER ... INFO BrokerMessageListener] Connection to Broker Server recreated.
#     [RUNNER ... INFO BrokerMessageListener] Sleeping for 55.7 seconds before retrying.
#
# To Kubernetes that pod is `Running` with `ready=true`, so ARC counts it as a
# live runner. The listener then computes `"assigned job"=1 decision=1
# currentRunnerCount=1` — "we already have enough runners" — re-patches
# `replicas=1` every ~50s, and never creates a pod that could take the queued
# job. A dead runner occupies the scale set's accounting and suppresses the
# very scale-up that would replace it. Observed live 2026-08-19 on TWO scale
# sets at once (`livespec-s43svm.30`); one of them held a merge gate for 33+
# minutes.
#
# WHY THIS NEEDS ITS OWN DETECTOR. The condition is invisible to every capacity
# signal this fleet already watches — pod phase `Running`, readiness `true`,
# Kueue zero gated and zero pending, node allocatable with headroom. It
# presents EXACTLY like pool saturation (jobs queued, nothing starting) and has
# the OPPOSITE fix: adding capacity cannot clear a wedge, and two separate
# triage sessions misrouted toward capacity tuning before the real cause was
# found. That conflation is the defect; see ../README.md "Wedged runner vs.
# saturation" for the operator-facing discrimination procedure.
#
# WHY THE LOG LINE IS A SUFFICIENT SIGNAL, with no GitHub API call: the runner
# emits it only after the broker has told it its own registration does not
# exist, and it never recovers from that — it has no code path that
# re-registers. A pod in this loop can never claim work, so the string plus a
# recency window is certainty, not a heuristic.
#
# WHY DELETING IS SAFE BY CONSTRUCTION. Scale-set runner pods are EPHEMERAL:
# one pod serves at most one job and ARC replaces a deleted one within seconds.
# A wedged pod is additionally incapable of holding work at all. Deletion is
# nonetheless OPT-IN (`--clear`), and even then this script refuses to delete a
# pod that has a live `<pod>-workflow` companion — a companion means the hook
# created a workflow pod for it, i.e. it really did claim a job, which no
# wedged runner can do. That guard makes a false positive non-destructive
# rather than merely unlikely.
#
# KNOWN LIMITATION — WHAT AUTOMATIC CLEARING HIDES. Running this on a timer in
# --clear mode absorbs recurrences silently. That is the point when the wedge is
# rare, and it is a hazard when it is not: if whatever causes wedging gets worse,
# an unattended sweep will delete pods every five minutes forever and nothing
# says the condition escalated. That is the same invisible-signal failure this
# script exists to fix, reintroduced one level up — and it matters more than
# usual because the TRIGGER IS STILL UNKNOWN (livespec-s43svm.30; the leading
# hypothesis is Kueue gating delay under oversubscription, see ../README.md).
#
# The mitigation here is deliberately small: the script remembers whether the
# PREVIOUS run also found wedged pods, and prints a distinct ESCALATION line
# naming the streak length when findings repeat across consecutive runs. A
# one-off wedge stays quiet; a recurring one gets progressively louder in the
# journal. The streak is tracked in BOTH modes, because repeated FINDINGS are
# the signal — clearing them is not what makes the recurrence interesting.
#
# This is a journal-visible signal, not a routed alert. Wiring it into the fleet
# attention surface is tracked separately; until then, an operator reading
# `journalctl -u scan-wedged-runners.service` sees the escalation, and nothing
# pages anyone.
#
# Requires: kubectl and a KUBECONFIG for the k3s cluster (see ../../provision-k3s.sh).
set -euo pipefail

USAGE="usage: scan-wedged-runners.sh [--clear] [--namespace NS] [--window DURATION] [--min-hits N] [--min-age-seconds N] [--state-file PATH] [--escalate-after N]
  (default is REPORT-ONLY: it prints what it would delete and exits 1 if any
   wedged pod is found, so it is usable directly as a check)"

NAMESPACE="${WEDGED_RUNNER_NAMESPACE:-arc-runners}"
# The log window. A wedged pod re-emits the signature every ~55s, so a window
# of several minutes sees it many times over while keeping the per-pod log
# fetch small on a busy runner.
WINDOW="${WEDGED_RUNNER_WINDOW:-6m}"
# Occurrences required INSIDE that window. The loop guarantees ~6 per 6
# minutes; requiring more than one is what separates the permanent loop from a
# single transient broker hiccup that the runner rode out.
MIN_HITS="${WEDGED_RUNNER_MIN_HITS:-2}"
# Grace period after pod start. A pod younger than this has not had time to
# accumulate MIN_HITS anyway, and skipping it keeps normal churn quiet.
MIN_AGE_SECONDS="${WEDGED_RUNNER_MIN_AGE_SECONDS:-180}"
# Where the consecutive-findings streak is remembered across runs (see this
# script's "KNOWN LIMITATION" header). /var/lib is the right home for state a
# systemd oneshot accumulates; an interactive non-root run simply cannot write
# there, and the script degrades to not tracking rather than failing.
STATE_FILE="${WEDGED_RUNNER_STATE_FILE:-/var/lib/ci-runner-k3s/wedged-runner-streak}"
# Consecutive finding runs before the ESCALATION line appears. 2 is the
# smallest value that means "this recurred" rather than "this happened".
ESCALATE_AFTER="${WEDGED_RUNNER_ESCALATE_AFTER:-2}"
CLEAR=0

# The registration-not-found signature. Deliberately matched on the stable
# prose either side of the volatile registration uuid.
SIGNATURE='Registration .* was not found'

while [ $# -gt 0 ]; do
  case "$1" in
    --clear)            CLEAR=1; shift ;;
    --namespace)        NAMESPACE="${2:?$USAGE}"; shift 2 ;;
    --window)           WINDOW="${2:?$USAGE}"; shift 2 ;;
    --min-hits)         MIN_HITS="${2:?$USAGE}"; shift 2 ;;
    --min-age-seconds)  MIN_AGE_SECONDS="${2:?$USAGE}"; shift 2 ;;
    --state-file)       STATE_FILE="${2:?$USAGE}"; shift 2 ;;
    --escalate-after)   ESCALATE_AFTER="${2:?$USAGE}"; shift 2 ;;
    -h|--help)          echo "$USAGE"; exit 0 ;;
    *)                  echo "FATAL: unknown argument '$1'"$'\n'"$USAGE" >&2; exit 2 ;;
  esac
done

[[ "$ESCALATE_AFTER" =~ ^[0-9]+$ ]] || { echo "FATAL: --escalate-after must be a non-negative integer, got '${ESCALATE_AFTER}'" >&2; exit 2; }
[[ "$MIN_HITS" =~ ^[0-9]+$ ]] || { echo "FATAL: --min-hits must be a non-negative integer, got '${MIN_HITS}'" >&2; exit 2; }
[[ "$MIN_AGE_SECONDS" =~ ^[0-9]+$ ]] || { echo "FATAL: --min-age-seconds must be a non-negative integer, got '${MIN_AGE_SECONDS}'" >&2; exit 2; }

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH" >&2; exit 2; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"

log() { printf '\n== %s ==\n' "$*"; }

# Streak persistence. Both helpers are FAIL-SOFT by design: an unwritable or
# unreadable state file must degrade this script to "does not track recurrence",
# never to "does not detect wedged runners". Losing the escalation signal is a
# smaller harm than losing the sweep, so nothing here is allowed to abort.
read_streak() {
  local value
  if value="$(cat "$STATE_FILE" 2>/dev/null)" && [[ "$value" =~ ^[0-9]+$ ]]; then
    printf '%s' "$value"
  else
    printf '0'
  fi
}

write_streak() {
  local value="$1"
  mkdir -p "$(dirname "$STATE_FILE")" 2>/dev/null || return 0
  printf '%s\n' "$value" > "$STATE_FILE" 2>/dev/null || return 0
}

# ---------------------------------------------------------------------------
log "1. Enumerate Running runner pods in namespace ${NAMESPACE}"

# `app.kubernetes.io/component=runner` is the chart's own label on runner pods.
# It is a stronger filter than a `-workflow` name-suffix test, because the
# hook-created WORKFLOW pods carry only a `runner-pod` label and so cannot
# match this selector at all — verified live 2026-08-19. Their logs are the
# job's own output, which can legitimately contain anything, including this
# script's signature quoted in a test fixture.
PODS="$(kubectl get pods -n "$NAMESPACE" \
  -l app.kubernetes.io/component=runner \
  --field-selector=status.phase=Running \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.labels.actions\.github\.com/scale-set-name}{"\t"}{.status.startTime}{"\t"}{.metadata.deletionTimestamp}{"\n"}{end}')"

if [ -z "$PODS" ]; then
  write_streak 0
  log "No Running runner pods. Nothing to scan."
  exit 0
fi
printf '%s\n' "$PODS" | while IFS=$'\t' read -r name scaleset _; do
  printf '  %-52s %s\n' "$name" "${scaleset:-<no-scale-set-label>}"
done

# ---------------------------------------------------------------------------
log "2. Scan each pod's last ${WINDOW} of runner log for: ${SIGNATURE}"

NOW_EPOCH="$(date -u +%s)"
WEDGED=""   # newline-separated "name<TAB>scaleset<TAB>age_seconds<TAB>hits<TAB>busy"

while IFS=$'\t' read -r name scaleset start_time deletion_time; do
  [ -n "$name" ] || continue

  # A pod being deleted keeps phase `Running` for its whole termination grace
  # period, so without this it is re-flagged on every sweep until it actually
  # disappears. That would inflate the consecutive-findings streak with a pod
  # already dealt with, which is precisely the signal the streak must not lie
  # about — and in --clear mode it also re-issues a delete for a pod already
  # terminating.
  if [ -n "$deletion_time" ]; then
    printf '  %-52s SKIP (already terminating since %s)\n' "$name" "$deletion_time"
    continue
  fi

  start_epoch="$(date -u -d "$start_time" +%s 2>/dev/null || echo "$NOW_EPOCH")"
  age=$(( NOW_EPOCH - start_epoch ))
  if [ "$age" -lt "$MIN_AGE_SECONDS" ]; then
    printf '  %-52s SKIP (age %ss < %ss grace)\n' "$name" "$age" "$MIN_AGE_SECONDS"
    continue
  fi

  # A pod can terminate between the listing and the log fetch; that is normal
  # churn, not an error, so a failed fetch means "nothing observed" rather than
  # aborting the sweep over every remaining pod.
  if ! pod_log="$(kubectl logs -n "$NAMESPACE" "$name" -c runner --since="$WINDOW" 2>/dev/null)"; then
    printf '  %-52s SKIP (log unavailable -- pod likely terminating)\n' "$name"
    continue
  fi

  hits="$(printf '%s\n' "$pod_log" | grep -c -E "$SIGNATURE" || true)"
  if [ "$hits" -lt "$MIN_HITS" ]; then
    printf '  %-52s ok (%s/%s signature hits)\n' "$name" "$hits" "$MIN_HITS"
    continue
  fi

  # The false-positive backstop described in this script's header: a runner
  # with a live workflow companion demonstrably claimed a job, which a wedged
  # runner cannot do.
  busy=no
  if kubectl get pod -n "$NAMESPACE" "${name}-workflow" >/dev/null 2>&1; then
    busy=yes
  fi

  printf '  %-52s WEDGED (%s hits, age %ss, workflow-companion=%s)\n' "$name" "$hits" "$age" "$busy"
  WEDGED="${WEDGED}${name}	${scaleset}	${age}	${hits}	${busy}
"
done <<< "$PODS"

# ---------------------------------------------------------------------------
if [ -z "$WEDGED" ]; then
  write_streak 0
  log "CLEAN. No wedged runner pods in namespace ${NAMESPACE}."
  exit 0
fi

STREAK=$(( $(read_streak) + 1 ))
write_streak "$STREAK"

log "3. WEDGED RUNNER PODS FOUND (consecutive runs with findings: ${STREAK})"
printf '%s' "$WEDGED" | while IFS=$'\t' read -r name scaleset age hits busy; do
  [ -n "$name" ] || continue
  printf '  pod=%s scale-set=%s age=%ss hits=%s workflow-companion=%s\n' \
    "$name" "${scaleset:-<unknown>}" "$age" "$hits" "$busy"
done

# The one line an operator should grep for. A single wedge is routine and this
# stays silent; a wedge that keeps coming back means the underlying condition
# is escalating, which no amount of successful clearing makes less true.
if [ "$ESCALATE_AFTER" -gt 0 ] && [ "$STREAK" -ge "$ESCALATE_AFTER" ]; then
  printf '\nESCALATION: wedged runners found on %s CONSECUTIVE sweeps. Clearing them is treating the symptom -- the underlying condition is recurring, and its trigger is not yet known (livespec-s43svm.30). Investigate rather than relying on the sweep.\n' "$STREAK"
fi

if [ "$CLEAR" -eq 0 ]; then
  cat <<'EOF'

REPORT-ONLY. Nothing was deleted. Each pod above is permanently unable to
accept work AND is suppressing its scale set's scale-up, so the scale set
cannot recover on its own. Re-run with --clear to delete them, or delete one
by hand:

    kubectl delete pod -n arc-runners <pod-name>

ARC creates a replacement within seconds; a job that was queued against that
scale set is claimed by the replacement. Adding capacity will NOT clear this
-- see ../README.md "Wedged runner vs. saturation".
EOF
  exit 1
fi

log "4. --clear: deleting wedged runner pods"
DELETE_FAILED=0
while IFS=$'\t' read -r name scaleset age hits busy; do
  [ -n "$name" ] || continue
  if [ "$busy" = yes ]; then
    echo "  REFUSING to delete ${name}: it has a live ${name}-workflow companion, so it claimed a job and cannot be wedged. Investigate by hand."
    DELETE_FAILED=1
    continue
  fi
  if kubectl delete pod -n "$NAMESPACE" "$name" --wait=false; then
    echo "  deleted ${name} (scale-set ${scaleset:-<unknown>})"
  else
    echo "  FAILED to delete ${name}"
    DELETE_FAILED=1
  fi
done <<< "$WEDGED"

if [ "$DELETE_FAILED" -ne 0 ]; then
  log "DONE WITH FAILURES. At least one wedged pod was not cleared; see above."
  exit 1
fi

log "DONE. Every wedged pod cleared; ARC recreates replacements within seconds."
