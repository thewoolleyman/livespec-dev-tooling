#!/usr/bin/env bash
# gate-repro.sh — run ONE diagnosed reproduction gate Job and keep its evidence
# on this host (livespec-dev-tooling-pkmxgu, the reproduction route for the
# gamingpc-xubuntu full-suite gate hang, livespec-dev-tooling-ddy5xu).
#
# Usage (from a livespec-dev-tooling checkout, on a host that can delegate):
#   just gate-repro <repo-root> [--queue gates-repro-lq] [--interval 300]
#                               [--out DIR]
#
# WHAT IT DOES.
#   1. Submits one gate Job for <repo-root>'s committed tree through the normal
#      gate client, `python -m livespec_dev_tooling.gate_repro`: the mirror push,
#      a `kubectl create` of the rendered Job, the admission and terminal waits,
#      and the delete of a Job the client stops waiting for. NEVER a hand
#      `kubectl create` or `apply`, which fleet_host_guard refuses. The Job goes
#      onto --queue, by default gates-repro-lq
#      (../kueue/cluster-queue-repro-gates.yaml, one gate unit on gamingpc-xubuntu),
#      so the held gates-cq lane stays held for every other gate.
#   2. Renders it with the renderer's stack diagnostics every --interval seconds:
#      the pod's log carries the process tree and each live Python process's
#      latest stack (render-gate-job.sh --repro-stack-interval).
#   3. Every --interval seconds, writes the Job's full container log and its
#      status to <out>/log-<UTC>.txt and <out>/job-<UTC>.json on THIS host. The
#      client streams a Job's log only after the Job reaches a terminal
#      condition, and it deletes a Job that reaches none, taking the log with it
#      (`.ai/deleted-gate-pod-diagnosis.md`), so this capture is the evidence
#      that survives a hang.
#   4. Ends when the client ends: the Job reached a terminal condition, or the
#      client stopped waiting (its poll budget is 3600 s from admission) and
#      deleted it. <out>/ending.txt records which, with the client's own line.
#
# Exit status is the client's: 0 Complete, 1 Failed, 3 no terminal condition.
#
# THE RENDERER IS THIS CHECKOUT'S, passed explicitly: the repository under test
# usually installs an older livespec-dev-tooling whose packaged renderer has
# neither --queue nor --repro-stack-interval.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLING_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
RENDERER="${SCRIPT_DIR}/render-gate-job.sh"

repo_root=""; queue="gates-repro-lq"; interval="300"; out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) repo_root="$2"; shift 2 ;;
    --queue)     queue="$2"; shift 2 ;;
    --interval)  interval="$2"; shift 2 ;;
    --out)       out="$2"; shift 2 ;;
    *) echo "FATAL: unknown argument $1" >&2; exit 2 ;;
  esac
done
[ -n "${repo_root}" ] || { echo "FATAL: --repo-root is required" >&2; exit 2; }
repo_root="$(cd "${repo_root}" && pwd)"
case "${interval}" in
  "" | *[!0-9]* | 0*) echo "FATAL: --interval '${interval}' is not a positive whole number of seconds" >&2; exit 2 ;;
esac
# The capture loop fires SLACK seconds early (see the loop below), so an interval
# no longer than that would capture on every tick.
SLACK=15
if [ "${interval}" -le $((SLACK * 2)) ]; then
  echo "FATAL: --interval '${interval}' must exceed $((SLACK * 2)) seconds" >&2
  exit 2
fi

tree="$(git -C "${repo_root}" rev-parse 'HEAD^{tree}')"
started="$(date -u +%Y%m%dT%H%M%SZ)"
# RFC3339, the form a Job's metadata.creationTimestamp takes, so the two compare
# as strings: a Job created before this run started is never this run's Job.
started_rfc3339="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
[ -n "${out}" ] || out="${TOOLING_ROOT}/tmp/gate-repro/${started}-$(basename "${repo_root}")"
mkdir -p "${out}"
{
  echo "repo_root=${repo_root}"
  echo "head=$(git -C "${repo_root}" rev-parse HEAD)"
  echo "tree=${tree}"
  echo "queue=${queue}"
  echo "interval=${interval}"
  echo "started=${started}"
} > "${out}/run.txt"
echo ":: gate-repro: evidence directory ${out}"

# EVERY cluster call here is bounded. An unbounded read that hangs would stop
# the captures, and the captures are the only evidence a hung Job leaves.
kubectl_gates() { with-gates-kubeconfig kubectl --request-timeout=30s --namespace gates "$@"; }

capture() {
  local stamp job
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  # THIS run's Job: the NEWEST Job of this tree on this queue created since the
  # run started. A finished same-tree Job is kept for its
  # ttlSecondsAfterFinished, so the first name in the list could be an earlier
  # run's.
  job="$(kubectl_gates get jobs \
          --selector "kueue.x-k8s.io/queue-name=${queue},livespec.gate/tree-hash=${tree}" \
          --output 'jsonpath={range .items[*]}{.metadata.creationTimestamp} {.metadata.name}{"\n"}{end}' \
          2>>"${out}/capture-errors.txt" |
        awk -v since="${started_rfc3339}" '$1 >= since' | sort | tail -n 1 | awk '{ print $2 }' || true)"
  if [ -z "${job}" ]; then
    echo "${stamp} no Job of tree ${tree} on queue ${queue} created since ${started_rfc3339}" >> "${out}/capture-errors.txt"
    return 0
  fi
  echo "${job}" > "${out}/job-name.txt"
  kubectl_gates get job "${job}" --output json > "${out}/job-${stamp}.json" 2>>"${out}/capture-errors.txt" || true
  kubectl_gates logs "job/${job}" --all-containers --tail=-1 > "${out}/log-${stamp}.txt" 2>&1 || true
  echo ":: gate-repro: ${stamp} captured $(wc -l < "${out}/log-${stamp}.txt") log lines of ${job}"
}

( cd "${TOOLING_ROOT}" && exec mise exec -- uv run python -m livespec_dev_tooling.gate_repro \
    --repo-root "${repo_root}" --renderer "${RENDERER}" \
    --queue "${queue}" --stack-interval "${interval}" ) > "${out}/client.log" 2>&1 &
client=$!

# FIRES SLACK SECONDS EARLY: the loop wakes every 10 s and a capture takes time,
# so a capture triggered at >= interval would land after it. Triggered at
# >= interval - SLACK, two capture STARTS are at most interval - 5 s apart,
# which keeps "at least once every <interval> seconds" true.
last=0
while kill -0 "${client}" 2>/dev/null; do
  now="$(date +%s)"
  if [ $((now - last)) -ge $((interval - SLACK)) ]; then
    capture
    last="${now}"
  fi
  sleep 10
done
set +e
wait "${client}"
status=$?
set -e
# One last read: a Job that reached a terminal condition is kept for its
# ttlSecondsAfterFinished, so its complete log is still there to take.
capture
{
  echo "ended_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "client_exit=${status}"
  grep '^gate-repro: ended=' "${out}/client.log" || echo "gate-repro: the client printed no ending line; read client.log"
} > "${out}/ending.txt"
cat "${out}/ending.txt"
exit "${status}"
