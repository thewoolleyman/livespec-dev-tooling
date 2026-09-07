#!/usr/bin/env bash
# ci-pool-attributed-gauges.sh — emit the runner pool's queue depth and runner
# population PER REPOSITORY, at a live-board cadence.
#
# WHO READS THESE, UP FRONT (the heartbeat's lesson, livespec-s43svm.20: a
# metric with no named reader is indistinguishable from one that stopped
# being emitted — that heartbeat exited 7 every five minutes for eight days
# and nothing noticed). The reader is the Honeycomb board named "CI runner
# pool — PowerEdge: queued, admitted and running by repository", which
# answers "what is queued or running on the PowerEdge pool, and for which
# repository". That board is code, not a hand-built page: its definition is
# ./boards/ci-runner-pool.json and ./boards/apply-boards.sh converges it by
# name (board H2 of the livespec plan `ci-runner-pod-lifecycle-reliability`,
# `livespec-mqy35a`). Its first two panels read the gauges below and its
# last reads the wide events further down; see ./README.md for which panel
# reads which dataset. No trigger pairs with these gauges: like the sweep's Kueue
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
# livespec-ifwnqj), and — since the running-jobs slice — its scope 3 as
# well: the per-runner running-job detail, emitted as WIDE EVENTS beside
# the gauges (see WHAT IT EMITS AS EVENTS below).
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
# WHAT IT EMITS AS EVENTS, and why events rather than more gauges. Scope 3
# of livespec-i4ahv4 asks for the jobs RUNNING NOW with per-runner detail:
# repository, workflow ref, run id, job name, phase and age. That is a row
# per runner per tick, and its two most useful columns — the run id and the
# job name — are unbounded high-cardinality identifiers. As gauge ATTRIBUTES
# they would multiply this pool's time series by every workflow run it ever
# serves, to carry a value (1) that says nothing; as a WIDE EVENT each row is
# ONE record with every field on it, which is the shape a Honeycomb table and
# BubbleUp actually read. So the running-job detail is emitted as OTLP LOGS,
# one record per runner carrying a job assignment, in a SECOND POST to the
# same collector on the same port: 127.0.0.1:4319/v1/logs.
#
# THE DATASET IS CHOSEN BY service.name, NOT BY A HEADER. The host collector
# (thewoolleyman/otel-collector config.ci-runner-host.yaml) wires a `logs`
# pipeline — receivers [otlp], exporters [otlp/honeycomb_livespec] — through
# the SAME exporter the metrics pipeline uses, and that exporter sets no
# x-honeycomb-dataset header, so traces and logs auto-route by service.name.
# Choosing the events dataset therefore IS choosing service.name: these
# records carry service.name = ci-runner-pool, so they land in the `livespec`
# environment's `ci-runner-pool` dataset — the name livespec-i4ahv4 named,
# and the one the plan's board H2 (`livespec-mqy35a`) reads as a table. It
# keeps both halves of this ONE emitter under one service identity with no
# collision: the gauges land in the env's single Metrics 2.0 `metrics`
# dataset whatever their service.name is.
#
#   ci-runner-pool (events dataset)  one record per runner that carries a
#       job assignment, per tick, with attributes ci.repository (owner/repo),
#       ci.workflow_ref, ci.run_id, ci.job_name, ci.runner_phase,
#       ci.runner_name, ci.runner_namespace and ci.runner_age_s.
#
# WHICH RUNNERS GET A ROW, and why not only the Running ones. A row is
# emitted for every runner whose listing carries at least ONE of the four
# job-assignment fields; a runner with none of them has no job and is a
# POPULATION fact the gauges above already carry, not a running job. The row
# is deliberately NOT filtered to phase Running: a job wedged in Pending or
# gone to Failed is exactly what an operator needs to see, so the phase rides
# the record as an attribute the board filters on rather than as a condition
# this emitter applies and cannot be asked about later. An attribute whose
# field is empty is OMITTED from the record rather than sent as an empty
# string — the gauges' fail-closed rule, applied per attribute.
#
# NO EVENTS IS NOT A DEAD EMITTER. An idle pool produces no rows and this
# script POSTs no logs payload at all, which for a board asking "what is
# running now" is the answer rather than a gap. The emitter's own liveness is
# carried by the gauge half — livespec.ci_pool.runners_total is emitted every
# tick, 0 included — so the events dataset needs no heartbeat row to be told
# apart from a broken emitter (the livespec-s43svm.20 lesson, discharged once
# per emitter rather than once per signal).
#
# ONE LISTING, TWO SIGNALS, TWO DIFFERENT REPOSITORY FIELDS — DELIBERATELY.
# The gauges and the events come from the SAME
# `kubectl get ephemeralrunners --all-namespaces` call, widened to carry the
# job fields, so scope 3 costs no additional API request per tick. But they
# derive ci.repository from DIFFERENT fields, and unifying them would break
# one or the other:
#   * the GAUGES use spec.githubConfigUrl, a CRD-REQUIRED spec field present
#     in every phase, so an IDLE runner still lands on its repository's row.
#     status.jobRepositoryName would silently drop every idle runner — the
#     population a board most wants to see.
#   * the EVENTS use status.jobRepositoryName, because the row exists only
#     while a job is assigned and that field names the repository the job
#     actually belongs to. It is already `owner/repo` and needs no
#     derivation, so it cannot be mangled the way a URL tail can.
#   Do NOT "unify" them.
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
# The SAME collector and the SAME port, the logs signal's path — the host's
# `logs` pipeline receives on the otlp receiver the metrics POST already uses
# (see THE DATASET IS CHOSEN BY service.name above). Spelled out rather than
# derived from OTLP_ENDPOINT by string surgery, so either can be pointed
# somewhere else without silently dragging the other along.
OTLP_LOGS_ENDPOINT="${CI_POOL_OTLP_LOGS:-http://127.0.0.1:4319/v1/logs}"
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
# The EphemeralRunner listing's raw rows, kept so the events assembler reads
# the SAME bytes the count loop below reads — one listing, two readers.
runners_raw="$(mktemp)"
trap 'rm -f "${readings}" "${runners_raw}"' EXIT
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
# ONE listing feeds BOTH signals (see ONE LISTING, TWO SIGNALS above): the
# per-repository/per-phase COUNTS in this loop, which derive the repository
# from spec.githubConfigUrl (a CRD-required spec field) so a runner that
# exists without a job still lands on its repository's row, and the
# per-runner running-job EVENTS assembled further down, which derive it from
# status.jobRepositoryName because their row exists only while a job does.
#
# FIELD ORDER IS LOAD-BEARING. Every field but the last is structurally
# constrained — two Kubernetes names, an RFC 3339 timestamp, a URL, a phase,
# an `owner/repo`, a workflow ref, a numeric run id — and so cannot contain
# the `|` separator. status.jobDisplayName is free text written by a workflow
# author, so it goes LAST, where both readers absorb the whole remainder of
# the line into it and an embedded `|` cannot shift any other field.
ER_JSONPATH='{range .items[*]}{.metadata.namespace}|{.metadata.name}|{.metadata.creationTimestamp}|{.spec.githubConfigUrl}|{.status.phase}|{.status.jobRepositoryName}|{.status.jobWorkflowRef}|{.status.workflowRunId}|{.status.jobDisplayName}{"\n"}{end}'

