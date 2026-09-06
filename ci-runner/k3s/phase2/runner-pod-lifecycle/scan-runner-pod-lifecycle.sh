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
# TEN CLASSES, each read from the node-side observable that actually PERSISTS
# long enough for a five-minute sweep to see it:
#
#   pvc-pending          a PVC in the runners namespace Pending longer than
#                        PVC_PENDING_SECONDS — the provisioner is behind
#                        (2026-09-01: Pending PVCs 38 -> 57). A PVC whose
#                        consumer pod carries spec.schedulingGates (Kueue
#                        holding the runner pod before admission) is NOT
#                        counted: under WaitForFirstConsumer its claim is
#                        Pending by design until the pod is released, so it
#                        says nothing about the provisioner (2026-09-06:
#                        10 gated pods' claims among 33 Pending). Those are
#                        counted separately and emitted as the
#                        livespec.ci_lifecycle.pvc-gated gauge.
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
#                        BEST-EFFORT, and honestly so: the log grep MISSES
#                        every failure whose runner pod is already gone,
#                        which is most of them — ephemeral runner pods are
#                        deleted seconds after a job fails (2026-09-06
#                        06:07Z: 17 jobs failed on `connect ECONNREFUSED` +
#                        the hook string; the 06:13Z and 06:20Z sweeps read
#                        0). Nothing node-side outlives the pod with the job
#                        outcome in it: the ARC 0.14.2 listener logs no job
#                        result at all (verified against 300+ MB of listener
#                        archive: `Updating job info for the runner`,
#                        `Calculated target runner count`, never a
#                        conclusion), EphemeralRunner status is Succeeded
#                        and deleted after a hook failure (the runner exits
#                        0), and the hook emits no event. The DURABLE
#                        detection is job-side, in the fleet's github-ci
#                        Honeycomb dataset (../README.md "The detector",
#                        the `ci-hook-failure-burst` trigger under
#                        ../../../observability/triggers/); this class
#                        names the node-side cause when one is visible
#                        (api-unavailable, containerd-deadline).
#   stale-listener       a scale-set listener pod not Running (or waiting in a
#                        crash loop), or an AutoscalingListener whose
#                        spec.ephemeralRunnerSetName names no existing
#                        EphemeralRunnerSet (the ARC 0.14.2 boot race;
#                        converge-side fix livespec-bde2). Remedy the report
#                        names: delete the AutoscalingListener — the controller
#                        recreates it against the live set within ~30 s.
#   capacity-absent      a runner node (NODE_SELECTOR) with no
#                        ci-runner.io/churn-slot in status.allocatable, or the
#                        nodes' allocatable total below the sum of every
#                        ClusterQueue's nominalQuota for it — Kueue admits
#                        against quota, the scheduler places against the node,
#                        so every admitted runner pod is unschedulable while
#                        nothing on the cluster says so (2026-09-04 06:31Z to
#                        07:52Z: a dependency-failed boot left the reapply
#                        unit unrun; converge assertion + timer fallback
#                        livespec-kgl3). Remedy the report names:
#                        `systemctl start reapply-node-extended-resource.service`.
#   warm-cache-oversize  the LIVE warm uv cache generation (the one every new
#                        work volume is seeded from, ../warm-cache/) is over
#                        its budget on either axis — bytes or files, the
#                        warm-cache-budget ConfigMap's numbers as last-run.json
#                        records them — or the populator is STALLED: its last
#                        run finished more than WARM_STALE_TICKS sweep windows
#                        ago (12 x 5 min = 1 h, two missed 30-minute
#                        schedules). Over-budget is read from the live
#                        generation's own manifest, NOT from last-run.json's
#                        generation_bytes: on a refused run those describe the
#                        refused candidate, and the live generation is the
#                        previous one. A stalled populator means every job
#                        seeds from an aging generation and the refusal path
#                        is no longer being exercised (livespec-44qx, F4b).
#   start-seed-cost      what one job start actually paid for its warm seed:
#                        on the NEWEST seeded work volume this node holds, the
#                        seed's real size (du -sb of _warm/uv) against the
#                        warm budget, and the seed's duration against
#                        SEED_SECONDS_BUDGET. The duration is read from the
#                        volume itself — the birth time of _warm (the setup
#                        script's mkdir, first thing before the reflink copy)
#                        to the mtime of _warm/.uv-generation (written last,
#                        after the copy and the directory chmod pass) —
#                        because the provisioner deletes its helper pod the
#                        moment it observes Succeeded, so the pod's terminated
#                        state is gone before a sweep can read it, while the
#                        volume persists for the job's life. No seeded volume
#                        visible (idle pool) OMITS the class rather than
#                        reporting 0 (livespec-44qx, F4b; research/005-006 of
#                        the plan measured 3 s on the 12k-file generation).
#   api-unavailable      the API server was not there: k3s.service's main
#                        process STARTED inside the window — systemd's
#                        ExecMainStartTimestampMonotonic (microseconds since
#                        boot, moved by every start: a crash-and-auto-restart
#                        and a hand `systemctl restart` alike) read against
#                        /proc/uptime, so no time zone is parsed and no state
#                        is kept (the journal's `Main process exited` line
#                        appears only for a FAILING exit and a hand restart
#                        RESETS NRestarts, which is why the first cut read 0
#                        on exactly the acceptance move) — plus this sweep's
#                        OWN API reads that were REFUSED (`connection
#                        refused`, `EOF`, `Service Unavailable`; a read that
#                        merely timed out, `TLS handshake timeout` included,
#                        is the deadline machinery's, not this class's — an
#                        overloaded API times out, a gone one refuses).
#                        A boot is a start too: the first sweep after one
#                        reports it, truthfully. 2026-09-06
#                        06:07:03Z: a flannel vxlan nil-pointer panic, systemd
#                        restart, API back ~06:07:20Z, 17 jobs failed on
#                        ECONNREFUSED in between; the 06:07:09Z sweep saw its
#                        ClusterQueue read refused and no class said so. A
#                        refused /readyz precheck posts this class ALONE
#                        (count 1) before the fail-closed exit 2, because a
#                        sweep that cannot read the cluster has still read
#                        this (livespec-kgdlte scope 7).
#
# EVERY READ IS BOUNDED (livespec-kgdlte, I1). On 2026-09-06 05:55Z, under the
# first 64-churn-slot start burst, the sweep's step-4 `kubectl get pods` sat
# for six minutes with no open socket while /readyz answered in 2.5 s; the
# unit had no TimeoutStartSec, so the timer's cadence stopped silently until
# the child was killed by hand. Now: every kubectl call carries
# --request-timeout (KUBECTL_REQUEST_TIMEOUT) and NO watch/follow form exists;
# every external read — kubectl, journalctl, the containerd.log walk, the
# runner-log read, du and find on the storage root — runs under timeout(1)
# with a per-step deadline (STEP_TIMEOUT) that also shrinks to whatever is
# left of the unit's deadline (RPL_DEADLINE_SECONDS, the .service's
# TimeoutStartSec=240, under the 5-minute timer), so the sweep finishes and
# says what it could not read instead of being killed mid-report. A step that
# hits its deadline is recorded; the class it feeds is then OMITTED from the
# gauges when its count is 0 (a false zero) and the sweep exits 2 rather than
# CLEAN when nothing else was found (a partial read is not a reading). Should
# systemd's deadline fire anyway, the SIGTERM trap prints one line naming it
# as a KILL, not a finding, and `systemctl show -p Result` reads `timeout`
# rather than `exit-code`. The sweep's own wall clock is emitted as
# livespec.ci_lifecycle.sweep_seconds so the trend is visible before the
# deadline is.
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
# EVERY SWEEP ALSO EMITS ITS READINGS — the per-class counts, Kueue's
# pending/admitted workload counts and the churn-slot allocatable-versus-
# quota-sum — as OTLP gauges to the host collector, best-effort, so the
# churn-slot cap can be re-derived from measured data rather than from this
# journal. See "OTLP EMISSION" at the end of the evaluation (livespec-vwzv).
#
# Requires: kubectl + KUBECONFIG for the k3s cluster, journalctl with access
# to the k3s unit's journal, read access to containerd.log and to the
# provisioner's storage root (root, on the live host — the service runs as
# root, like the wedge sweep), timeout(1), python3 (the JSON reads), GNU
# find (-printf). curl for the emission (its absence is logged, never fatal).
set -euo pipefail

USAGE="usage: scan-runner-pod-lifecycle.sh [--window DURATION] [--pvc-pending-seconds N] [--workflow-pending-seconds N] [--killpod-min N] [--containerd-log PATH] [--state-file PATH] [--escalate-after N] [--namespace NS] [--systems-namespace NS] [--node-selector LABEL] [--otlp-endpoint URL] [--no-emit] [--warm-last-run PATH] [--warm-budget-configmap NS/NAME] [--warm-stale-ticks N] [--seed-seconds-budget N] [--seed-bytes-budget N] [--storage-root PATH] [--request-timeout DURATION] [--step-timeout N] [--deadline-seconds N] [--k3s-unit UNIT]
  DURATION is <N>s, <N>m or <N>h. REPORT-ONLY: prints every lifecycle-stall
  class found on the node with its count and exits 1 if any; exits 0 on a
  clean node; exits 2 when it cannot read one of its inputs, or when a read
  hit its deadline and nothing else was found. Every sweep also POSTs its
  readings as OTLP gauges to the host collector, best-effort; --no-emit (or
  RPL_NO_EMIT=1) skips that."

