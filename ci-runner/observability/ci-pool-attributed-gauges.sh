#!/usr/bin/env bash
# ci-pool-attributed-gauges.sh — emit the runner pool's queue depth and runner
# population PER REPOSITORY, at a live-board cadence.
#
# WHO READS THESE, UP FRONT (the heartbeat's lesson, livespec-s43svm.20: a
# metric with no named reader is indistinguishable from one that stopped
# being emitted — that heartbeat exited 7 every five minutes for eight days
# and nothing noticed). The reader is the Honeycomb board H2 of the livespec
# plan `ci-runner-pod-lifecycle-reliability` (`livespec-mqy35a`), which
# answers "what is queued or running on the PowerEdge pool, and for which
# repository". No trigger pairs with these gauges: like the sweep's Kueue
# pair they are board inputs, not alarms. The alarms on this pool are the
# ones already under ./triggers/, and none of them reads a metric name this
# script emits (see WHY A SEPARATE NAME FAMILY below).
#
# WHY THIS EXISTS. The runner-pod lifecycle sweep
# (../k3s/phase2/runner-pod-lifecycle/scan-runner-pod-lifecycle.sh,
# `emit_lifecycle_metrics`) already makes the one `kubectl get clusterqueues`
# call that yields a row per queue — and then sums the rows one line before
# the OTLP POST, so `livespec.ci_kueue.pending`, `livespec.ci_kueue.admitted`
# and `livespec.ci_churn_slot.quota_sum` are FLEET SUMS and the queue
# identity is discarded. The EphemeralRunner objects
# (actions.github.com/v1alpha1) carry every per-repository fact and are never
# read for emission at all. So there is no place to see which repository is
# waiting: a saturated pool and one saturated repository look identical.
# Scope 1, 2, 4 and 5 of livespec-i4ahv4 (livespec repo, epic
# livespec-ifwnqj). Scope 3, the per-runner running-job detail, is a
# separate slice and is NOT emitted here.
#
# WHAT IT EMITS. One OTLP/HTTP metrics POST to the host collector's loopback
# receiver (127.0.0.1:4319/v1/metrics — the heartbeat's and the sweep's
# endpoint, JSON shape and curl flags), which the collector exports to the
# `livespec` Honeycomb environment's `metrics` dataset. That environment is a
# Metrics 2.0 environment with ONE metrics dataset, so rows are told apart by
# metric name and attributes, never by dataset. Resource: service.name =
# ci-runner-pool, host.name = $(hostname). Scope name: ci-pool-attributed-gauges.
#
#   livespec.ci_pool.queue_pending   {ci.queue, ci.repository}
#   livespec.ci_pool.queue_admitted  {ci.queue, ci.repository}
#   livespec.ci_pool.queue_quota     {ci.queue, ci.repository}
#       ClusterQueue.status.pendingWorkloads / .admittedWorkloads and the
#       nominalQuota for ci-runner.io/churn-slot, ONE datapoint per queue.
#   livespec.ci_pool.runners         {ci.repository, ci.runner_phase}
#       EphemeralRunner objects across all namespaces, counted by owning
#       repository and phase.
#   livespec.ci_pool.runners_total   (no attributes)
#       the same listing's total — the fleet number the per-repository rows
#       break down.
#
# WHY A SEPARATE NAME FAMILY, and not attributes bolted onto the sweep's
# gauges. The sweep's three fleet sums are attribute-less single datapoints
# that existing queries and the plan's archive-evidence recipe read directly.
# Adding attributed datapoints to those SAME metric names would change what
# an ungrouped query over them returns — the fleet sum would silently become
# a sum over the sum plus every part. `livespec.ci_pool.*` is a new family,
# so every existing query, every archive-evidence number and every trigger
# under ./triggers/ reads exactly what it read before. The sweep is not
# edited by this work at all.
#
# THE ci.repository DERIVATION, and its one exception.
#   For a QUEUE: the pool's ClusterQueues are named `<repository>-cq`, so
#   ci.repository = "thewoolleyman/" + the name with that suffix removed
#   (`livespec-dev-tooling-cq` -> `thewoolleyman/livespec-dev-tooling`). The
#   owner is a constant here because this pool serves one GitHub owner; it is
#   overridable as CI_POOL_REPO_OWNER. ONE queue on the live cluster is NOT a
#   repository — `phase1-proof-cq`, the Kueue proof queue, which is
#   denominated in cpu/memory rather than churn-slot. It is excluded twice
#   over: by the churn-slot filter below, which is the reason the sweep's
#   quota_sum is 32 while all eleven queues' quotas sum to 34, and by the
#   explicit CI_POOL_NON_REPO_QUEUES list, so a future non-repository queue
#   that DID carry churn-slot is still not mangled into a repository name.
#   A queue with no derivable repository is emitted with ci.queue alone —
#   never with a made-up ci.repository.
#
#   For an EPHEMERAL RUNNER: from `spec.githubConfigUrl`, which the
#   EphemeralRunner CRD lists as a REQUIRED spec field (githubConfigSecret,
#   githubConfigUrl, runnerScaleSetId), so it is set at creation and present
#   for every object in every phase. That matters: the sibling
#   `status.jobRepositoryName` is populated only while a job is ASSIGNED, so
#   deriving from it would drop a runner that exists but has not been handed
#   a job — exactly the population a board wants to see. The value is a URL
#   (`https://github.com/thewoolleyman/livespec-dev-tooling`); the repository
#   is its last two path segments. A URL that does not yield two segments
#   (an organization- or enterprise-level scale set) contributes to
#   runners_total but to NO per-repository datapoint, and the omission is
#   logged — a made-up repository would be worse than a gap.
#
# THE CHURN-SLOT FILTER, matched to the sweep's. Only ClusterQueues whose
# resourceGroups contain a resource named `ci-runner.io/churn-slot` are
# emitted, which is byte-for-byte the sweep's test in `emit_lifecycle_metrics`
# (`case "$tok" in "ci-runner.io/churn-slot="*)`) over byte-for-byte the same
# jsonpath. Without it the per-queue rows would not reconcile with
# livespec.ci_churn_slot.quota_sum: the live cluster's eleven queues' quotas
# sum to 34, the ten churn-slot ones to 32, and 32 is what the sweep emits.
#
# FAIL-CLOSED OMISSION, NOT A FALSE ZERO (the split ci-cache-gauges.sh and the
# heartbeat use). A source that cannot be READ emits NOTHING for its gauges
# and makes this script exit non-zero, so the journal is red. A source that
# reads successfully and reports nothing is a genuine reading: an empty
# EphemeralRunner listing on an idle pool emits runners_total=0 and no
# per-repository rows, because there is no repository to attribute to, and
# `pendingWorkloads: 0` on a live queue is emitted as 0. Per-repository rows
# sum to runners_total unless a runner carried no derivable repository, which
# is logged when it happens.
#
# CADENCE. About one minute, on its OWN timer (ci-pool-attributed-gauges.timer),
# deliberately NOT by speeding up the lifecycle sweep: that sweep's journal,
# event and containerd-log reads are sized for 5-minute tiling and consecutive
# sweeps would double-count at a shorter interval. This script makes two
# bounded kubectl list calls and one POST, so a minute is cheap.
#
# CREDENTIAL. Root with the k3s admin kubeconfig, the same
# `Environment=KUBECONFIG=/etc/rancher/k3s/k3s.yaml` the lifecycle sweep's
# unit carries, because it reads the same cluster-scoped ClusterQueues plus
# an all-namespace EphemeralRunner listing. It is a strictly read-only use of
# it; nothing here writes to the cluster.
set -uo pipefail

