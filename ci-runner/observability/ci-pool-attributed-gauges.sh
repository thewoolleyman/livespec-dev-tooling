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
#   livespec.ci_pool.start_created_to_scheduled_s   {ci.repository}
#   livespec.ci_pool.start_scheduled_to_ready_s     {ci.repository}
#   livespec.ci_pool.start_ready_to_workflow_pod_s  {ci.repository}
#   livespec.ci_pool.start_pvc_bound_s              {ci.repository}
#       the runner-pod START interval BROKEN INTO ITS PHASES rather than
#       summed (see THE START INTERVAL, PER PHASE below). Seconds, as
#       doubles — these phases are routinely sub-second and an integer gauge
#       would report a 400 ms provisioning as 0. ONE datapoint per repository
#       per tick, carrying the MAX over the starts that tick observed: a gauge
#       cannot carry a distribution, and the slowest start is the one that
#       indicts a component. The distribution lives in the wide events, where
#       a percentile over ci.start_*_s is exact.
#   livespec.ci_pool.starts_observed   (no attributes)
#       how many starts this tick could compute, 0 included. It is what makes
#       a gap in the four series above READABLE: 0 says the emitter looked and
#       found no start to measure, which on an idle pool is the usual state
#       and never a stall (see IT SAMPLES STARTS below).
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
#       ...and, in the SAME POST, one record per observed runner START,
#       carrying its phase durations (ci.start_created_to_scheduled_s and
#       friends, below). Two record kinds share one payload deliberately:
#       they are told apart by ci.record_kind (`running-job` / `start`), and
#       a second POST would have cost this unit's tick another 10 s of
#       worst-case deadline for nothing (see THE TICK'S BUDGET below).
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
# THE START INTERVAL, PER PHASE — AND THE ONE PHASE THAT HAS NO CLOCK
# (`livespec-ifwnqj.6`). The runner-pod-to-workflow-pod delta was being read
# as ONE number — 60 s median on 2026-09-08, down from 100 s — and one number
# cannot be acted on, because it is four stacked waits summed. It indicts no
# component when it regresses, and it can convict the wrong one when it does
# not: the same aggregate made livespec-wm7c's criterion read as unmet while
# the phase that item actually owns was about 4 s. An aggregate that cannot
# attribute is not a measurement. So the interval is emitted as its parts:
#
#   1  created -> scheduled    pod .metadata.creationTimestamp to the
#      PodScheduled condition's lastTransitionTime. Kueue admission, the
#      scheduler's bind, and — because this pool's storage class binds on
#      WaitForFirstConsumer — the work volume's provisioning, which is why
#      the PVC sub-interval below sits INSIDE this phase and not beside it.
#   2  scheduled -> ready      PodScheduled to Ready. containerd's sandbox
#      creation, the image, and the runner process reaching readiness.
#   3  ready -> job assigned   NOT EMITTED — no clock exists for it. Below.
#   4  job assigned -> workflow pod   the ARC container hook's prepare-job.
#      NOT EMITTED ON ITS OWN, because its start is phase 3's missing end.
#
#   start_ready_to_workflow_pod_s is what IS emitted in place of 3 and 4:
#   the Ready condition's lastTransitionTime to the workflow pod's
#   .metadata.creationTimestamp, which is phases 3 and 4 together. It is
#   named for what it measures — two boundaries this emitter can actually
#   see — rather than for the hook, so it can never be read as the hook's
#   number. It is an UPPER BOUND on the hook's prepare-job. A claim about the
#   hook cites the hook's own log line (../k3s/phase2/container-hook/), which
#   is the instrument that can split them; this series cannot.
#
# WHY PHASE 3 HAS NO CLOCK, AND WHY NOTHING HERE INVENTS ONE. The
# EphemeralRunner status carries the FACT of a job assignment — jobRequestId,
# jobRepositoryName, jobWorkflowRef, workflowRunId, jobDisplayName all become
# non-empty when the listener hands the runner a job — but it carries no
# timestamp for the moment they did, and no other object records one either:
# the pod's conditions (PodScheduled, Initialized, ContainersReady, Ready) do
# not move at job assignment, and the workflow pod does not exist yet. The
# two timestamps that could be reached for are both false. This script's own
# tick clock would encode the SAMPLER's 60 s cadence as the runner's latency.
# The status subresource's managedFields `time` is the last write by that
# manager, not the job-assignment write. The GitHub API's job started_at is
# neither a cluster listing nor free (the fleet's request budget), and would
# make a latency series depend on a rate-limited third party.
#   So phase 3 is ABSENT: no gauge, no event field, no derived stand-in. A
# fabricated timestamp would be worse than a gap, because a gap is visibly a
# gap while a fabrication charts. What phase 3 costs, it costs to the
# combined series above, where the header says so.
#
# THE PVC SUB-INTERVAL, AND WHY IT IS NOT A `Bound` TRANSITION. A
# PersistentVolumeClaim carries NO lastTransitionTime for its Bound phase:
# .status.phase is a bare string and .status.conditions on a PVC is the
# resize-only pair (Resizing, FileSystemResizePending), which never mentions
# binding. The bind instant is recoverable all the same, from the other side
# of the pair: a DYNAMICALLY provisioned PersistentVolume is created by the
# provisioner at the moment provisioning completes and the claim binds, so
# the bound PV's .metadata.creationTimestamp IS that instant, on a real
# object, with no inference. start_pvc_bound_s is therefore measured from the
# RUNNER POD's creationTimestamp to the creationTimestamp of the PV whose
# .spec.claimRef names `<runner pod name>-work`. Sharing phase 1's origin is
# deliberate: it makes the sub-interval directly comparable to the phase it
# sits inside, rather than a number on a second timeline. Under
# WaitForFirstConsumer the PV cannot precede the pod, so a negative value is
# not a slow volume but a misread, and is omitted rather than clamped to 0.
#
# WHICH LISTINGS THE PHASES COME FROM, and why they are new. The
# EphemeralRunner objects this script already reads carry the runner's
# identity and job fields but NOT pod conditions and NOT volume status —
# different objects, and the item that asked for this work was filed
# asserting otherwise and corrected itself before any code was written. So
# the tick makes two ADDITIONAL bounded list calls: pods across all
# namespaces (creationTimestamp plus the PodScheduled and Ready conditions)
# and PersistentVolumes (creationTimestamp plus claimRef). What is NOT added
# is a second timer, a second unit or a second polling loop — this is the
# precedent the running-jobs events set when they widened the EphemeralRunner
# listing rather than standing up an emitter of their own, applied to a
# measurement that genuinely needs objects that listing does not carry.
#
# IT SAMPLES STARTS, AND A GAP IS NOT A STALL. A start is computable only
# while BOTH the runner pod and its workflow pod are still present, so a job
# short enough to appear and vanish inside one 60 s tick is never observed at
# all. Two narrower cases drop a start the same way: a runner sampled after
# its job finished may have flipped Ready back to False, and every phase that
# needs Ready is then omitted rather than computed from a transition in the
# wrong direction; and a pod whose PodScheduled or Ready condition is not yet
# True contributes nothing for the phases that depend on it. The bias runs
# one way — toward the longer-lived job — and it is a bias in WHICH starts are
# sampled, never in the durations reported for the ones that are.
#   This is an acceptable design for a latency signal and an unacceptable one
# to leave unwritten, so: a gap in these series means no start was observed,
# NOT that starts stopped or stalled. livespec.ci_pool.starts_observed is
# emitted every tick, 0 included, so the two are distinguishable without
# reading this comment.
#
# EACH START IS EMITTED ONCE, WITHOUT KEEPING STATE. A start stays computable
# for as long as both pods live, so a naive emitter would re-report the same
# start on every tick of a ten-minute job and weight it ten times in any
# percentile. The dedup is a WINDOW rather than a state file: a start is
# emitted only while its workflow pod is younger than CI_POOL_START_WINDOW_S,
# which defaults to 60 — the timer's own interval. With ticks one interval
# apart, exactly one tick sees a given workflow pod inside the window. When
# the timer runs late the start falls outside it and is dropped, which is the
# safe direction: an omitted sample is a gap the paragraph above already
# accounts for, while a duplicated one silently skews a percentile.
#
# SINGLE-START MODE, for a measurement in a quiet window. `--single-start
# [<runner name>]` reads the same four listings ONCE, ignores the emission
# window, prints every start it can compute as a human-readable phase
# breakdown, and POSTs NOTHING. Posting is the timer's job; a mode meant to
# be run by hand at any moment must not be able to inject a duplicate
# datapoint into the series it exists to explain. It needs no waiting and
# no loop: the runner pod and the workflow pod both live for the duration of
# the job, so any moment while the job runs is a moment this mode can read.
# Exit 0 when it reported at least one start, 3 when it read the cluster
# cleanly and there was no start to report, non-zero otherwise. This is the
# form a start-latency acceptance claim cites — research/005's single-start
# watcher of 2026-09-04 was a session-local loop whose raw rows were never a
# durable source, and this is its committed successor rather than a third
# tool beside it.
#
# THE TICK'S BUDGET, REALLOCATED RATHER THAN GROWN. The unit's deadline is
# TimeoutStartSec=55 against a 60 s interval, and its worst case was 50 s:
# two 15 s kubectl reads plus two 10 s curls. The two new listings are 5 s
# each, and the two loopback POSTs drop from 10 s to 5 s to pay for them, so
# the worst case is 50 s still and the deadline is untouched. Five seconds is
# not a weakened POST deadline: the collector is on 127.0.0.1, a small JSON
# body it cannot accept in five seconds means it is wedged, and failing fast
# there is the outcome this unit wants. The start listings get the SHORTER
# kubectl deadline on purpose — the start signal samples by construction, so
# abandoning one slow listing costs one sample, while overrunning the unit's
# deadline costs the whole tick, gauges and events together.
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
#   The START rows follow the GAUGES' rule even though they are events,
#   because the field choice follows what the ROW IS ABOUT and not which
#   signal carries it: a start is a fact about a pod's lifecycle, and it must
#   stay attributable when it is sampled a minute later with the job fields
#   already cleared. spec.githubConfigUrl is present in every phase and
#   cannot be cleared; status.jobRepositoryName can be, and a start that
#   loses its repository is a start that vanishes from the board.
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
# sweeps would double-count at a shorter interval. This script makes four
# bounded kubectl list calls and two POSTs, so a minute is cheap.
#
# CREDENTIAL. Root with the k3s admin kubeconfig, the same
# `Environment=KUBECONFIG=/etc/rancher/k3s/k3s.yaml` the lifecycle sweep's
# unit carries, because it reads the same cluster-scoped ClusterQueues plus
# an all-namespace EphemeralRunner listing — and, for the start phases, an
# all-namespace pod listing and the cluster-scoped PersistentVolumes, both of
# which that kubeconfig already covers, so no RBAC changes with this work. It
# is a strictly read-only use of it; nothing here writes to the cluster.
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
# The two START listings read on a SHORTER deadline than the two above, and
# the reason is in THE TICK'S BUDGET in the header: the start signal samples
# by construction, so abandoning one slow listing costs one sample while
# overrunning the unit's TimeoutStartSec costs the whole tick.
START_KUBECTL_REQUEST_TIMEOUT="${CI_POOL_START_KUBECTL_REQUEST_TIMEOUT:-5s}"
# How young a workflow pod must be for its start to be emitted, in seconds.
# The default is the timer's own interval, which is what makes each start
# reach the series exactly once with no state kept between ticks (see EACH
# START IS EMITTED ONCE in the header).
START_WINDOW_S="${CI_POOL_START_WINDOW_S:-60}"
# Seconds a loopback POST may take. Five, not ten: the collector is on
# 127.0.0.1, and the ten seconds this was paid for the two new listings.
POST_MAX_TIME="${CI_POOL_POST_MAX_TIME:-5}"
# The GitHub owner every queue name on this pool is a repository of.
REPO_OWNER="${CI_POOL_REPO_OWNER:-thewoolleyman}"
# Space-separated ClusterQueue names that are NOT repositories. Belt and
# braces beside the churn-slot filter, which already excludes this one.
NON_REPO_QUEUES="${CI_POOL_NON_REPO_QUEUES:-phase1-proof-cq}"
# The resource whose presence marks a ClusterQueue as one of this pool's —
# the sweep's filter, spelled once here.
CHURN_SLOT_RESOURCE="${CI_POOL_CHURN_SLOT_RESOURCE:-ci-runner.io/churn-slot}"