NAMESPACE="${RPL_NAMESPACE:-arc-runners}"
SYSTEMS_NAMESPACE="${RPL_SYSTEMS_NAMESPACE:-arc-systems}"
# The nodes expected to carry ci-runner.io/churn-slot: the label
# ../node-extended-resource/patch-node-churn-capacity.sh patches and
# ../kueue/resource-flavor.yaml selects (provision-k3s.sh's --node-label).
NODE_SELECTOR="${RPL_NODE_SELECTOR:-k3s-role=arc-runner-host}"
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
# Where the end-of-sweep gauges go (see "OTLP EMISSION" below): the host
# otel-collector's loopback HTTP receiver, the heartbeat family's endpoint
# (../../../observability/), honouring its host-wide override too.
OTLP_ENDPOINT="${RPL_OTLP_ENDPOINT:-${CI_RUNNER_HEARTBEAT_OTLP:-http://127.0.0.1:4319/v1/metrics}}"
NO_EMIT="${RPL_NO_EMIT:-0}"
# The warm-cache populator's per-run document (../warm-cache/, livespec-41w4)
# and the file recording the last run_id this sweep emitted from it — see
# "WARM-CACHE BUILD GAUGES" under the OTLP emission.
WARM_LAST_RUN="${RPL_WARM_LAST_RUN:-/var/lib/rancher/k3s/storage/.warm/last-run.json}"
WARM_STATE_FILE="${RPL_WARM_STATE_FILE:-/var/lib/ci-runner-k3s/warm-cache-last-emitted-run}"
# The budget's second home (../warm-cache/warm-cache-cronjob.yaml), read only
# when last-run.json does not carry budget_bytes/budget_files: `<ns>/<name>`
# with data keys `bytes` and `files`.
WARM_BUDGET_CONFIGMAP="${RPL_WARM_BUDGET_CONFIGMAP:-ci-warm-cache/warm-cache-budget}"
# The populator stalled when its last run finished more than this many sweep
# windows ago: 12 x 5 min = 1 h, two missed 30-minute schedules (the same
# 3600 s the ci-cache-warm-generation-stale trigger uses; this one reads the
# RUN's age, that one the generation's last-verified mtime).
WARM_STALE_TICKS="${RPL_WARM_STALE_TICKS:-12}"
# start-seed-cost budgets. Duration: research/005-006 measured the reflink
# seed at 3 s on the 12k-file generation and ~13 s on the old 191k-file one;
# 10 s is under the provisioner's 120 s helper ceiling by an order of
# magnitude and above the measured value by three. Size: empty means "the
# warm budget bytes" (a seed cannot legitimately exceed the generation it
# copies; the same number, so a chart draws one line).
SEED_SECONDS_BUDGET="${RPL_SEED_SECONDS_BUDGET:-10}"
SEED_BYTES_BUDGET="${RPL_SEED_BYTES_BUDGET:-}"
# Where the provisioner's work volumes live (`pvc-<uuid>_<ns>_<name>/`), the
# parent of the warm root; empty means "derive it from WARM_LAST_RUN".
STORAGE_ROOT="${RPL_STORAGE_ROOT:-}"
# Bounds (header, "EVERY READ IS BOUNDED"): the per-request timeout kubectl
# applies to each API call; the per-step deadline every external read runs
# under (timeout(1)); and the unit's own deadline, which the .service passes
# in beside its TimeoutStartSec so the step deadline can shrink to what is
# left of it. Empty deadline means unbounded (a hand run).
KUBECTL_REQUEST_TIMEOUT="${RPL_KUBECTL_REQUEST_TIMEOUT:-30s}"
STEP_TIMEOUT="${RPL_STEP_TIMEOUT:-30}"
DEADLINE_SECONDS="${RPL_DEADLINE_SECONDS:-}"
# api-unavailable (header): the API server's unit.
K3S_UNIT="${RPL_K3S_UNIT:-k3s.service}"

HOOK_SIGNATURE='Executing the custom container implementation failed'
# What a REFUSED API read looks like on kubectl's stderr — the server GONE,
# never merely slow: no timeout phrase belongs here (a slow API hits the
# deadline instead, and `TLS handshake timeout` is what an overloaded API
# returns under a burst). Verified sample, host 2026-09-06: `The connection
# to the server 127.0.0.1:1 was refused - did you specify the right host or
# port?`
API_REFUSAL_SIGNATURE='was refused|connection refused|unexpected EOF|EOF$|currently unable to handle the request|Service Unavailable|no route to host'
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
    --node-selector)            NODE_SELECTOR="${2:?$USAGE}"; shift 2 ;;
    --otlp-endpoint)            OTLP_ENDPOINT="${2:?$USAGE}"; shift 2 ;;
    --no-emit)                  NO_EMIT=1; shift ;;
    --warm-last-run)            WARM_LAST_RUN="${2:?$USAGE}"; shift 2 ;;
    --warm-budget-configmap)    WARM_BUDGET_CONFIGMAP="${2:?$USAGE}"; shift 2 ;;
    --warm-stale-ticks)         WARM_STALE_TICKS="${2:?$USAGE}"; shift 2 ;;
    --seed-seconds-budget)      SEED_SECONDS_BUDGET="${2:?$USAGE}"; shift 2 ;;
    --seed-bytes-budget)        SEED_BYTES_BUDGET="${2:?$USAGE}"; shift 2 ;;
    --storage-root)             STORAGE_ROOT="${2:?$USAGE}"; shift 2 ;;
    --request-timeout)          KUBECTL_REQUEST_TIMEOUT="${2:?$USAGE}"; shift 2 ;;
    --step-timeout)             STEP_TIMEOUT="${2:?$USAGE}"; shift 2 ;;
    --deadline-seconds)         DEADLINE_SECONDS="${2:?$USAGE}"; shift 2 ;;
    --k3s-unit)                 K3S_UNIT="${2:?$USAGE}"; shift 2 ;;
    -h|--help)                  echo "$USAGE"; exit 0 ;;
    *)                          echo "FATAL: unknown argument '$1'"$'\n'"$USAGE" >&2; exit 2 ;;
  esac
done

for v in PVC_PENDING_SECONDS WORKFLOW_PENDING_SECONDS KILLPOD_MIN ESCALATE_AFTER WARM_STALE_TICKS SEED_SECONDS_BUDGET STEP_TIMEOUT; do
  [[ "${!v}" =~ ^[0-9]+$ ]] || { echo "FATAL: ${v} must be a non-negative integer, got '${!v}'" >&2; exit 2; }
done
for v in SEED_BYTES_BUDGET DEADLINE_SECONDS; do
  [ -z "${!v}" ] || [[ "${!v}" =~ ^[0-9]+$ ]] || { echo "FATAL: ${v} must be empty or a non-negative integer, got '${!v}'" >&2; exit 2; }