OTLP_ENDPOINT="${CI_RUNNER_HEARTBEAT_OTLP:-http://127.0.0.1:4319/v1/metrics}"
KUBECTL_BIN="${CI_POOL_KUBECTL:-kubectl}"
KUBECTL_REQUEST_TIMEOUT="${CI_POOL_KUBECTL_REQUEST_TIMEOUT:-15s}"
# The GitHub owner every queue name on this pool is a repository of.
REPO_OWNER="${CI_POOL_REPO_OWNER:-thewoolleyman}"
# Space-separated ClusterQueue names that are NOT repositories. Belt and
# braces beside the churn-slot filter, which already excludes this one.
NON_REPO_QUEUES="${CI_POOL_NON_REPO_QUEUES:-phase1-proof-cq}"
# The resource whose presence marks a ClusterQueue as one of this pool's —
# the sweep's filter, spelled once here.
CHURN_SLOT_RESOURCE="${CI_POOL_CHURN_SLOT_RESOURCE:-ci-runner.io/churn-slot}"

log() { printf 'ci-pool-attributed-gauges: %s\n' "$*"; }

now_ns="$(date +%s%N)"
host_name="$(hostname)"
readings="$(mktemp)"
trap 'rm -f "${readings}"' EXIT
failed=0

# One TSV record per datapoint, read back by the assembler below:
#   <metric-key>\t<value>\t<attr>=<value>[\t<attr>=<value>...]
put() { printf '%s\n' "$*" >> "${readings}"; }