log() { printf 'ci-pool-attributed-gauges: %s\n' "$*"; }

usage() {
  printf '%s\n' \
    'usage: ci-pool-attributed-gauges.sh [--single-start [<runner name>]]' \
    '' \
    '  (no arguments)   one tick: emit the pool gauges and the wide events.' \
    '  --single-start   read the cluster once, print every start it can' \
    '                   compute as a per-phase breakdown, and POST nothing.' \
    '                   With a runner name, report only that runner. Exit 3' \
    '                   when the read was clean and there was no start.'
}

# --single-start turns this into a REPORTER: same listings, same derivation,
# no emission window and no POST (see SINGLE-START MODE in the header).
single_start=0
single_start_runner=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --single-start)
      single_start=1
      # An optional runner name, but never the next FLAG mistaken for one.
      case "${2:-}" in
        ""|-*) ;;
        *) single_start_runner="$2"; shift ;;
      esac
      ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

now_ns="$(date +%s%N)"
host_name="$(hostname)"
readings="$(mktemp)"
# The EphemeralRunner listing's raw rows, kept so the events assembler reads
# the SAME bytes the count loop below reads — one listing, two readers.
runners_raw="$(mktemp)"
# The two START listings' raw rows, and the two files the start assembler
# writes: gauge readings folded into "${readings}", and OTLP log records
# folded into the running-job events' POST.
pods_raw="$(mktemp)"
volumes_raw="$(mktemp)"
start_records="$(mktemp)"
trap 'rm -f "${readings}" "${runners_raw}" "${pods_raw}" "${volumes_raw}" "${start_records}"' EXIT
failed=0