done
[ "$STEP_TIMEOUT" -gt 0 ] || { echo "FATAL: STEP_TIMEOUT must be positive" >&2; exit 2; }
[[ "$KUBECTL_REQUEST_TIMEOUT" =~ ^[0-9]+(s|m|h)$ ]] || { echo "FATAL: --request-timeout must be <N>s, <N>m or <N>h, got '${KUBECTL_REQUEST_TIMEOUT}'" >&2; exit 2; }
case "$WARM_BUDGET_CONFIGMAP" in */*) ;; *) echo "FATAL: --warm-budget-configmap must be <namespace>/<name>, got '${WARM_BUDGET_CONFIGMAP}'" >&2; exit 2 ;; esac
[ -n "$STORAGE_ROOT" ] || STORAGE_ROOT="$(dirname "$(dirname "$WARM_LAST_RUN")")"
WARM_ROOT="$(dirname "$WARM_LAST_RUN")"
case "$NO_EMIT" in 0|1) ;; *) echo "FATAL: RPL_NO_EMIT must be 0 or 1, got '${NO_EMIT}'" >&2; exit 2 ;; esac
case "$WINDOW" in
  *s) WINDOW_SECONDS="${WINDOW%s}" ;;
  *m) WINDOW_SECONDS=$(( ${WINDOW%m} * 60 )) ;;
  *h) WINDOW_SECONDS=$(( ${WINDOW%h} * 3600 )) ;;
  *)  echo "FATAL: --window must be <N>s, <N>m or <N>h, got '${WINDOW}'" >&2; exit 2 ;;
esac
[[ "$WINDOW_SECONDS" =~ ^[0-9]+$ ]] || { echo "FATAL: --window must be <N>s, <N>m or <N>h, got '${WINDOW}'" >&2; exit 2; }

log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
# BOUNDED READS (header, "EVERY READ IS BOUNDED"). `bounded STEP cmd...` runs
# cmd under timeout(1) with the smaller of STEP_TIMEOUT and what is left of
# the unit's deadline (minus DEADLINE_RESERVE for the report and the POST);
# when nothing is left the step is not started at all. A step that timed out
# or was skipped is recorded by name in DEADLINE_FILE — a file, not a
# variable, because most reads run inside a process substitution whose shell
# cannot set the caller's variables — and the exit status is passed through
# (124 = timed out; 125 here = skipped), so a caller's `|| true` keeps the
# sweep going as before. STEP names the class the read feeds (or `emit` /
# `precheck`), which is how the emitter later knows which zero is false.
# `kc STEP args...` is kubectl with the per-request timeout, always through
# `bounded`; no kubectl call in this file may bypass it, and none may --watch
# or --follow.
SWEEP_START_NS="$(date +%s%N)"
DEADLINE_RESERVE=15
# fd 3 is the sweep's real stderr: a deadline message must reach the journal
# even from a call site that silences its read's own stderr with 2>/dev/null.
exec 3>&2
DEADLINE_FILE="$(mktemp)"
trap 'rm -f "$DEADLINE_FILE"' EXIT
# GNU timeout exits 124 on expiry with or without `-k N` (TERM, then KILL);
# uutils' timeout (Ubuntu 25.10+ coreutils) exits 125 on expiry when `-k` is
# given — observed on 0.2.2 — which this sweep would read as "did not time
# out". Probe with a REAL expiry (0.2 s) and use the kill-after form only
# where expiry still reads 124; without it a child that ignores TERM is left
# to the unit's deadline.
if timeout -k 0.2 0.2 sleep 2 >/dev/null 2>&1; [ $? -eq 124 ]; then TIMEOUT_KILL=(-k 5); else TIMEOUT_KILL=(); fi
sweep_elapsed_s() { printf '%s' "$(( ($(date +%s%N) - SWEEP_START_NS) / 1000000000 ))"; }
bounded() {
  local step="$1" limit="$STEP_TIMEOUT" left rc
  shift
  if [ -n "$DEADLINE_SECONDS" ]; then
    left=$(( DEADLINE_SECONDS - $(sweep_elapsed_s) - DEADLINE_RESERVE ))
    if [ "$left" -lt 1 ]; then
      echo "  ${step}: SKIPPED — ${DEADLINE_SECONDS}s deadline has $(( left + DEADLINE_RESERVE ))s left, reserved for the report" >&3
      printf '%s skipped\n' "$step" >> "$DEADLINE_FILE"
      return 125
    fi
    [ "$left" -lt "$limit" ] && limit="$left"
  fi
  timeout "${TIMEOUT_KILL[@]}" "$limit" "$@"
  rc=$?
  if [ "$rc" -eq 124 ]; then
    echo "  ${step}: read hit its ${limit}s step deadline ($*)" >&3
    printf '%s timeout\n' "$step" >> "$DEADLINE_FILE"
  fi
  return "$rc"
}
# kc also records a REFUSED read (API_REFUSAL_SIGNATURE on kubectl's stderr,
# exit status other than the deadline's 124) in API_REFUSED_FILE for the
# api-unavailable class, then forwards the stderr unchanged so every caller
# sees exactly what it saw before.
API_REFUSED_FILE="$(mktemp)"
trap 'rm -f "$DEADLINE_FILE" "$API_REFUSED_FILE"' EXIT
kc() {
  local step="$1" errf rc
  shift
  errf="$(mktemp)"
  bounded "$step" kubectl --request-timeout="$KUBECTL_REQUEST_TIMEOUT" "$@" 2>"$errf"
  rc=$?
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 124 ] && grep -q -E "$API_REFUSAL_SIGNATURE" "$errf" 2>/dev/null; then
    printf '%s %s\n' "$step" "$(tr '\n' ' ' <"$errf" | cut -c1-160)" >> "$API_REFUSED_FILE"
  fi
  cat "$errf" >&2 2>/dev/null
  rm -f "$errf"
  return "$rc"
}

# One gauge metric carrying one integer datapoint — the heartbeat's shape.
# $1 name, $2 description, $3 unit, $4 value, $5 timeUnixNano.
gauge_json() {
  printf '{"name":"%s","description":"%s","unit":"%s","gauge":{"dataPoints":[{"asInt":"%s","timeUnixNano":"%s"}]}}' "$1" "$2" "$3" "$4" "$5"
}
# The same, with a floating-point datapoint (the proxy hit ratio).
gauge_double_json() {
  printf '{"name":"%s","description":"%s","unit":"%s","gauge":{"dataPoints":[{"asDouble":%s,"timeUnixNano":"%s"}]}}' "$1" "$2" "$3" "$4" "$5"
}
# ONE OTLP/HTTP metrics POST of the comma-joined metric objects in $1, in
# the heartbeat's resource/scope shape (see "OTLP EMISSION"); prints curl's
# error on failure, nothing on success.
otlp_post() {
  local payload
  payload="$(cat <<JSON
{"resourceMetrics":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"ci-runner-lifecycle"}},{"key":"host.name","value":{"stringValue":"$(hostname)"}}]},"scopeMetrics":[{"scope":{"name":"runner-pod-lifecycle"},"metrics":[$1]}]}]}
JSON
)"
  { curl --silent --show-error --fail --max-time 10 -X POST "${OTLP_ENDPOINT}" -H 'Content-Type: application/json' -d "${payload}" >/dev/null; } 2>&1
}
# The api-unavailable gauge ALONE, for the sweep that cannot read anything
# else because /readyz itself was refused: count 1 plus the wall clock,
# best-effort, before the fail-closed exit 2.
emit_api_unavailable_alone() {
  local now_ns err
  [ "$NO_EMIT" = 0 ] && command -v curl >/dev/null || return 0
  now_ns="$(date +%s%N)"
  if err="$(otlp_post "$(gauge_json livespec.ci_lifecycle.api-unavailable "runner-pod lifecycle sweep: count reported for class api-unavailable (0 = clean)" "{findings}" 1 "$now_ns"),$(gauge_double_json livespec.ci_lifecycle.sweep_seconds "This sweep's wall clock at the emit POST" "s" "$(sweep_elapsed_s).0" "$now_ns")")"; then
    echo "  emit: livespec.ci_lifecycle.api-unavailable=1 (the /readyz precheck was refused; nothing else could be read) -> ${OTLP_ENDPOINT}"
  else
    echo "  emit: POST to ${OTLP_ENDPOINT} FAILED (${err:-no detail}); api-unavailable=1 not posted" >&2
  fi
  return 0
}
# Every step recorded in DEADLINE_FILE, space-separated `<step>:<how>`,
# deduplicated (a class with two reads records twice), or empty.
# `deadline_hits classes` lists only the reads that feed a CLASS: `emit` (the
# emitter's own Kueue/node reads, best-effort by contract) and `precheck`
# never decide the exit code — a sweep whose ten classes all completed is a
# reading even when the shrinking deadline skipped the last two gauge reads,
# which under a burst is the common case, not an incomplete sweep.
deadline_hits() { [ -s "$DEADLINE_FILE" ] && awk -v classes="${1:-}" '!seen[$0]++ && !(classes != "" && ($1 == "emit" || $1 == "precheck")) {printf "%s%s:%s", (n++?" ":""), $1, $2}' "$DEADLINE_FILE"; printf ''; }
deadline_hit_for() { grep -q "^$1 " "$DEADLINE_FILE" 2>/dev/null; }
# Whether a read feeding class $1 hit its deadline: the class's own reads,
# plus the shared `pods` listing for the two classes it feeds.
class_read_hit() {
  deadline_hit_for "$1" && return 0
  case "$1" in pvc-pending|containerd-deadline) deadline_hit_for pods ;; *) return 1 ;; esac
}

# systemd's TimeoutStartSec (or a `systemctl stop`) arrives as SIGTERM to the
# whole cgroup: the child read dies with it, then this trap runs. One line
# that names the kill as a kill — the streak, the findings so far and the
# gauges are NOT written, because a half-swept node is not a reading.
# shellcheck disable=SC2329  # invoked by the trap below
on_term() {
  # shellcheck disable=SC2016  # the backticks are operator-facing text
  printf '\n== KILLED: SIGTERM after %ss (the unit'"'"'s TimeoutStartSec=%s deadline, or a stop). NOT a stall finding: the sweep did not finish; `systemctl show -p Result scan-runner-pod-lifecycle.service` reads `timeout` for the deadline. Steps recorded before the kill: %s ==\n' "$(sweep_elapsed_s)" "${DEADLINE_SECONDS:-unset}" "$(deadline_hits)"
  exit 2
}
trap on_term TERM INT

if [ -n "$DEADLINE_SECONDS" ]; then
  echo "sweep start: deadline ${DEADLINE_SECONDS}s (the unit's TimeoutStartSec); per-step ${STEP_TIMEOUT}s, kubectl --request-timeout=${KUBECTL_REQUEST_TIMEOUT}. A run that ends without a CLEAN, STALL, INCOMPLETE or KILLED line was killed by systemd — read Result=timeout, not a finding."
else
  echo "sweep start: no unit deadline (hand run); per-step ${STEP_TIMEOUT}s, kubectl --request-timeout=${KUBECTL_REQUEST_TIMEOUT}"
fi

# Preconditions, fail-closed: a scan that cannot read an input must not report
# a clean node it did not look at.
command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH" >&2; exit 2; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"
command -v journalctl >/dev/null || { echo "FATAL: journalctl not found on PATH" >&2; exit 2; }
command -v timeout >/dev/null || { echo "FATAL: timeout not found on PATH (coreutils)" >&2; exit 2; }
# A precheck that hit its deadline says so — "run as root" would send the
# operator after the wrong cause.
# (`rc=$?` is taken from the command itself, never after a `!` — bash sets
# $? to the NEGATED status there, which read every failure as rc 0.)
rc=0; bounded precheck journalctl -u k3s -n 1 -q --no-pager >/dev/null 2>&1 || rc=$?
if [ "$rc" -ne 0 ]; then
  if [ "$rc" -eq 124 ]; then echo "FATAL: the k3s journal read hit its ${STEP_TIMEOUT}s deadline (journald busy or the disk stalled), not a permission failure" >&2; else echo "FATAL: cannot read the k3s unit's journal (rc ${rc}; run as root or a member of systemd-journal)" >&2; fi
  exit 2
fi
[ -r "$CONTAINERD_LOG" ] || { echo "FATAL: cannot read ${CONTAINERD_LOG} (run as root, or pass --containerd-log)" >&2; exit 2; }
rc=0; kc precheck get --raw /readyz >/dev/null 2>&1 || rc=$?
if [ "$rc" -ne 0 ]; then
  if [ "$rc" -eq 124 ]; then echo "FATAL: /readyz via ${KUBECONFIG} did not answer within the ${STEP_TIMEOUT}s deadline" >&2
  elif [ -s "$API_REFUSED_FILE" ]; then
    echo "FATAL: the API server REFUSED /readyz via ${KUBECONFIG} ($(head -1 "$API_REFUSED_FILE" | cut -d' ' -f2- | cut -c1-140)) — api-unavailable; the class is posted alone and the sweep exits 2 because nothing else can be read" >&2
    emit_api_unavailable_alone || true
  else echo "FATAL: the API server is not answering /readyz via ${KUBECONFIG} (rc ${rc})" >&2; fi
  exit 2
fi

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
# Classes whose ZERO must not be emitted because an input the judgement needs
# was unreadable this sweep (a non-zero count is a true reading regardless;
# only a zero can be false). Space-separated names; see the emitter.
OMIT_ZERO_CLASSES=" "
omit_zero() { OMIT_ZERO_CLASSES="${OMIT_ZERO_CLASSES}${1} "; }

# ---------------------------------------------------------------------------
log "1. pvc-pending: PVCs in ${NAMESPACE} Pending > ${PVC_PENDING_SECONDS}s (claims owned by scheduling-gated pods excluded)"
# THE ONE POD LISTING of the runners namespace, shared by this step (gates,
# UIDs) and step 4 (terminated reasons): a full `get pods` is the heaviest
# read the sweep makes under a burst, so it is made once. Record layout:
#   <name>|<uid>|<gate names, space-separated>|<terminated reasons>
# When it fails or hits its deadline the set of gated UIDs is empty, gated
# claims are counted as pending — the pre-2026-09-06 over-count, named as
# such, never a silent under-count — and the pvc-gated gauge is withheld.
POD_ROWS=""; pods_read=1
if POD_ROWS="$(kc pods -n "$NAMESPACE" get pods -o jsonpath='{range .items[*]}{.metadata.name}|{.metadata.uid}|{range .spec.schedulingGates[*]}{.name}{" "}{end}|{range .status.containerStatuses[*]}{.state.terminated.reason}{" "}{end}{"\n"}{end}' 2>&1)"; then :; else
  pods_read=0
  echo "  could not list pods ($(printf '%s' "$POD_ROWS" | head -1)); gated claims will be counted as pending; livespec.ci_lifecycle.pvc-gated withheld" >&2
  POD_ROWS=""
fi
# The runner pods' work volumes are GENERIC EPHEMERAL volumes (ARC kubernetes
# container mode: `ephemeral.volumeClaimTemplate`), so the PVC is created by
# the ephemeral-volume controller, named `<pod>-work`, and OWNED by the pod
# through metadata.ownerReferences — `spec.volumes[*].persistentVolumeClaim`
# is empty on every runner pod, which is why keying on claimName (the first
# cut of this exclusion, 2026-09-06) matched nothing. The key is therefore
# the owner's UID, never its name: a same-name successor pod must not shadow
# a dead owner's stale claim (the livespec-n5eudb deadlock shape).
gated_uids=" "
while IFS='|' read -r name uid gates _; do
  [ -n "$name" ] && [ -n "${gates// /}" ] && [ -n "$uid" ] || continue
  gated_uids="${gated_uids}${uid} "
done <<< "$POD_ROWS"
# WHEN a Pending claim's clock starts. Under WaitForFirstConsumer nothing is
# provisioned until the scheduler has picked a node and the claim carries
# the `volume.kubernetes.io/selected-node` ANNOTATION; a claim whose pod
# sat ten minutes behind a Kueue gate is then ten minutes old and seconds
# into provisioning, and aging it from creationTimestamp spikes this class
# after every admission wave. So: no annotation = nothing asked of the
# provisioner yet, not counted; with it, the clock is the time of the
# claim's managedFields entry whose fieldsV1 OWNS that annotation key —
# which is `kube-scheduler` upstream and the single `k3s` entry on k3s,
# where every in-process component (scheduler, ephemeral-volume and PV
# controllers) writes as one manager named `k3s` (verified live on
# v1.36.2: every runner -work claim carries exactly `k3s/Update`, plus
# `k3s/Update/status` once Bound). The second cut of this clock matched
# the manager NAME against `*scheduler*`, which on k3s matched nothing, so
# every claim read "not requested" and the class emitted a true-looking
# zero — the same shape as the blocker before it. Matching the FIELD the
# entry owns is what holds on both. The entry's time moves once more when
# the provisioner strips selected-node and the scheduler re-selects (a
# legitimate clock restart), and the pod's PodScheduled.lastTransitionTime
# cannot serve at all: a gate release keeps the condition False and a
# same-status update keeps its time. creationTimestamp is the fallback
# only when the owning entry's time does not parse. This needs the JSON
# form (managedFields' fieldsV1 is not addressable by jsonpath), read by
# the python3 the sweep already uses. A listing that FAILS (any rc, not
# only the deadline) withholds both pvc-pending's zero and the pvc-gated
# gauge: an empty listing is not a reading.
pvc_hits=0; pvc_gated=0; pvc_unrequested=0; pvc_read=1; pvc_rows=""
pvc_json="$(mktemp)"
if kc pvc-pending -n "$NAMESPACE" get pvc --show-managed-fields -o json >"$pvc_json" 2>/dev/null && pvc_rows="$(python3 - "$pvc_json" <<'PY'
import json, sys
KEY = "volume.kubernetes.io/selected-node"
def owns(node, key):
    if isinstance(node, dict):
        return ("f:" + key) in node or any(owns(v, key) for v in node.values())
    return False
d = json.load(open(sys.argv[1]))
for it in d.get("items", []):
    if (it.get("status") or {}).get("phase") != "Pending":
        continue
    md = it.get("metadata") or {}
    owners = " ".join(str(o.get("uid", "")) for o in md.get("ownerReferences") or [])
    selected = (md.get("annotations") or {}).get(KEY, "")
    since = ""
    for entry in md.get("managedFields") or []:
        if owns(entry.get("fieldsV1") or {}, KEY):
            since = str(entry.get("time") or "")
    print(f"{md.get('name','')}|{md.get('creationTimestamp','')}|{owners}|{selected}|{since}")
PY
)"; then :; else
  pvc_read=0; pvc_rows=""
  echo "  could not list PVCs: pvc-pending's zero and livespec.ci_lifecycle.pvc-gated withheld this sweep" >&2
  omit_zero pvc-pending
fi
rm -f "$pvc_json"
while IFS='|' read -r name created owners selected since; do
  [ -n "$name" ] || continue
  gated=0
  for uid in $owners; do case "$gated_uids" in *" ${uid} "*) gated=1 ;; esac; done
  [ "$gated" = 1 ] && { pvc_gated=$((pvc_gated+1)); continue; }
  [ -n "$selected" ] || { pvc_unrequested=$((pvc_unrequested+1)); continue; }
  age="$(age_seconds "$since")"
  [ "$age" != unknown ] || age="$(age_seconds "$created")"
  if [ "$age" != unknown ] && [ "$age" -ge "$PVC_PENDING_SECONDS" ]; then
    pvc_hits=$((pvc_hits+1)); add_detail "    pvc=${name} pending_for=${age}s (since node ${selected} was selected)"
  fi
done <<< "$pvc_rows"
echo "  ${pvc_hits} PVC(s) Pending longer than ${PVC_PENDING_SECONDS}s since their node was selected; ${pvc_gated} Pending claim(s) owned by scheduling-gated pods excluded; ${pvc_unrequested} Pending with no node selected yet (not counted)"
[ "$pvc_hits" -gt 0 ] && add_finding pvc-pending "$pvc_hits"

# ---------------------------------------------------------------------------
log "2. bind-deadline: scheduler volume-bind expiries in the k3s journal, last ${WINDOW}"
bind_hits="$(bounded bind-deadline journalctl -u k3s --since "@${CUTOFF_EPOCH}" --no-pager -q 2>/dev/null | grep -c "$BIND_SIGNATURE" || true)"
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
emfile_hits="$({ bounded inotify-emfile tac "$CONTAINERD_LOG" 2>/dev/null || true; } | awk -v cut="$CUTOFF_ISO" -v sig="$EMFILE_SIGNATURE" '
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
# Container states come from step 1's single pod listing (POD_ROWS).
while IFS='|' read -r name _ _ reasons; do
  [ -n "$name" ] || continue
  case " $reasons " in *" StartError "*) starterror_hits=$((starterror_hits+1)); add_detail "    pod=${name} container StartError";; esac
done <<< "$POD_ROWS"
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
done < <(kc containerd-deadline -n "$NAMESPACE" get events -o jsonpath='{range .items[*]}{.lastTimestamp}|{.eventTime}|{.reason}|{.involvedObject.name}|{.message}{"\n"}{end}' 2>/dev/null || true)
echo "  ${starterror_hits} StartError container(s); ${create_hits} create-path deadline event(s); ${killpod_hits} FailedKillPod event(s) (burst threshold ${KILLPOD_MIN})"
if [ "$starterror_hits" -gt 0 ] || [ "$create_hits" -gt 0 ] || [ "$killpod_hits" -ge "$KILLPOD_MIN" ]; then
  add_finding containerd-deadline "$(( starterror_hits + create_hits + killpod_hits ))"
  [ "$killpod_hits" -ge "$KILLPOD_MIN" ] && add_detail "    FailedKillPod=${killpod_hits} in ${WINDOW} (teardown starvation)"
fi

# ---------------------------------------------------------------------------
log "5. hook-failure: '${HOOK_SIGNATURE}' in runner logs, last ${WINDOW}; -workflow pods Pending > ${WORKFLOW_PENDING_SECONDS}s"
hook_hits=0
# ONE bounded read for every runner pod's window, not one call per pod: a
# per-pod loop over a 64-slot burst is 64 request timeouts of exposure, which
# no step deadline can hold. `--prefix` tags each line `[pod/<name>/runner]`
# so the count is still per pod; `--ignore-errors` skips a pod that vanished
# between the listing and the read (churn, not error). No --follow, ever.
while IFS= read -r pod; do
  [ -n "$pod" ] || continue
  hook_hits=$((hook_hits+1)); add_detail "    runner=${pod} logged the ARC hook failure"
done < <(kc hook-failure -n "$NAMESPACE" logs -l app.kubernetes.io/component=runner -c runner --since="$WINDOW" --prefix --ignore-errors 2>/dev/null | grep -F "$HOOK_SIGNATURE" | sed -n 's|^\[pod/\([^/]*\)/[^]]*\].*|\1|p' | sort -u || true)
wf_hits=0
while IFS='|' read -r name created; do
  [ -n "$name" ] || continue
  case "$name" in *-workflow) ;; *) continue ;; esac
  age="$(age_seconds "$created")"
  if [ "$age" != unknown ] && [ "$age" -ge "$WORKFLOW_PENDING_SECONDS" ]; then
    wf_hits=$((wf_hits+1)); add_detail "    workflow-pod=${name} pending_for=${age}s"
  fi
done < <(kc hook-failure -n "$NAMESPACE" get pods --field-selector=status.phase=Pending -o jsonpath='{range .items[*]}{.metadata.name}|{.metadata.creationTimestamp}{"\n"}{end}' 2>/dev/null || true)
echo "  ${hook_hits} runner log(s) with the hook failure; ${wf_hits} workflow pod(s) Pending longer than ${WORKFLOW_PENDING_SECONDS}s (best-effort: a failure whose runner pod is already gone is invisible here; the durable detection is the job-side ci-hook-failure-burst trigger)"
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
done < <(kc stale-listener -n "$SYSTEMS_NAMESPACE" get pods -o jsonpath='{range .items[*]}{.metadata.name}|{.status.phase}|{range .status.containerStatuses[*]}{.state.waiting.reason}{" "}{end}{"\n"}{end}' 2>/dev/null || true)
ers=" $(kc stale-listener -n "$NAMESPACE" get ephemeralrunnerset -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true) "
stale_hits=0
while IFS='|' read -r name ref; do
  [ -n "$name" ] || continue
  case "$ers" in *" ${ref} "*) ;; *)
    stale_hits=$((stale_hits+1)); add_detail "    AutoscalingListener=${name} references EphemeralRunnerSet=${ref:-<empty>} which does not exist (delete the listener; the controller recreates it)";;
  esac
done < <(kc stale-listener -n "$SYSTEMS_NAMESPACE" get autoscalinglistener -o jsonpath='{range .items[*]}{.metadata.name}|{.spec.ephemeralRunnerSetName}{"\n"}{end}' 2>/dev/null || true)
echo "  ${listener_hits} listener pod(s) not Running/healthy; ${stale_hits} stale EphemeralRunnerSet reference(s)"
[ $(( listener_hits + stale_hits )) -gt 0 ] && add_finding stale-listener "$(( listener_hits + stale_hits ))"

# ---------------------------------------------------------------------------
log "7. capacity-absent: allocatable ci-runner.io/churn-slot on ${NODE_SELECTOR} nodes vs the ClusterQueues' nominalQuota sum"
# Kueue admits against the queues' quota; the scheduler places against the
# node's allocatable. When the node has none of the resource — it is a
# node-status patch, not kubelet-owned, and a dependency-failed boot leaves
# the reapply unit unrun (2026-09-04) — every admitted runner pod is
# unschedulable and no capacity signal says so. Node side: one line per
# selected node, `<name>|<allocatable, or empty>`; a node without the key is
# a hit and contributes 0 to the total.
cap_total=0; cap_nodes=0; cap_missing=0
while IFS='|' read -r name have; do
  [ -n "$name" ] || continue
  cap_nodes=$((cap_nodes+1))
  if [[ "$have" =~ ^[0-9]+$ ]]; then
    cap_total=$((cap_total+have))
  else
    cap_missing=$((cap_missing+1)); add_detail "    node=${name} allocatable ci-runner.io/churn-slot=${have:-<absent>} (systemctl start reapply-node-extended-resource.service)"
  fi
done < <(kc capacity-absent get nodes -l "$NODE_SELECTOR" -o jsonpath='{range .items[*]}{.metadata.name}|{.status.allocatable.ci-runner\.io/churn-slot}{"\n"}{end}' 2>/dev/null || true)
# Quota side: every ClusterQueue's `<resource>=<nominalQuota>` tokens, summed
# over the churn-slot ones (the phase-1 proof queue is cpu/memory and adds
# nothing). The values are plain integers by derivation (../kueue/DERIVATION.md).
quota_sum=0; quota_queues=0
while IFS='|' read -r name tokens; do
  [ -n "$name" ] || continue
  for t in $tokens; do
    case "$t" in
      ci-runner.io/churn-slot=*)
        q="${t#*=}"
        [[ "$q" =~ ^[0-9]+$ ]] || continue
        quota_sum=$((quota_sum+q)); quota_queues=$((quota_queues+1)) ;;
    esac
  done
done < <(kc capacity-absent get clusterqueue -o jsonpath='{range .items[*]}{.metadata.name}|{range .spec.resourceGroups[*]}{range .flavors[*]}{range .resources[*]}{.name}={.nominalQuota}{" "}{end}{end}{end}{"\n"}{end}' 2>/dev/null || true)
capacity_hits=$cap_missing
if [ "$quota_sum" -gt "$cap_total" ]; then
  capacity_hits=$((capacity_hits+1)); add_detail "    ClusterQueue nominalQuota sum=${quota_sum} over ${quota_queues} queue(s) exceeds node allocatable total=${cap_total} (shortfall $((quota_sum - cap_total)))"
fi
echo "  ${cap_total} allocatable across ${cap_nodes} node(s), ${cap_missing} without the resource; nominalQuota sum ${quota_sum} across ${quota_queues} queue(s)"
[ "$capacity_hits" -gt 0 ] && add_finding capacity-absent "$capacity_hits"

# ---------------------------------------------------------------------------
log "8. warm-cache-oversize: the live warm uv generation vs its budget; the populator's last run vs ${WARM_STALE_TICKS} x ${WINDOW}"
# Three inputs, each read once, each allowed to be absent (the class's zero
# is then withheld, header "FAIL-CLOSED ON ITS OWN INPUTS"):
#   the budget    last-run.json's budget_bytes/budget_files (the numbers the
#                 populator actually enforced), else the ConfigMap they come
#                 from;
#   the live      $WARM_ROOT/uv -> uv-generations/<stamp>, read through the
#   generation    generation's OWN .warm-manifest.json — not last-run.json's
#                 generation_* fields, which on a refused run describe the
#                 refused candidate; its age is the <stamp> (the populator's
#                 %Y%m%dT%H%M%SZ publish time), the manifest's
#                 published_at_epoch as the fallback;
#   the last run  last-run.json's finished_uv_at_epoch (started_at_epoch as
#                 the fallback) — the populator writes it on every run,
#                 refused and rejected ones included, so its age is the
#                 populator's liveness, unlike the generation's age, which a
#                 healthy populator leaves alone while nothing changes.
warm_budget_bytes=""; warm_budget_files=""; warm_budget_from=""
warm_live_gen=""; warm_live_bytes=""; warm_live_files=""; warm_live_age=""
warm_last_run_age=""
if [ -r "$WARM_LAST_RUN" ] && warm_rows="$(python3 - "$WARM_LAST_RUN" <<'PY' 2>/dev/null
import json, sys
d = json.load(open(sys.argv[1]))
for k in ("budget_bytes", "budget_files", "finished_uv_at_epoch", "started_at_epoch"):
    if d.get(k) is not None:
        print(f"{k}={int(d[k])}")
PY
)"; then
  warm_budget_bytes="$(printf '%s\n' "$warm_rows" | sed -n 's/^budget_bytes=//p')"
  warm_budget_files="$(printf '%s\n' "$warm_rows" | sed -n 's/^budget_files=//p')"
  [ -n "$warm_budget_bytes" ] && [ -n "$warm_budget_files" ] && warm_budget_from="last-run.json"
  last_epoch="$(printf '%s\n' "$warm_rows" | sed -n 's/^finished_uv_at_epoch=//p')"
  [ -n "$last_epoch" ] || last_epoch="$(printf '%s\n' "$warm_rows" | sed -n 's/^started_at_epoch=//p')"
  [[ "$last_epoch" =~ ^[0-9]+$ ]] && warm_last_run_age=$(( NOW_EPOCH - last_epoch ))
elif [ -d "$WARM_ROOT" ] && [ ! -e "$WARM_LAST_RUN" ]; then
  # The warm root exists (the populator's home is there) but no run has ever
  # written last-run.json: a populator that never ran, or was rebuilt and
  # has not run since, is the stalled case, not an unknown one.
  warm_last_run_age="never"
elif [ -d "$WARM_ROOT" ]; then
  echo "  ${WARM_LAST_RUN} exists but is unreadable or unparseable: the populator's last-run age (and its budget) unknown — a populator writing a document this sweep cannot read is a defect to look at, not a stall"
else
  echo "  no warm root at ${WARM_ROOT}: the populator has never run on this node, or the path is wrong; last-run age and budget unknown"
fi
if [ -z "$warm_budget_from" ]; then
  cm_ns="${WARM_BUDGET_CONFIGMAP%%/*}"; cm_name="${WARM_BUDGET_CONFIGMAP#*/}"
  if cm_row="$(kc warm-cache-oversize -n "$cm_ns" get configmap "$cm_name" -o jsonpath='{.data.bytes}|{.data.files}' 2>&1)" \
     && [[ "${cm_row%%|*}" =~ ^[0-9]+$ ]] && [[ "${cm_row#*|}" =~ ^[0-9]+$ ]]; then
    warm_budget_bytes="${cm_row%%|*}"; warm_budget_files="${cm_row#*|}"; warm_budget_from="ConfigMap ${WARM_BUDGET_CONFIGMAP}"
  else
    warm_budget_bytes=""; warm_budget_files=""
    echo "  budget unreadable from last-run.json AND ConfigMap ${WARM_BUDGET_CONFIGMAP} ($(printf '%s' "$cm_row" | head -1)): the size legs cannot be judged"
  fi