if er_rows="$(kc get ephemeralrunners --all-namespaces -o jsonpath="${ER_JSONPATH}" 2>&1)"; then
  printf '%s\n' "${er_rows}" > "${runners_raw}"
  er_total=0
  er_unattributed=0
  declare -A er_counts=()
  # Field order per ER_JSONPATH above; this loop needs only the phase and the
  # config URL, so the namespace, the name (read solely as the record's
  # existence test) and the four job fields are discarded into `_`. The
  # events assembler reads the same rows for the rest.
  while IFS='|' read -r _ er_name _ er_url er_phase _; do
    # A jsonpath range over an empty item list yields nothing. Count on
    # metadata.name, which every object has: a line carrying no name is not
    # an object, and counting it would inflate runners_total.
    [ -n "${er_name}" ] || continue
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

post_failed=0
if curl --silent --show-error --fail --max-time 10 -X POST "${OTLP_ENDPOINT}" \
     -H 'Content-Type: application/json' -d "${payload}" > /dev/null; then
  log "posted $(wc -l < "${readings}") datapoint(s) -> ${OTLP_ENDPOINT} (host.name=${host_name})"
else
  # Deliberately no longer an immediate exit: the events POST below carries a
  # DIFFERENT signal derived from the same listing, and a collector that
  # rejected the metrics payload has said nothing about whether it would take
  # the events one. The exit status is still 7, at the bottom.
  log "POST to ${OTLP_ENDPOINT} failed" >&2
  post_failed=7
fi

# ---- running-job events ------------------------------------------------------
# One wide event per runner carrying a job assignment, POSTed to the same
# collector's logs path (see WHAT IT EMITS AS EVENTS in the header). The rows
# are the ones the count loop above already read; nothing is listed twice.
if [ ! -s "${runners_raw}" ]; then
  log "no EphemeralRunner listing to derive running-job events from; none POSTed" >&2
else
  events_rc=0
  # stdout is the record COUNT on line 1 and the OTLP payload on line 2.
  events_out="$(python3 - "${runners_raw}" "${now_ns}" "${host_name}" <<'PY'
import json
import sys
from datetime import datetime, timezone