# One TSV record per datapoint, read back by the assembler below:
#   <metric-key>\t<value>\t<attr>=<value>[\t<attr>=<value>...]
put() { printf '%s\n' "$*" >> "${readings}"; }

kc() { "${KUBECTL_BIN}" --request-timeout="${KUBECTL_REQUEST_TIMEOUT}" "$@"; }
kc_start() { "${KUBECTL_BIN}" --request-timeout="${START_KUBECTL_REQUEST_TIMEOUT}" "$@"; }

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

if [ "${single_start}" -eq 1 ]; then
  # The reporter reads only what the start phases need. Skipping this listing
  # is not a shortcut: it emits no gauges, so a ClusterQueue reading would be
  # 15 s of deadline spent on a number nothing would print.
  log "--single-start: skipping the ClusterQueue listing (it feeds gauges this mode does not emit)"
elif cq_rows="$(kc get clusterqueues -o jsonpath="${CQ_JSONPATH}" 2>&1)"; then
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

# ---- start phases ------------------------------------------------------------
# The two listings the EphemeralRunner objects cannot supply (see WHICH
# LISTINGS THE PHASES COME FROM in the header), on the shorter deadline.
#
# Pods: the runner pod's origin and the two conditions that bound phases 1
# and 2, plus the `<runner pod name>-workflow` pod whose creationTimestamp
# closes the combined phase. Each condition is rendered `<status>@<time>`
# because a lastTransitionTime is only a phase boundary when its status is
# True — a PodScheduled that is False is when SCHEDULING GATING began, and a
# Ready that is False is when the finished job's runner stopped being ready.
PODS_JSONPATH='{range .items[*]}{.metadata.namespace}|{.metadata.name}|{.metadata.creationTimestamp}|{range .status.conditions[?(@.type=="PodScheduled")]}{.status}@{.lastTransitionTime}{end}|{range .status.conditions[?(@.type=="Ready")]}{.status}@{.lastTransitionTime}{end}{"\n"}{end}'
# PersistentVolumes: the bind instant, on the only object that records it
# (see THE PVC SUB-INTERVAL in the header). claimRef names the PVC, so the
# claim listing itself is never needed.
PVS_JSONPATH='{range .items[*]}{.metadata.name}|{.metadata.creationTimestamp}|{.spec.claimRef.namespace}|{.spec.claimRef.name}{"\n"}{end}'