kc() { "${KUBECTL_BIN}" --request-timeout="${KUBECTL_REQUEST_TIMEOUT}" "$@"; }

# ---- ClusterQueues -----------------------------------------------------------
# The sweep's jsonpath verbatim: every resource of every flavor of every
# resource group, as `name=quota` tokens, so the churn-slot test below reads
# the same tokens the sweep tests.
CQ_JSONPATH='{range .items[*]}{.metadata.name}|{range .spec.resourceGroups[*]}{range .flavors[*]}{range .resources[*]}{.name}={.nominalQuota} {end}{end}{end}|{.status.pendingWorkloads}|{.status.admittedWorkloads}{"\n"}{end}'

queue_repository() {  # queue_repository NAME -> repository, or empty
  local name="$1" tok
  for tok in ${NON_REPO_QUEUES}; do
    [ "${name}" = "${tok}" ] && return 0
  done
  case "${name}" in
    *-cq) printf '%s/%s' "${REPO_OWNER}" "${name%-cq}" ;;
    *) ;;
  esac
}

if cq_rows="$(kc get clusterqueues -o jsonpath="${CQ_JSONPATH}" 2>&1)"; then
  queues_emitted=0
  while IFS='|' read -r cq_name cq_quotas cq_pending cq_admitted; do
    [ -n "${cq_name}" ] || continue
    cq_quota=""
    for tok in ${cq_quotas}; do
      case "${tok}" in "${CHURN_SLOT_RESOURCE}="*) cq_quota="${tok#*=}" ;; esac
    done
    # Not one of this pool's queues (phase1-proof-cq is cpu/memory only).
    # This is the filter that makes these rows reconcile with the sweep's
    # livespec.ci_churn_slot.quota_sum.
    [ -n "${cq_quota}" ] || continue
    cq_repo="$(queue_repository "${cq_name}")"
    if [ -z "${cq_repo}" ]; then
      log "ClusterQueue ${cq_name} yields no repository (not <repository>-cq, or listed in CI_POOL_NON_REPO_QUEUES); emitting it with ci.queue alone rather than a made-up ci.repository" >&2
    fi
    cq_attrs="ci.queue=${cq_name}"
    [ -n "${cq_repo}" ] && cq_attrs="${cq_attrs}"$'\t'"ci.repository=${cq_repo}"
    [[ "${cq_quota}" =~ ^[0-9]+$ ]] && put "queue_quota"$'\t'"${cq_quota}"$'\t'"${cq_attrs}"
    [[ "${cq_pending}" =~ ^[0-9]+$ ]] && put "queue_pending"$'\t'"${cq_pending}"$'\t'"${cq_attrs}"
    [[ "${cq_admitted}" =~ ^[0-9]+$ ]] && put "queue_admitted"$'\t'"${cq_admitted}"$'\t'"${cq_attrs}"
    queues_emitted=$((queues_emitted + 1))
  done <<< "${cq_rows}"
  log "read ${queues_emitted} ClusterQueue(s) covering ${CHURN_SLOT_RESOURCE}"