raw_path, now_ns, host = sys.argv[1], sys.argv[2], sys.argv[3]
now_epoch = int(now_ns) / 1_000_000_000

# ER_JSONPATH's field order, spelled once. jobDisplayName is LAST because it
# is the only free-text field, so the bounded split below hands it the whole
# remainder of the line and an embedded "|" cannot shift another field.
FIELDS = (
    "namespace", "name", "created", "config_url", "phase",
    "job_repository", "job_workflow_ref", "run_id", "job_name",
)

# The four fields populated only while a job is ASSIGNED. A runner carrying
# none of them has no job: it is a population fact the gauges already emit,
# not a running job, so it gets no row.
JOB_FIELDS = ("job_repository", "job_workflow_ref", "run_id", "job_name")

# Attribute name -> field. ci.repository here is status.jobRepositoryName,
# already owner/repo -- NOT the gauges' spec.githubConfigUrl derivation; the
# two are different on purpose (see the script header). ci.run_id is a STRING
# attribute although its value is numeric: it is an identifier to group and
# filter by, never a quantity to sum or average.
ATTRIBUTES = (
    ("ci.repository", "job_repository"),
    ("ci.workflow_ref", "job_workflow_ref"),
    ("ci.run_id", "run_id"),
    ("ci.job_name", "job_name"),
    ("ci.runner_phase", "phase"),
    ("ci.runner_name", "name"),
    ("ci.runner_namespace", "namespace"),
)


def age_seconds(stamp: str) -> int | None:
    """Whole seconds since metadata.creationTimestamp, or None if unreadable.

    Unreadable means the attribute is OMITTED, never sent as 0 -- a runner
    reported as brand new when its age is unknown would be a false reading.
    """
    if not stamp:
        return None
    try:
        created = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0, int(now_epoch - created.timestamp()))


records: list[dict[str, object]] = []
malformed = 0
for line in open(raw_path):
    line = line.rstrip("\n")
    if not line.replace("|", "").strip():
        continue
    parts = line.split("|", len(FIELDS) - 1)
    if len(parts) != len(FIELDS):
        malformed += 1
        continue
    row = dict(zip(FIELDS, parts))
    if not row["name"] or not any(row[field] for field in JOB_FIELDS):
        continue
    attrs: list[dict[str, object]] = [
        {"key": key, "value": {"stringValue": row[field]}}
        for key, field in ATTRIBUTES
        if row[field]
    ]
    age = age_seconds(row["created"])
    if age is not None:
        attrs.append({"key": "ci.runner_age_s", "value": {"intValue": str(age)}})
    summary = " ".join(
        part for part in (row["phase"], row["job_repository"], row["job_name"]) if part
    )
    records.append({
        "timeUnixNano": now_ns,
        "observedTimeUnixNano": now_ns,
        "severityNumber": 9,
        "severityText": "INFO",
        "body": {"stringValue": summary or row["name"]},
        "attributes": attrs,
    })

if malformed:
    print(
        f"ci-pool-attributed-gauges: {malformed} EphemeralRunner record(s) did not "
        "carry the expected field count and were skipped rather than misparsed",
        file=sys.stderr,
    )

# Exit 3 is "the listing read fine and nothing is running" -- the caller
# POSTs nothing, which for a board asking what is running now is the answer,
# not a gap. Any other non-zero is a real assembly failure.
if not records:
    sys.exit(3)

print(len(records))
print(json.dumps({"resourceLogs": [{
    "resource": {"attributes": [
        {"key": "service.name", "value": {"stringValue": "ci-runner-pool"}},
        {"key": "host.name", "value": {"stringValue": host}},
    ]},
    "scopeLogs": [{
        "scope": {"name": "ci-pool-attributed-gauges"},
        "logRecords": records,
    }],
}]}))
PY
)" || events_rc=$?

  case "${events_rc}" in
    0)
      events_count="${events_out%%$'\n'*}"
      events_body="${events_out#*$'\n'}"
      if curl --silent --show-error --fail --max-time 10 -X POST "${OTLP_LOGS_ENDPOINT}" \
           -H 'Content-Type: application/json' -d "${events_body}" > /dev/null; then
        log "posted ${events_count} running-job event(s) -> ${OTLP_LOGS_ENDPOINT} (host.name=${host_name})"
      else
        log "POST to ${OTLP_LOGS_ENDPOINT} failed" >&2
        post_failed=7
      fi
      ;;
    3)
      log "no EphemeralRunner carried a job assignment; no running-job events to post"
      ;;
    *)
      log "could not assemble the running-job events payload (python3 exited ${events_rc}); none POSTed" >&2
      failed=1
      ;;
  esac
fi

if [ "${post_failed}" -ne 0 ]; then
  exit "${post_failed}"
fi
exit "${failed}"