start_sources=0
if pod_rows="$(kc_start get pods --all-namespaces -o jsonpath="${PODS_JSONPATH}" 2>&1)"; then
  printf '%s\n' "${pod_rows}" > "${pods_raw}"
  start_sources=$((start_sources + 1))
else
  log "could not read pods ($(printf '%s' "${pod_rows}" | head -1)); omitting every livespec.ci_pool.start_* gauge and every start event this tick rather than sending false zeros" >&2
  failed=1
fi

if pv_rows="$(kc_start get persistentvolumes -o jsonpath="${PVS_JSONPATH}" 2>&1)"; then
  printf '%s\n' "${pv_rows}" > "${volumes_raw}"
else
  # NOT fatal to the start signal: the volume sub-interval is one attribute
  # inside phase 1, so an unreadable PV listing costs that attribute and
  # nothing else. The four phases still read from the pods listing.
  log "could not read PersistentVolumes ($(printf '%s' "${pv_rows}" | head -1)); the start phases are still emitted, without their work-volume sub-interval" >&2
  : > "${volumes_raw}"
  failed=1
fi

start_mode="emit"
start_window="${START_WINDOW_S}"
if [ "${single_start}" -eq 1 ]; then
  start_mode="report"
  # No window: a hand-run measurement reports whatever is on the cluster now.
  start_window=""