fi
if [ -L "${WARM_ROOT}/uv" ]; then
  gen_link="$(readlink "${WARM_ROOT}/uv")"
  case "$gen_link" in /*) gen_dir="$gen_link" ;; *) gen_dir="${WARM_ROOT}/${gen_link}" ;; esac
  warm_live_gen="${gen_dir##*/}"
  if gen_rows="$(python3 - "${gen_dir}/.warm-manifest.json" <<'PY' 2>/dev/null
import json, sys
d = json.load(open(sys.argv[1]))
print(f"generation_bytes={int(d['generation_bytes'])}")
print(f"generation_files={int(d['generation_files'])}")
if d.get("published_at_epoch") is not None:
    print(f"published_at_epoch={int(d['published_at_epoch'])}")
PY
)"; then
    warm_live_bytes="$(printf '%s\n' "$gen_rows" | sed -n 's/^generation_bytes=//p')"
    warm_live_files="$(printf '%s\n' "$gen_rows" | sed -n 's/^generation_files=//p')"
    pub_epoch=""
    if [[ "$warm_live_gen" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
      s="$warm_live_gen"
      pub_epoch="$(date -u -d "${s:0:4}-${s:4:2}-${s:6:2}T${s:9:2}:${s:11:2}:${s:13:2}Z" +%s 2>/dev/null || true)"
    fi
    [[ "$pub_epoch" =~ ^[0-9]+$ ]] || pub_epoch="$(printf '%s\n' "$gen_rows" | sed -n 's/^published_at_epoch=//p')"
    [[ "$pub_epoch" =~ ^[0-9]+$ ]] && warm_live_age=$(( NOW_EPOCH - pub_epoch ))
  else
    echo "  live generation ${warm_live_gen} has no readable .warm-manifest.json (${gen_dir}): its size and age unknown"
  fi
else
  echo "  ${WARM_ROOT}/uv is not a symlink: no published warm generation (every job seeds cold); size and age unknown"
fi
oversize_hits=0
if [ -n "$warm_budget_from" ] && [ -n "$warm_live_bytes" ]; then
  if [ "$warm_live_bytes" -gt "$warm_budget_bytes" ]; then
    oversize_hits=$((oversize_hits+1)); add_detail "    generation=${warm_live_gen} bytes=${warm_live_bytes} OVER budget ${warm_budget_bytes} (${warm_budget_from})"
  fi
  if [ "$warm_live_files" -gt "$warm_budget_files" ]; then
    oversize_hits=$((oversize_hits+1)); add_detail "    generation=${warm_live_gen} files=${warm_live_files} OVER budget ${warm_budget_files} (${warm_budget_from})"
  fi
fi
warm_stale_after=$(( WARM_STALE_TICKS * WINDOW_SECONDS ))
if [ "$warm_last_run_age" = never ]; then
  oversize_hits=$((oversize_hits+1)); add_detail "    populator STALLED: ${WARM_ROOT} exists but no run has written ${WARM_LAST_RUN##*/} (never ran, or rebuilt and not run since; kubectl -n ci-warm-cache get cronjob,jobs)"
elif [ -n "$warm_last_run_age" ] && [ "$warm_last_run_age" -gt "$warm_stale_after" ]; then
  oversize_hits=$((oversize_hits+1)); add_detail "    populator STALLED: last run finished ${warm_last_run_age}s ago, over ${WARM_STALE_TICKS} x ${WINDOW} = ${warm_stale_after}s (kubectl -n ci-warm-cache get cronjob,jobs; the generation ages unrefreshed)"
fi
echo "  generation=${warm_live_gen:-none} bytes=${warm_live_bytes:-unknown} files=${warm_live_files:-unknown} age=${warm_live_age:-unknown}s; budget bytes=${warm_budget_bytes:-unknown} files=${warm_budget_files:-unknown} (${warm_budget_from:-unreadable}); last populator run $([ "$warm_last_run_age" = never ] && printf 'NEVER (no last-run.json)' || printf '%ss ago' "${warm_last_run_age:-unknown}") (stale past ${warm_stale_after}s)"
if [ -z "$warm_budget_from" ] || [ -z "$warm_live_bytes" ] || [ -z "$warm_last_run_age" ]; then
  omit_zero warm-cache-oversize
  [ "$oversize_hits" -gt 0 ] || echo "  warm-cache-oversize judged on partial inputs and found nothing: its zero is withheld from the gauges"
fi
[ "$oversize_hits" -gt 0 ] && add_finding warm-cache-oversize "$oversize_hits"

# ---------------------------------------------------------------------------
log "9. start-seed-cost: the newest seeded work volume under ${STORAGE_ROOT} — seed bytes vs budget, seed seconds vs ${SEED_SECONDS_BUDGET}s"
# The newest `pvc-*/_warm/.uv-generation` marker by mtime names the volume
# most recently seeded (the marker is written last by the provisioner's setup
# script, ../local-path-provisioner/local-path-provisioner.yaml). Size is
# `du -sb` of its `_warm/uv` — the seed plus whatever the job has written
# into the cache since, which the NEWEST volume keeps smallest. Duration is
# the volume's own record: `_warm` is born (stat %W) by the mkdir that opens
# the seed and the marker's mtime closes it. A filesystem without birth
# times reports %W as 0; the seconds gauge is then omitted, never 0.
seed_vol=""; seed_gen=""; seed_bytes=""; seed_seconds=""
newest="$(bounded start-seed-cost find "$STORAGE_ROOT" -mindepth 3 -maxdepth 3 -path '*/pvc-*/_warm/.uv-generation' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 || true)"
if [ -n "$newest" ]; then
  seed_marker="${newest#* }"; seed_dir="${seed_marker%/.uv-generation}"
  seed_vol="${seed_dir%/_warm}"; seed_vol="${seed_vol##*/}"
  seed_gen="$(head -c 64 "$seed_marker" 2>/dev/null | tr -d '\n' || true)"
  seed_stat=1
  # The volume can be torn down between the find and the du (a job ending);
  # that is churn, named as such, distinct from a du that hit its deadline.
  if du_out="$(bounded start-seed-cost du -sb "${seed_dir}/uv" 2>/dev/null)"; then
    seed_bytes="${du_out%%[[:space:]]*}"
    [[ "$seed_bytes" =~ ^[0-9]+$ ]] || { seed_bytes=""; echo "  du -sb ${seed_dir}/uv printed no size: livespec.ci_seed.bytes omitted"; }
  else
    rc=$?; seed_bytes=""
    # Every further touch of this path is bounded too: a du that hit its
    # deadline on a stalled volume must not be followed by an unbounded
    # stat or test on the same path (a D-state read would hold the sweep
    # to the unit's deadline), so after a 124 the volume is left alone.
    if [ "$rc" -eq 124 ]; then
      echo "  du -sb ${seed_dir}/uv hit its step deadline: livespec.ci_seed.* omitted; the volume's timestamps are not read either (same path)"; seed_stat=0
    else
      rc2=0; bounded start-seed-cost test -d "${seed_dir}/uv" >/dev/null 2>&1 || rc2=$?
      if [ "$rc2" -eq 1 ]; then echo "  ${seed_vol} was deleted between the listing and the du (a job ended): livespec.ci_seed.* omitted this sweep"; seed_vol=""; seed_gen=""; seed_stat=0
      elif [ "$rc2" -eq 124 ]; then echo "  ${seed_dir}/uv did not answer a bounded test -d: livespec.ci_seed.* omitted"; seed_stat=0
      else echo "  du -sb ${seed_dir}/uv failed (rc ${rc}): livespec.ci_seed.bytes omitted"; fi
    fi
  fi
  if [ "$seed_stat" = 1 ]; then
    seed_born="$(bounded start-seed-cost stat -c %W "$seed_dir" 2>/dev/null || true)"; seed_done="$(bounded start-seed-cost stat -c %Y "$seed_marker" 2>/dev/null || true)"
    if [[ "$seed_born" =~ ^[0-9]+$ ]] && [ "$seed_born" -gt 0 ] && [[ "$seed_done" =~ ^[0-9]+$ ]] && [ "$seed_done" -ge "$seed_born" ]; then
      seed_seconds=$(( seed_done - seed_born ))
    else
      echo "  ${seed_dir}: birth time unavailable (stat %W='${seed_born:-}', marker mtime '${seed_done:-}'): livespec.ci_seed.seconds omitted"
    fi
  fi
else
  echo "  no seeded work volume visible under ${STORAGE_ROOT} (idle pool, or the seed is not running): start-seed-cost and livespec.ci_seed.* omitted"
fi
seed_bytes_budget="${SEED_BYTES_BUDGET:-$warm_budget_bytes}"
seed_hits=0
if [ -n "$seed_bytes" ] && [ -n "$seed_bytes_budget" ] && [ "$seed_bytes" -gt "$seed_bytes_budget" ]; then
  seed_hits=$((seed_hits+1)); add_detail "    volume=${seed_vol} seed bytes=${seed_bytes} OVER budget ${seed_bytes_budget} (generation ${seed_gen:-unknown})"
fi
if [ -n "$seed_seconds" ] && [ "$seed_seconds" -gt "$SEED_SECONDS_BUDGET" ]; then
  seed_hits=$((seed_hits+1)); add_detail "    volume=${seed_vol} seed took ${seed_seconds}s, OVER ${SEED_SECONDS_BUDGET}s (generation ${seed_gen:-unknown})"
fi
if [ -n "$seed_vol" ]; then
  echo "  volume=${seed_vol} generation=${seed_gen:-unknown}$( [ -n "$warm_live_gen" ] && [ "$seed_gen" != "$warm_live_gen" ] && printf ' (live is %s)' "$warm_live_gen") seed bytes=${seed_bytes:-unknown} (budget ${seed_bytes_budget:-unknown}) seconds=${seed_seconds:-unknown} (budget ${SEED_SECONDS_BUDGET})"
fi
if [ -z "$seed_bytes" ] || [ -z "$seed_seconds" ] || [ -z "$seed_bytes_budget" ]; then
  omit_zero start-seed-cost
  [ "$seed_hits" -gt 0 ] || [ -z "$seed_vol" ] || echo "  start-seed-cost judged on partial inputs and found nothing: its zero is withheld from the gauges"
fi
[ "$seed_hits" -gt 0 ] && add_finding start-seed-cost "$seed_hits"

# ---------------------------------------------------------------------------
log "10. api-unavailable: ${K3S_UNIT} (re)started in the last ${WINDOW}; API reads refused during this sweep"
# Restart detection is the unit's OWN main-process start, read as a
# MONOTONIC clock against /proc/uptime so no time zone is parsed and no
# state file is kept: ExecMainStartTimestampMonotonic is microseconds since
# boot at the moment systemd forked the current k3s main process, and it
# moves on EVERY start — a crash-and-auto-restart and a hand `systemctl
# restart k3s` alike. (The first cut counted the journal's `Main process
# exited` lines, which systemd logs only for a FAILING exit, and a NRestarts
# delta, which a hand restart resets to 0 — so the acceptance move read 0.)
# Verified on the host 2026-09-06 09:49Z, verbatim: `ExecMainStartTimestamp=
# Sat 2026-09-05 23:07:09 PDT`, `ExecMainStartTimestampMonotonic=
# 14726505650`, `NRestarts=1`. A start younger than the window is ONE
# restart (the property carries only the latest start; two in one window
# count once). A boot is a start too: the first sweep after it reports the
# API as having been away, which it was. Refused reads are what kc recorded
# for steps 1-9; the emitter's own reads come after this step and show only
# in its emit lines.
api_restarts=0; api_started_ago=""
if mono="$(bounded api-unavailable systemctl show -p ExecMainStartTimestampMonotonic --value "$K3S_UNIT" 2>/dev/null)" \
   && [[ "$mono" =~ ^[0-9]+$ ]] && [ "$mono" -gt 0 ] && read -r uptime _ < /proc/uptime; then
  api_started_ago=$(( ${uptime%.*} - mono / 1000000 ))
  if [ "$api_started_ago" -ge 0 ] && [ "$api_started_ago" -le "$WINDOW_SECONDS" ]; then
    api_restarts=1; add_detail "    ${K3S_UNIT} main process started ${api_started_ago}s ago, inside the ${WINDOW} window (ExecMainStartTimestampMonotonic vs /proc/uptime): the API was gone across that start, and a job starting then fails on connect ECONNREFUSED"
  fi
else
  echo "  systemctl show -p ExecMainStartTimestampMonotonic ${K3S_UNIT} unreadable: restarts unknown this sweep; api-unavailable's zero withheld"
  omit_zero api-unavailable
fi
api_refused=0
while IFS=' ' read -r step rest; do
  [ -n "$step" ] || continue
  api_refused=$((api_refused+1)); add_detail "    API read REFUSED at step ${step}: ${rest}"
done < "$API_REFUSED_FILE"
echo "  ${api_restarts} (re)start(s) of ${K3S_UNIT} inside the window (main process started ${api_started_ago:-unknown}s ago); ${api_refused} API read(s) refused during this sweep (steps 1-9)"
api_hits=$(( api_restarts + api_refused ))
[ "$api_hits" -gt 0 ] && add_finding api-unavailable "$api_hits"

# ---------------------------------------------------------------------------
# OTLP EMISSION — every sweep's readings, posted as gauges (livespec-vwzv).
#
# WHY. Until 2026-09-04 the class counts above, Kueue's pending/admitted
# workload counts and the node's churn-slot allocatable-versus-quota lived in
# this unit's journal only. The maintainer's 2026-09-04 directive is that the
# churn-slot cap C (kueue/DERIVATION.md calls it "a measured ceiling, not a
# free parameter") and the CI routing are re-derived from MEASURED Honeycomb
# data, so every signal that derivation needs is captured beside the disk
# rows and the k8s pod phases the host collector already exports. THE NAMED
# READER (naming one up front is the lesson of the heartbeat's eight silent
# days, ../../../observability/ci-runner-heartbeat.sh): the retrospective
# query recipe in ../README.md "What every sweep emits to Honeycomb", which
# lines these gauges up against concurrent workflow pods and the array's
# queue time per operation. Decision inputs, like the heartbeat's io_stall
# pair — no trigger pairs with them.
#
# WHAT. ONE OTLP/HTTP metrics POST to the host otel-collector's loopback
# receiver — the heartbeat's endpoint, JSON shape and curl flags; the
# collector exports to the `livespec` env's `metrics` dataset — with resource
# service.name=ci-runner-lifecycle + host.name, scope runner-pod-lifecycle:
#   livespec.ci_lifecycle.<class>       the count the report carries for the
#                                       class — EVERY class, ALWAYS, 0 when
#                                       clean: an absent metric is
#                                       indistinguishable from a broken
#                                       emitter.
#   livespec.ci_kueue.pending           ClusterQueue status.pendingWorkloads
#   livespec.ci_kueue.admitted          and status.admittedWorkloads, summed
#                                       over every ClusterQueue that covers
#                                       ci-runner.io/churn-slot (the pool;
#                                       phase1-proof-cq covers cpu/memory
#                                       only and is excluded). One list
#                                       call, which also yields
#   livespec.ci_churn_slot.quota_sum    the sum of those queues' nominalQuota
#                                       for ci-runner.io/churn-slot; and
#   livespec.ci_churn_slot.allocatable  allocatable ci-runner.io/churn-slot
#                                       summed over the nodes — 0 when the
#                                       extended resource is not registered,
#                                       which IS a reading (capacity absent).
#   livespec.ci_warm.*                  the warm-cache populator's last run,
#                                       once per new run_id, from its
#                                       last-run.json (the block below).
#   livespec.ci_lifecycle.pvc-gated     Pending claims of scheduling-gated
#                                       pods that step 1 excluded — not a
#                                       class, a reading of Kueue's queue
#                                       depth as the provisioner sees it.
#                                       Omitted when the gates read failed.
#   livespec.ci_lifecycle.sweep_seconds this sweep's wall clock at the POST,
#                                       every sweep: the trend that reaches
#                                       the unit's deadline before the
#                                       deadline does (2026-09-06: 8-11 min
#                                       against a 5-minute timer).
#   livespec.ci_warm.live_generation_bytes / _files / _age_s
#                                       the LIVE generation, EVERY sweep (the
#                                       ci_warm.generation_* pair above is
#                                       once per run and describes the run's
#                                       candidate): size from its manifest,
#                                       age since its publish stamp. Each
#                                       omitted when step 8 could not read it.
#   livespec.ci_seed.bytes / .seconds   step 9's newest seeded volume: what
#                                       one job start paid. Omitted when no
#                                       seeded volume is visible, or when the
#                                       du or the birth time was unreadable.
#
# BEST-EFFORT, BY CONTRACT. The report and the exit code are the interface
# the journal and `systemctl is-failed` depend on; a collector outage must not
# turn a clean node into a failed unit or mask a stall. A curl failure is
# logged and absorbed, and the call site is guarded so that even a bug in
# this block cannot change the exit code. One fail-closed split is kept: the
# class gauges come from variables this sweep already computed and are always
# sent; the Kueue and node gauges need two extra reads, and when a read FAILS
# those gauges are OMITTED (and the failure logged) rather than sent as false
# zeros — the heartbeat's split between "0" and "could not read".
#
# ADDING A CLASS: append its name to EMIT_CLASSES so its zero is emitted on a
# clean sweep. A class present in FINDINGS but missing from the list is still
# emitted — only its zero would be lost. TWO EXCEPTIONS to "always", both
# fail-closed: a class whose read hit its step deadline (DEADLINE_FILE) or
# whose judgement lacked an input (OMIT_ZERO_CLASSES) has its ZERO withheld,
# because that zero would mean "looked and found nothing" when the sweep did
# not look; a non-zero count from a partial read is still a true reading.
EMIT_CLASSES="pvc-pending bind-deadline inotify-emfile containerd-deadline hook-failure stale-listener capacity-absent warm-cache-oversize start-seed-cost api-unavailable"

# WARM-CACHE BUILD GAUGES (livespec-41w4; ../warm-cache/README.md "Metrics").
# The warm-cache populator runs in a pod with no hostNetwork and the collector
# listens on loopback only, so it cannot post its own readings; it writes
# $WARM_LAST_RUN (one document per run — rebuilt, refused, verified, sizes,
# trim against the previous generation, proxy hit ratio) and THIS sweep, the
# host-side emitter that already exists, carries them ONCE per new run_id in
# the same POST as the lifecycle gauges:
#   livespec.ci_warm.generation_bytes / .generation_files   the live generation
#   livespec.ci_warm.trimmed_bytes / .trimmed_files         previous minus new
#                                                           on a rebuild (0 on
#                                                           a verified-unchanged
#                                                           run; negative = grew)
#   livespec.ci_warm.populate_seconds                       the uv build phase
#   livespec.ci_warm.repos_synced / .repos_failed
#   livespec.ci_warm.rebuilt / .refused / .verified         0|1 for the run
#   livespec.ci_warm.unreferenced_entries                   the verifier's count
#   livespec.ci_warm.budget_bytes / .budget_files           the budget in effect
#   livespec.ci_warm.proxied_downloads                      distributions fetched
#                                                           through the proxy
#   livespec.ci_warm.proxy_hit_ratio                        when the populator
#                                                           could derive it
#   livespec.ci_warm.run_epoch                              the run's start, the
#                                                           join key back to the
#                                                           Job log
# FAIL-CLOSED, like the Kueue and node gauges: an absent or unparseable
# last-run.json omits the whole family (and says so) rather than sending
# zeros; a run_id already recorded in $WARM_STATE_FILE is not re-sent (the
# populator runs every 30 min, the sweep every 5); the state is written only
# after the POST succeeds, so a collector outage re-sends the run on the next
# sweep instead of losing it.
# Both set by warm_metrics_fragment (which therefore runs in the caller's
# shell, never in a command substitution): the JSON fragment to append to the
# POST, and the run it describes (empty when nothing is to be sent).
WARM_FRAG=""
warm_run_id=""
warm_unit() {
  case "$1" in
    *_bytes) printf 'By' ;;
    *_files|*_entries|proxied_downloads) printf '{files}' ;;
    populate_seconds|run_epoch) printf 's' ;;
    repos_*) printf '{repos}' ;;
    *) printf '1' ;;
  esac
}
warm_metrics_fragment() {
  local rows now_ns="$1" key val frag="" ratio="" last_emitted
  WARM_FRAG=""; warm_run_id=""
  if [ ! -r "$WARM_LAST_RUN" ]; then
    echo "  emit: ${WARM_LAST_RUN} absent or unreadable (no populate since the rebuild, or not root); omitting livespec.ci_warm.* rather than sending false zeros" >&2
    return 0
  fi
  if ! rows="$(python3 - "$WARM_LAST_RUN" <<'PY' 2>&1
import json, sys
d = json.load(open(sys.argv[1]))
print("run_id=" + str(d["run_id"]))
print("run_epoch=" + str(int(d["started_at_epoch"])))
for k in ("generation_bytes", "generation_files", "trimmed_bytes", "trimmed_files", "populate_seconds",
          "repos_synced", "repos_failed", "rebuilt", "refused", "verified", "unreferenced_entries",
          "budget_bytes", "budget_files", "proxied_downloads"):
    if d.get(k) is not None:
        print(f"{k}={int(d[k])}")
if d.get("proxy_hit_ratio") is not None:
    print(f"proxy_hit_ratio={float(d['proxy_hit_ratio'])}")
PY
)"; then
    echo "  emit: ${WARM_LAST_RUN} unparseable ($(printf '%s' "$rows" | tail -1)); omitting livespec.ci_warm.*" >&2
    return 0
  fi
  warm_run_id="$(printf '%s\n' "$rows" | sed -n 's/^run_id=//p')"
  last_emitted="$(cat "$WARM_STATE_FILE" 2>/dev/null || true)"
  if [ -n "$warm_run_id" ] && [ "$warm_run_id" = "$last_emitted" ]; then
    echo "  emit: warm-cache run ${warm_run_id} already emitted; livespec.ci_warm.* not re-sent"
    warm_run_id=""
    return 0
  fi
  while IFS='=' read -r key val; do
    case "$key" in
      run_id|'') ;;
      proxy_hit_ratio) ratio="$val" ;;
      *) frag="${frag},$(gauge_json "livespec.ci_warm.${key}" "warm-cache populate run ${warm_run_id}: ${key} (from last-run.json)" "$(warm_unit "$key")" "$val" "$now_ns")" ;;
    esac
  done <<< "$rows"
  if [ -n "$ratio" ]; then
    frag="${frag},$(gauge_double_json livespec.ci_warm.proxy_hit_ratio "warm-cache populate run ${warm_run_id}: share of proxied distribution downloads served from the PyPI files proxy's store" "1" "$ratio" "$now_ns")"
  fi
  WARM_FRAG="$frag"
}
record_warm_run() {
  [ -n "$warm_run_id" ] || return 0
  mkdir -p "$(dirname "$WARM_STATE_FILE")" 2>/dev/null || return 0
  printf '%s\n' "$warm_run_id" > "$WARM_STATE_FILE" 2>/dev/null || return 0
}