else
  log "could not read ClusterQueues ($(printf '%s' "${cq_rows}" | head -1)); omitting every livespec.ci_pool.queue_* gauge rather than sending false zeros" >&2
  failed=1
fi

# ---- EphemeralRunners --------------------------------------------------------
# spec.githubConfigUrl (a CRD-required spec field) rather than
# status.jobRepositoryName (populated only while a job is assigned), so a
# runner that exists without a job still lands on its repository's row.
ER_JSONPATH='{range .items[*]}{.spec.githubConfigUrl}|{.status.phase}{"\n"}{end}'

if er_rows="$(kc get ephemeralrunners --all-namespaces -o jsonpath="${ER_JSONPATH}" 2>&1)"; then
  er_total=0
  er_unattributed=0
  declare -A er_counts=()
  while IFS='|' read -r er_url er_phase; do
    # A jsonpath range over an empty item list yields nothing; a runner with
    # neither field set would still be a runner, so count on the record, not
    # on the URL.
    [ -n "${er_url}${er_phase}" ] || continue
    er_total=$((er_total + 1))
    # An empty status.phase is a real state (the object exists, its pod has
    # not reported one yet), so it is labelled rather than dropped — the
    # per-phase rows must still sum to the total.
    [ -n "${er_phase}" ] || er_phase="unset"
    # The config URL's PATH, which is <owner>/<repo> for a repository-level
    # scale set and a bare <owner> for an organization- or enterprise-level
    # one. Strip the scheme, then the host, and require exactly two segments —
    # a bare owner must yield no repository rather than be paired with the
    # host name.
    er_repo=""
    er_stripped="${er_url%/}"
    case "${er_stripped}" in
      *://*/*/*)
        er_path="${er_stripped#*://}"   # <host>/<path...>
        er_path="${er_path#*/}"         # <path...>
        case "${er_path}" in
          */*/*) ;;                     # deeper than <owner>/<repo>: not one
          */*) er_repo="${er_path}" ;;
        esac ;;
    esac
    if [ -z "${er_repo}" ]; then
      er_unattributed=$((er_unattributed + 1))
      continue
    fi
    key="${er_repo}"$'\t'"${er_phase}"
    er_counts["${key}"]=$(( ${er_counts["${key}"]:-0} + 1 ))
  done <<< "${er_rows}"
  # A successful listing that found nothing is a genuine zero: ARC scale sets
  # run minRunners 0, so an idle pool has no EphemeralRunner objects at all.
  put "runners_total"$'\t'"${er_total}"$'\t'
  for key in "${!er_counts[@]}"; do
    IFS=$'\t' read -r k_repo k_phase <<< "${key}"
    put "runners"$'\t'"${er_counts[${key}]}"$'\t'"ci.repository=${k_repo}"$'\t'"ci.runner_phase=${k_phase}"
  done
  if [ "${er_unattributed}" -gt 0 ]; then
    log "${er_unattributed} EphemeralRunner(s) carried a spec.githubConfigUrl with no <owner>/<repo> tail (an org- or enterprise-level scale set); they are in runners_total but in no per-repository row" >&2
  fi
  log "read ${er_total} EphemeralRunner(s) across all namespaces"
else
  log "could not read EphemeralRunners ($(printf '%s' "${er_rows}" | head -1)); omitting livespec.ci_pool.runners and .runners_total rather than sending false zeros" >&2
  failed=1