fi

start_rc=0
if [ "${start_sources}" -eq 0 ] || [ ! -s "${runners_raw}" ]; then
  log "no pod listing or no EphemeralRunner listing to derive start phases from; none computed" >&2
  start_rc=4
else
  python3 - "${runners_raw}" "${pods_raw}" "${volumes_raw}" "${now_ns}" \
    "${start_window}" "${single_start_runner}" "${readings}" "${start_records}" \
    "${start_mode}" <<'PY' || start_rc=$?
import json
import sys
from datetime import datetime, timezone

(
    runners_path, pods_path, volumes_path, now_ns, window_raw,
    runner_filter, readings_path, records_path, mode,
) = sys.argv[1:10]
now_epoch = int(now_ns) / 1_000_000_000
window = float(window_raw) if window_raw else None

# ER_JSONPATH's field order (the count loop's comment carries the same list).
ER_FIELDS = (
    "namespace", "name", "created", "config_url", "phase",
    "job_repository", "job_workflow_ref", "run_id", "job_name",
)
# PODS_JSONPATH's field order.
POD_FIELDS = ("namespace", "name", "created", "scheduled", "ready")
# PVS_JSONPATH's field order.
PV_FIELDS = ("name", "created", "claim_namespace", "claim_name")

# The phases, in the order a reader wants them: the TSV key the gauge
# assembler reads, the event attribute, and the label the report prints.
PHASES = (
    ("start_created_to_scheduled", "ci.start_created_to_scheduled_s",
     "1 created -> scheduled"),
    ("start_scheduled_to_ready", "ci.start_scheduled_to_ready_s",
     "2 scheduled -> ready"),
    ("start_ready_to_workflow_pod", "ci.start_ready_to_workflow_pod_s",
     "4 ready -> workflow pod"),
    ("start_pvc_bound", "ci.start_pvc_bound_s",
     "  of which work volume bound"),
)