# gauge_json / gauge_double_json / otlp_post are defined beside kc above
# (the refused-/readyz path needs them before this block).
# The count the report carries for class $1; 0 when the class is absent.
class_count() {
  local t
  for t in $FINDINGS; do case "$t" in "$1="*) printf '%s' "${t#*=}"; return 0 ;; esac; done
  printf '0'
}

emit_lifecycle_metrics() {
  local now_ns host_name tok c n classes metrics summary err
  local cq_rows node_rows name quotas p a q alloc pending admitted quota_sum allocatable
  if [ "$NO_EMIT" != 0 ]; then
    echo "  emit: disabled (--no-emit / RPL_NO_EMIT=1); nothing posted"
    return 0
  fi
  command -v curl >/dev/null || { echo "  emit: curl not found on PATH; nothing posted (best-effort; the report and exit code are unaffected)" >&2; return 0; }
  now_ns="$(date +%s%N)"
  host_name="$(hostname)"

  classes="$EMIT_CLASSES"
  for tok in $FINDINGS; do
    c="${tok%%=*}"
    case " $classes " in *" $c "*) ;; *) classes="$classes $c" ;; esac
  done
  metrics=""; summary=""
  for c in $classes; do
    n="$(class_count "$c")"
    if [ "$n" -eq 0 ]; then
      case "$OMIT_ZERO_CLASSES" in *" $c "*)
        echo "  emit: livespec.ci_lifecycle.${c} omitted — an input its judgement needs was unreadable this sweep (a zero would be false)" >&2; continue ;;
      esac
      if class_read_hit "$c"; then
        echo "  emit: livespec.ci_lifecycle.${c} omitted — its read hit the step deadline (a zero would be false)" >&2; continue
      fi
    fi
    metrics="${metrics},$(gauge_json "livespec.ci_lifecycle.${c}" "runner-pod lifecycle sweep: count reported for class ${c} (0 = clean)" "{findings}" "$n" "$now_ns")"
    summary="${summary} livespec.ci_lifecycle.${c}=${n}"
  done
  if [ "$pods_read" = 1 ] && [ "$pvc_read" = 1 ] && ! class_read_hit pvc-pending; then
    metrics="${metrics},$(gauge_json livespec.ci_lifecycle.pvc-gated "Pending PVCs whose consumer pod carries spec.schedulingGates (Kueue holding it), excluded from pvc-pending" "{pvcs}" "$pvc_gated" "$now_ns")"
    summary="${summary} livespec.ci_lifecycle.pvc-gated=${pvc_gated}"
  fi
  if [ -n "$warm_live_bytes" ]; then
    metrics="${metrics},$(gauge_json livespec.ci_warm.live_generation_bytes "The live warm uv cache generation's size, from its manifest (every sweep; generation ${warm_live_gen})" "By" "$warm_live_bytes" "$now_ns")"
    metrics="${metrics},$(gauge_json livespec.ci_warm.live_generation_files "The live warm uv cache generation's regular-file count, from its manifest (every sweep)" "{files}" "$warm_live_files" "$now_ns")"
    summary="${summary} livespec.ci_warm.live_generation_bytes=${warm_live_bytes} livespec.ci_warm.live_generation_files=${warm_live_files}"
  fi
  if [ -n "$warm_live_age" ]; then
    metrics="${metrics},$(gauge_json livespec.ci_warm.live_generation_age_s "Seconds since the live warm uv cache generation was published (its stamp), every sweep" "s" "$warm_live_age" "$now_ns")"
    summary="${summary} livespec.ci_warm.live_generation_age_s=${warm_live_age}"
  fi
  if [ -n "$seed_bytes" ]; then
    metrics="${metrics},$(gauge_json livespec.ci_seed.bytes "du -sb of _warm/uv on the newest seeded work volume: what one job start's warm seed holds (volume ${seed_vol})" "By" "$seed_bytes" "$now_ns")"
    summary="${summary} livespec.ci_seed.bytes=${seed_bytes}"
  fi
  if [ -n "$seed_seconds" ]; then
    metrics="${metrics},$(gauge_json livespec.ci_seed.seconds "Seconds the warm seed took on the newest seeded work volume: _warm birth to the .uv-generation marker (volume ${seed_vol})" "s" "$seed_seconds" "$now_ns")"
    summary="${summary} livespec.ci_seed.seconds=${seed_seconds}"
  fi

  if cq_rows="$(kc emit get clusterqueues -o jsonpath='{range .items[*]}{.metadata.name}|{range .spec.resourceGroups[*]}{range .flavors[*]}{range .resources[*]}{.name}={.nominalQuota} {end}{end}{end}|{.status.pendingWorkloads}|{.status.admittedWorkloads}{"\n"}{end}' 2>&1)"; then
    pending=0; admitted=0; quota_sum=0
    while IFS='|' read -r name quotas p a; do
      [ -n "$name" ] || continue
      q=""
      for tok in $quotas; do case "$tok" in "ci-runner.io/churn-slot="*) q="${tok#*=}" ;; esac; done
      [ -n "$q" ] || continue
      [[ "$q" =~ ^[0-9]+$ ]] && quota_sum=$((quota_sum + q))
      [[ "$p" =~ ^[0-9]+$ ]] && pending=$((pending + p))
      [[ "$a" =~ ^[0-9]+$ ]] && admitted=$((admitted + a))
    done <<< "$cq_rows"
    metrics="${metrics},$(gauge_json livespec.ci_kueue.pending "Kueue workloads pending admission, summed over the ClusterQueues covering ci-runner.io/churn-slot" "{workloads}" "$pending" "$now_ns")"
    metrics="${metrics},$(gauge_json livespec.ci_kueue.admitted "Kueue workloads admitted and not yet finished, summed over the ClusterQueues covering ci-runner.io/churn-slot" "{workloads}" "$admitted" "$now_ns")"
    metrics="${metrics},$(gauge_json livespec.ci_churn_slot.quota_sum "Sum of nominalQuota for ci-runner.io/churn-slot across ClusterQueues" "{slots}" "$quota_sum" "$now_ns")"
    summary="${summary} livespec.ci_kueue.pending=${pending} livespec.ci_kueue.admitted=${admitted} livespec.ci_churn_slot.quota_sum=${quota_sum}"
  else
    echo "  emit: could not read ClusterQueues ($(printf '%s' "$cq_rows" | head -1)); omitting livespec.ci_kueue.* and livespec.ci_churn_slot.quota_sum rather than sending false zeros" >&2
  fi

  if node_rows="$(kc emit get nodes -o jsonpath='{range .items[*]}{.metadata.name}|{.status.allocatable.ci-runner\.io/churn-slot}{"\n"}{end}' 2>&1)"; then
    allocatable=0
    while IFS='|' read -r name alloc; do
      [ -n "$name" ] || continue
      [[ "$alloc" =~ ^[0-9]+$ ]] && allocatable=$((allocatable + alloc))
    done <<< "$node_rows"
    metrics="${metrics},$(gauge_json livespec.ci_churn_slot.allocatable "Allocatable ci-runner.io/churn-slot summed over the cluster's nodes (0 = extended resource not registered)" "{slots}" "$allocatable" "$now_ns")"
    summary="${summary} livespec.ci_churn_slot.allocatable=${allocatable}"
  else
    echo "  emit: could not read nodes ($(printf '%s' "$node_rows" | head -1)); omitting livespec.ci_churn_slot.allocatable rather than sending a false zero" >&2
  fi

  warm_metrics_fragment "$now_ns"
  if [ -n "$WARM_FRAG" ]; then
    metrics="${metrics}${WARM_FRAG}"
    summary="${summary} livespec.ci_warm.*(run ${warm_run_id})"
  fi

  # The sweep's wall clock, last, so it covers the emitter's own reads.
  sweep_ms=$(( ($(date +%s%N) - SWEEP_START_NS) / 1000000 ))
  metrics="${metrics},$(gauge_double_json livespec.ci_lifecycle.sweep_seconds "This sweep's wall clock from start to the emit POST (the unit deadline is TimeoutStartSec; the timer is 5 min)" "s" "$(( sweep_ms / 1000 )).$(printf '%03d' $(( sweep_ms % 1000 )))" "$now_ns")"
  summary="${summary} livespec.ci_lifecycle.sweep_seconds=$(( sweep_ms / 1000 )).$(printf '%03d' $(( sweep_ms % 1000 )))"

  if err="$(otlp_post "${metrics#,}")"; then
    echo "  emit:${summary} host.name=${host_name} -> ${OTLP_ENDPOINT}"
    record_warm_run
  else
    echo "  emit: POST to ${OTLP_ENDPOINT} FAILED (${err:-no detail}); best-effort — the report and exit code are unaffected. Not posted:${summary}" >&2
  fi
  return 0
}