fi

# ---- assemble + POST ---------------------------------------------------------
# Nothing readable at all means nothing to say: POSTing an empty metric list
# would look to the collector like a healthy tick that measured zero.
if [ ! -s "${readings}" ]; then
  log "every source was unreadable; nothing to POST" >&2
  exit 1
fi

payload="$(python3 - "${readings}" "${now_ns}" "${host_name}" <<'PY'
import json, sys

readings_path, now_ns, host = sys.argv[1], sys.argv[2], sys.argv[3]

# metric key -> (OTLP name, unit, description)
SPEC = {
    "queue_pending": (
        "livespec.ci_pool.queue_pending", "{workloads}",
        "Kueue workloads pending admission on ONE ClusterQueue covering "
        "ci-runner.io/churn-slot (the per-queue breakdown of "
        "livespec.ci_kueue.pending)",
    ),
    "queue_admitted": (
        "livespec.ci_pool.queue_admitted", "{workloads}",
        "Kueue workloads admitted and not yet finished on ONE ClusterQueue "
        "covering ci-runner.io/churn-slot (the per-queue breakdown of "
        "livespec.ci_kueue.admitted)",
    ),
    "queue_quota": (
        "livespec.ci_pool.queue_quota", "{slots}",
        "nominalQuota for ci-runner.io/churn-slot on ONE ClusterQueue (the "
        "per-queue breakdown of livespec.ci_churn_slot.quota_sum)",
    ),
    "runners": (
        "livespec.ci_pool.runners", "{runners}",
        "EphemeralRunner objects owned by one repository in one phase; the "
        "repository comes from spec.githubConfigUrl, so a runner with no job "
        "assigned still counts",
    ),
    "runners_total": (
        "livespec.ci_pool.runners_total", "{runners}",
        "EphemeralRunner objects across all namespaces; 0 is a genuine "
        "reading on an idle pool (ARC scale sets run minRunners 0)",
    ),
}

points: dict[str, list[dict[str, object]]] = {}
for line in open(readings_path):
    fields = line.rstrip("\n").split("\t")
    key, value, attr_fields = fields[0], fields[1], fields[2:]
    if key not in SPEC:
        continue
    dp: dict[str, object] = {"timeUnixNano": now_ns, "asInt": str(int(value))}
    attrs = []
    for field in attr_fields:
        if not field:
            continue
        name, _, val = field.partition("=")
        attrs.append({"key": name, "value": {"stringValue": val}})
    if attrs:
        dp["attributes"] = attrs
    points.setdefault(key, []).append(dp)

metrics = []
for key, (name, unit, description) in SPEC.items():
    if key in points:
        metrics.append({
            "name": name, "description": description, "unit": unit,
            "gauge": {"dataPoints": points[key]},
        })

resource_attrs = [
    {"key": "service.name", "value": {"stringValue": "ci-runner-pool"}},
    {"key": "host.name", "value": {"stringValue": host}},
]
print(json.dumps({"resourceMetrics": [{
    "resource": {"attributes": resource_attrs},
    "scopeMetrics": [{
        "scope": {"name": "ci-pool-attributed-gauges"},
        "metrics": metrics,
    }],
}]}))
print(sum(len(p) for p in points.values()), file=sys.stderr)
PY
)" || {
  log "could not assemble the OTLP payload from the readings; nothing POSTed" >&2
  exit 1
}

if ! curl --silent --show-error --fail --max-time 10 -X POST "${OTLP_ENDPOINT}" \
     -H 'Content-Type: application/json' -d "${payload}" > /dev/null; then
  log "POST to ${OTLP_ENDPOINT} failed" >&2
  exit 7
fi

log "posted $(wc -l < "${readings}") datapoint(s) -> ${OTLP_ENDPOINT} (host.name=${host_name})"
exit "${failed}"