def stamp(value: str) -> float | None:
    """RFC 3339 to epoch seconds, or None when it is not a timestamp.

    None means the phases that need it are OMITTED, never sent as 0 -- the
    fail-closed rule the gauges above apply to a whole source, applied here
    per boundary.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def condition_stamp(value: str) -> float | None:
    """`<status>@<time>` to epoch seconds, only while the status is True.

    A False condition's lastTransitionTime is when the condition STOPPED
    holding -- scheduling gating beginning, or a finished job's runner going
    not-ready -- so reading it as a phase boundary would report a transition
    in the wrong direction as a duration.
    """
    status, _, when = value.partition("@")
    return stamp(when) if status == "True" else None


def rows(path: str, fields: tuple[str, ...]) -> list[dict[str, str]]:
    parsed = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line.replace("|", "").strip():
                continue
            parts = line.split("|")
            if len(parts) != len(fields):
                continue
            parsed.append(dict(zip(fields, parts)))
    return parsed


def repository(config_url: str) -> str:
    """spec.githubConfigUrl's <owner>/<repo> tail, or empty.

    The GAUGES' derivation, spelled the same way here on purpose; the header
    says why a start row follows it rather than status.jobRepositoryName.
    """
    stripped = config_url.rstrip("/")
    if "://" not in stripped:
        return ""
    path = stripped.split("://", 1)[1]
    if "/" not in path:
        return ""
    segments = path.split("/", 1)[1].split("/")
    return "/".join(segments) if len(segments) == 2 else ""


def interval(start: float | None, end: float | None) -> float | None:
    """End minus start in seconds, or None when either end is unknown.

    A NEGATIVE result is None too, not a clamp to 0: these boundaries cannot
    legitimately run backwards, so a negative one is a misread and reporting
    it as an instantaneous phase would be a false reading.
    """
    if start is None or end is None:
        return None
    delta = end - start
    return round(delta, 3) if delta >= 0 else None


pods = {(row["namespace"], row["name"]): row for row in rows(pods_path, POD_FIELDS)}
volumes = {
    (row["claim_namespace"], row["claim_name"]): stamp(row["created"])
    for row in rows(volumes_path, PV_FIELDS)
    if row["claim_name"]
}

starts: list[dict[str, object]] = []
for runner in rows(runners_path, ER_FIELDS):
    name, namespace = runner["name"], runner["namespace"]
    if not name or (runner_filter and name != runner_filter):
        continue
    pod = pods.get((namespace, name))
    workflow = pods.get((namespace, name + "-workflow"))
    if pod is None or workflow is None:
        continue
    created = stamp(pod["created"])
    workflow_created = stamp(workflow["created"])
    if created is None or workflow_created is None:
        continue
    # The stateless dedup (see EACH START IS EMITTED ONCE in the header).
    # --single-start passes no window and reports whatever is on the cluster.
    age = now_epoch - workflow_created
    if window is not None and not 0 <= age < window:
        continue
    scheduled = condition_stamp(pod["scheduled"])
    ready = condition_stamp(pod["ready"])
    starts.append({
        "name": name,
        "namespace": namespace,
        "phase": runner["phase"],
        "repository": repository(runner["config_url"]),
        "age": round(age, 3),
        "total": interval(created, workflow_created),
        "start_created_to_scheduled": interval(created, scheduled),
        "start_scheduled_to_ready": interval(scheduled, ready),
        "start_ready_to_workflow_pod": interval(ready, workflow_created),
        "start_pvc_bound": interval(created, volumes.get((namespace, name + "-work"))),
    })

def report_line(label: str, value: object, note: str) -> None:
    shown = "%9.3f s" % value if isinstance(value, float) else "   absent  "
    print("  %-28s %s   %s" % (label, shown, note))


if mode == "report":
    if not starts:
        print(
            "ci-pool-attributed-gauges: no runner has both its pod and its "
            "<name>-workflow pod on the cluster right now, so no start is "
            "computable; run this while the job is running",
            file=sys.stderr,
        )
        sys.exit(3)
    # Printed in the order the phases HAPPEN, with the volume sub-interval
    # indented under the phase it sits inside and phase 3 stated as absent
    # rather than silently missing -- a reader must be able to see that the
    # number below it carries phase 3 within it.
    for start in sorted(starts, key=lambda item: str(item["name"])):
        print("runner %s (%s)  %s  phase=%s  workflow pod %.1f s old" % (
            start["name"], start["namespace"],
            start["repository"] or "<no repository in spec.githubConfigUrl>",
            start["phase"] or "unset", start["age"],
        ))
        report_line(
            "1 created -> scheduled", start["start_created_to_scheduled"],
            "Kueue admission, scheduler bind, volume provisioning",
        )
        report_line(
            "    of which volume bound", start["start_pvc_bound"],
            "pod created -> the PV bound to <runner>-work created",
        )
        report_line(
            "2 scheduled -> ready", start["start_scheduled_to_ready"],
            "containerd sandbox, image, runner process",
        )
        report_line(
            "3 ready -> job assigned", None,
            "no cluster object timestamps this; it is inside the next line",
        )
        report_line(
            "4 ready -> workflow pod", start["start_ready_to_workflow_pod"],
            "phases 3 and 4 together; an UPPER BOUND on the hook",
        )
        report_line(
            "= created -> workflow pod", start["total"],
            "the aggregate — never an acceptance signal on its own",
        )
    sys.exit(0)

# --- emit mode: gauge readings appended to the tick's TSV, events to JSON ---
with open(readings_path, "a", encoding="utf-8") as handle:
    handle.write("starts_observed\t%d\t\n" % len(starts))
    # One datapoint per repository per phase, carrying the tick's MAX: a
    # gauge cannot carry a distribution, and the slowest start is the one
    # that indicts a component. Percentiles come from the events below.
    for key, _attribute, _label in PHASES:
        worst: dict[str, float] = {}
        for start in starts:
            value, repo = start[key], start["repository"]
            if value is None or not repo:
                continue
            worst[str(repo)] = max(worst.get(str(repo), 0.0), float(value))
        for repo, value in sorted(worst.items()):
            handle.write("%s\t%.3f\tci.repository=%s\n" % (key, value, repo))

records = []
for start in starts:
    attributes: list[dict[str, object]] = [
        {"key": "ci.record_kind", "value": {"stringValue": "start"}},
        {"key": "ci.runner_name", "value": {"stringValue": str(start["name"])}},
        {"key": "ci.runner_namespace", "value": {"stringValue": str(start["namespace"])}},
    ]
    for key, field in (("ci.repository", "repository"), ("ci.runner_phase", "phase")):
        if start[field]:
            attributes.append({"key": key, "value": {"stringValue": str(start[field])}})
    for key, attribute, _label in PHASES:
        if start[key] is not None:
            attributes.append({"key": attribute, "value": {"doubleValue": start[key]}})
    if start["total"] is not None:
        # The aggregate rides the row so it reconciles with its own parts.
        # It is deliberately NOT a gauge: charting it takes a deliberate act,
        # and this item exists because that number was being acted on alone.
        attributes.append(
            {"key": "ci.start_created_to_workflow_pod_s", "value": {"doubleValue": start["total"]}}
        )
    attributes.append(
        {"key": "ci.workflow_pod_age_s", "value": {"doubleValue": start["age"]}}
    )
    records.append({
        "timeUnixNano": now_ns,
        "observedTimeUnixNano": now_ns,
        "severityNumber": 9,
        "severityText": "INFO",
        "body": {"stringValue": "start %s %s" % (start["repository"], start["name"])},
        "attributes": attributes,
    })

with open(records_path, "w", encoding="utf-8") as handle:
    json.dump(records, handle)

# To STDERR, beside the shell's own log lines: 0 is the usual reading on an
# idle pool and is emitted as starts_observed, so the journal and the series
# agree about what this tick saw.
print(
    "ci-pool-attributed-gauges: computed %d start(s) from the pod and "
    "PersistentVolume listings" % len(starts),
    file=sys.stderr,
)
PY

  if [ "${start_rc}" -ne 0 ] && [ "${start_rc}" -ne 3 ]; then
    log "could not derive the start phases (python3 exited ${start_rc}); none emitted" >&2
    failed=1
  fi
fi

if [ "${single_start}" -eq 1 ]; then
  # The reporter has printed. It POSTs nothing, on purpose: a mode meant to
  # be run by hand at any moment must not inject a duplicate datapoint into
  # the series it exists to explain.
  case "${start_rc}" in
    0|3) exit "${start_rc}" ;;
    *) exit 1 ;;
  esac
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

# metric key -> (OTLP name, unit, description, value kind). The KIND is not
# decoration: the start phases below are routinely sub-second, and an integer
# datapoint would report a 400 ms volume provisioning as 0 -- a false zero of
# exactly the kind the omission rule above exists to prevent.
SPEC = {
    "queue_pending": (
        "livespec.ci_pool.queue_pending", "{workloads}",
        "Kueue workloads pending admission on ONE ClusterQueue covering "
        "ci-runner.io/churn-slot (the per-queue breakdown of "
        "livespec.ci_kueue.pending)", "int",
    ),
    "queue_admitted": (
        "livespec.ci_pool.queue_admitted", "{workloads}",
        "Kueue workloads admitted and not yet finished on ONE ClusterQueue "
        "covering ci-runner.io/churn-slot (the per-queue breakdown of "
        "livespec.ci_kueue.admitted)", "int",
    ),
    "queue_quota": (
        "livespec.ci_pool.queue_quota", "{slots}",
        "nominalQuota for ci-runner.io/churn-slot on ONE ClusterQueue (the "
        "per-queue breakdown of livespec.ci_churn_slot.quota_sum)", "int",
    ),
    "runners": (
        "livespec.ci_pool.runners", "{runners}",
        "EphemeralRunner objects owned by one repository in one phase; the "
        "repository comes from spec.githubConfigUrl, so a runner with no job "
        "assigned still counts", "int",
    ),
    "runners_total": (
        "livespec.ci_pool.runners_total", "{runners}",
        "EphemeralRunner objects across all namespaces; 0 is a genuine "
        "reading on an idle pool (ARC scale sets run minRunners 0)", "int",
    ),
    "starts_observed": (
        "livespec.ci_pool.starts_observed", "{starts}",
        "runner starts this tick could compute -- both the runner pod and "
        "its <name>-workflow pod present, and the workflow pod inside the "
        "emission window. Emitted every tick, 0 included, so a gap in the "
        "start phase series reads as an unobserved start rather than a stall",
        "int",
    ),
    "start_created_to_scheduled": (
        "livespec.ci_pool.start_created_to_scheduled_s", "s",
        "PHASE 1 of the runner-pod start, worst observed this tick for one "
        "repository: pod creationTimestamp to the PodScheduled condition. "
        "Kueue admission, the scheduler's bind, and the WaitForFirstConsumer "
        "work volume's provisioning (start_pvc_bound_s is inside this)",
        "double",
    ),
    "start_scheduled_to_ready": (
        "livespec.ci_pool.start_scheduled_to_ready_s", "s",
        "PHASE 2 of the runner-pod start, worst observed this tick for one "
        "repository: PodScheduled to Ready. containerd's sandbox creation, "
        "the image, and the runner process reaching readiness",
        "double",
    ),
    "start_ready_to_workflow_pod": (
        "livespec.ci_pool.start_ready_to_workflow_pod_s", "s",
        "PHASES 3 AND 4 TOGETHER, worst observed this tick for one "
        "repository: the runner pod's Ready condition to the workflow pod's "
        "creationTimestamp. No cluster object timestamps the job assignment "
        "that separates them, so this is an UPPER BOUND on the ARC container "
        "hook's prepare-job and never the hook's own number",
        "double",
    ),
    "start_pvc_bound": (
        "livespec.ci_pool.start_pvc_bound_s", "s",
        "the work volume's provisioning, INSIDE phase 1, worst observed this "
        "tick for one repository: pod creationTimestamp to the "
        "creationTimestamp of the PersistentVolume bound to <runner>-work, "
        "which is the bind instant a PVC itself records no time for",
        "double",
    ),
}

points: dict[str, list[dict[str, object]]] = {}
for line in open(readings_path):
    fields = line.rstrip("\n").split("\t")
    key, value, attr_fields = fields[0], fields[1], fields[2:]
    if key not in SPEC:
        continue
    dp: dict[str, object] = {"timeUnixNano": now_ns}
    if SPEC[key][3] == "double":
        dp["asDouble"] = float(value)
    else:
        dp["asInt"] = str(int(value))
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
for key, (name, unit, description, _kind) in SPEC.items():
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
if curl --silent --show-error --fail --max-time "${POST_MAX_TIME}" -X POST "${OTLP_ENDPOINT}" \
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

# ---- wide events -------------------------------------------------------------
# One POST to the collector's logs path (see WHAT IT EMITS AS EVENTS in the
# header) carrying BOTH record kinds: one per runner carrying a job
# assignment, and one per observed start. The running-job rows are the ones
# the count loop above already read; nothing is listed twice, and the start
# records were assembled from the pod and PersistentVolume listings above.
if [ ! -s "${runners_raw}" ] && [ ! -s "${start_records}" ]; then
  log "no EphemeralRunner listing and no start records to derive wide events from; none POSTed" >&2
else
  events_rc=0
  # stdout is the record COUNT on line 1 and the OTLP payload on line 2.
  events_out="$(python3 - "${runners_raw}" "${now_ns}" "${host_name}" "${start_records}" <<'PY'
import json
import sys
from datetime import datetime, timezone

raw_path, now_ns, host, starts_path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
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
        # Two record kinds share this dataset, so every record says which it
        # is rather than leaving a reader to infer it from which columns
        # happen to be populated.
        {"key": "ci.record_kind", "value": {"stringValue": "running-job"}},
    ]
    attrs.extend(
        {"key": key, "value": {"stringValue": row[field]}}
        for key, field in ATTRIBUTES
        if row[field]
    )
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

# The start records, assembled earlier from the pod and PersistentVolume
# listings, ride the SAME payload. An unreadable or absent file is a tick
# with no starts, not a failure: the start block above has already logged
# whatever went wrong and set the exit status.
try:
    with open(starts_path, encoding="utf-8") as handle:
        records.extend(json.load(handle))
except (OSError, ValueError):
    pass

# Exit 3 is "the listings read fine and there was nothing to say" -- the
# caller POSTs nothing, which for a board asking what is running now is the
# answer, not a gap. Any other non-zero is a real assembly failure.
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
      if curl --silent --show-error --fail --max-time "${POST_MAX_TIME}" -X POST "${OTLP_LOGS_ENDPOINT}" \
           -H 'Content-Type: application/json' -d "${events_body}" > /dev/null; then
        log "posted ${events_count} wide event(s) -> ${OTLP_LOGS_ENDPOINT} (host.name=${host_name})"
      else
        log "POST to ${OTLP_LOGS_ENDPOINT} failed" >&2
        post_failed=7
      fi
      ;;
    3)
      log "no EphemeralRunner carried a job assignment and no start was observed; no wide events to post"
      ;;
    *)
      log "could not assemble the wide-events payload (python3 exited ${events_rc}); none POSTed" >&2
      failed=1
      ;;
  esac
fi

if [ "${post_failed}" -ne 0 ]; then
  exit "${post_failed}"
fi
exit "${failed}"