log "emit: end-of-sweep gauges to the host collector"
# `|| true` is the contract, not belt-and-braces: it also switches errexit off
# inside the function, so a failing read in there cannot abort the sweep.
emit_lifecycle_metrics || true

# ---------------------------------------------------------------------------
# A CLASS read that hit its deadline or was skipped makes a clean sweep a
# PARTIAL one: exit 2 (could not read), streak untouched, never CLEAN. With
# findings the stall exit stands and the partial reads are named beside them.
# The emitter's own reads and the prechecks are listed for the operator but
# never decide the exit code (header "BEST-EFFORT, BY CONTRACT").
DEADLINE_HITS="$(deadline_hits classes)"
DEADLINE_HITS_ALL="$(deadline_hits)"
if [ -z "$FINDINGS" ]; then
  if [ -n "$DEADLINE_HITS" ]; then
    log "INCOMPLETE after $(sweep_elapsed_s)s. No class found, but these class reads did not complete: ${DEADLINE_HITS}. Not a clean reading (exit 2); the node is under load or the API is slow — see the sweep_seconds gauge."
    exit 2
  fi
  write_streak 0
  log "CLEAN after $(sweep_elapsed_s)s. No runner-pod lifecycle stall class present on this node.${DEADLINE_HITS_ALL:+ (non-class reads that did not complete: ${DEADLINE_HITS_ALL})}"
  exit 0
fi

STREAK=$(( $(read_streak) + 1 ))
write_streak "$STREAK"

log "RUNNER-POD LIFECYCLE STALL after $(sweep_elapsed_s)s: ${FINDINGS}(consecutive sweeps with findings: ${STREAK})"
printf '%s' "$DETAIL"
[ -n "$DEADLINE_HITS_ALL" ] && printf '\nPARTIAL: these reads did not complete, so their classes (or gauges) may be under-counted: %s\n' "$DEADLINE_HITS_ALL"

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
it within ~30 s; converge-side fix livespec-bde2); capacity-absent =
`systemctl start reapply-node-extended-resource.service` (the converge asserts
it on every run and the reapply timer re-tries every 5 min; livespec-kgl3);
warm-cache-oversize = the warm uv generation or its populator (warm-cache/:
over budget means the refusal gate let it through or the budget moved —
`kubectl -n ci-warm-cache get configmap warm-cache-budget -o yaml`; stalled
means the CronJob is not running — `kubectl -n ci-warm-cache get cronjob,jobs`;
livespec-44qx); start-seed-cost = the seed the provisioner's setup script
makes per volume (local-path-provisioner/): too big means the generation
grew, too slow means the volume tier is slow or the file count climbed
(research/005-006; livespec-44qx); api-unavailable = k3s itself went away
(`journalctl -u k3s -p err --since -1h` for the crash — 2026-09-06 it was a
flannel vxlan nil-pointer panic; every job that started in the boot window
failed on connect ECONNREFUSED and is re-run on the SAME commit).
A job that failed with the ARC hook's "custom container implementation
failed" is re-run on the SAME commit once the class has cleared — it is not a
test failure.
EOF
exit 1
