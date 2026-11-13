#!/usr/bin/env bash
# departure-drill.sh <host> --confirm-depart <host>-homelab-worker
#   [--mode power-loss|network-loss] [--hold-seconds N] [--state-root <dir>]
# — make <host>'s homelab worker leave the cluster without warning, hold it
# away for a bounded time, bring it back with one command, and print what the
# cluster the caller's `kubectl` reaches did with the work that was on it. Run
# it on the worker's macOS host, from a clone of this repository, with the
# same kubectl and limactl as join-worker.sh, while the node carries live load.
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes", "Departure and rejoin": work on a worker that leaves without warning
# must not be lost, and the worker must rejoin and re-enroll with no operator
# step. This script is the measured departure; it reports, and judges only the
# rejoin.
#
#   1. The host, the mode (default power-loss) and the hold (default 600
#      seconds; an integer from 60 to 3600) are validated. THE FENCE:
#      `--confirm-depart` must name the worker's Node, <host>-homelab-worker,
#      exactly. Without it, or with another name, nothing is read and nothing
#      is changed. It is the same rule the window routes follow: a disruption
#      acts only on the node an explicit confirmation names.
#   2. Reads first; nothing is changed until all pass. The Node
#      <host>-homelab-worker must exist, be Ready and not be cordoned (a drill
#      on a cordoned node measures nothing), and the VM must answer through
#      limactl. The BEFORE record is printed: the node's uid, taints,
#      enrollment labels (k3s-role, ci-runner.io/factory,
#      homelab-worker.livespec.dev/gate-share-millicores) and
#      ci-runner.io/churn-slot allocatable, the collector's endpoint, every
#      pod on the node (phase, owner, restart count), and the Jobs that own
#      those pods.
#   3. Departure, with no cordon and no drain.
#        power-loss    `limactl stop --force <worker>`: the VM, the worker
#                      container, the kubelet and every pod process die at
#                      once, as when the host loses power.
#        network-loss  `ip link set dev lima0 down` inside the VM: the node
#                      loses its home-LAN address, which is its node IP and
#                      its pod-network underlay. The kubelet and the pods keep
#                      running. It does NOT simulate a host with no network
#                      at all: Lima's own user-mode interface stays up (this
#                      script needs it to bring lima0 back), so the kubelet
#                      may still reach the API server through the host and
#                      the Node may stay Ready. The tailnet path stays too.
#   4. Hold: the Node's Ready condition is polled every POLL_SECONDS (default
#      15) and the moment it leaves True is printed. Nothing is evicted,
#      deleted or cordoned.
#   5. Read-back at the end of the hold. For every pod captured in step 2:
#      where it is now, and whether its owner has a new pod on another node (a
#      pod that did not exist before the departure). Each is classified as one
#      of
#        finished-before-departure        Succeeded at capture, or reported
#                                         Succeeded before the node went quiet
#        replaced-elsewhere               its owner has a new pod on another node
#        still-bound-to-the-departed-node still there, not finished
#        failed                           Failed, at capture or now
#        gone                             deleted, and no replacement seen
#      and every captured Job's succeeded, failed and active counts are
#      printed beside their BEFORE values. The classes are evidence, not a
#      verdict. A replacement is found through the pod's own owner only: a
#      runner whose owner object is itself replaced under a new name shows as
#      `gone` here and is found in its runner set.
#   6. Return, with one command and nothing else: `limactl start` in
#      power-loss mode, `ip link set dev lima0 up` in network-loss mode. No
#      start task, no join, no converge: "no operator step" is the claim
#      under test.
#      IN NETWORK-LOSS MODE THE RETURN RESTORES ONLY THE CONNECTED ROUTE.
#      Taking lima0 down removes every route over it; bringing it up puts
#      back the address's own connected route and nothing else. A route
#      another agent installed over lima0 returns only when that agent
#      re-syncs, and if it does not, a converge (the start task) may have to
#      follow. The drill does not run one: whether the worker needs it is
#      part of what the read-back shows.
#   7. The Node is awaited Ready for up to WAIT_SECONDS (default 600), then
#      read back against BEFORE: uid, Ready, taints, enrollment labels and
#      churn-slot allocatable, whether the worker container runs, and the
#      collector — the OTLP_PODS_ENDPOINT in <state-root>/telemetry/node.env
#      (default state root /mnt/lima-hwdata/worker) against the container's
#      current cni0 address, and whether anything listens there.
#      The work is then read a SECOND time, after the rejoin: every captured
#      pod (where it is now, and its replacement if one exists) and every
#      captured Job with its backoffLimit. A Job with backoffLimit 0 that
#      reports a failed pod does not retry: a gate Job is such a Job, so its
#      gate is lost and its client reads the failure. A pod captured in a
#      factory namespace gets FACTORY lines. This script cannot read a
#      factory run's own state (it lives in the factory server, not in the
#      cluster), so it names the sandbox pod and says where to read it.
#   8. Exit 0 only if the control plane saw the node leave, the node came back
#      Ready within the bound with the uid, taints, enrollment labels and
#      churn-slot value it had BEFORE, and the collector listens on the
#      node's current cni0 address. Every difference is named. Collector
#      findings are on their own lines, prefixed COLLECTOR: the join path has
#      this gap open (livespec-dev-tooling-qotekb), and the drill shows
#      whether a plain restart has it too.
#      WHAT THIS DRILL DOES NOT PROVE. A VM stop and start does not log the
#      macOS user out, so it does not exercise the collector ingest key's
#      dependence on a login Keychain unlock. That clause is proved only on
#      a real host return (a reboot or a fresh login session), and must not
#      be claimed from this drill.
#   9. Once the departure has begun, an interrupt or a failed step still
#      attempts the return step, and says so. A kill that no trap can catch
#      leaves the worker away; the return is then by hand, `limactl start
#      <worker>` or `limactl shell <worker> sudo ip link set dev lima0 up`.
set -euo pipefail

prog="departure-drill"
hw="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$hw/hosts}"
poll="${POLL_SECONDS:-15}"
wait_seconds="${WAIT_SECONDS:-600}"
# The VM's bridged home-LAN interface (start-homelab-worker-node-container.sh
# sets the declared address on it through vm/converge-lan-address.sh).
lan_iface="lima0"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

say() {
  printf '%s: %s\n' "$prog" "$*"
}

# say_lines <text>: each non-empty line of <text>, indented under the prefix.
say_lines() {
  [ -z "$1" ] || printf '%s\n' "$1" | sed "s/^/$prog:   /"
}

usage="usage: $prog <host> --confirm-depart <host>-homelab-worker [--mode power-loss|network-loss] [--hold-seconds N] [--state-root <dir>]"
[ "$#" -ge 1 ] || die "$usage"
host="$1"
shift
mode="power-loss"
hold="600"
state_root="/mnt/lima-hwdata/worker"
confirm=""
while [ "$#" -gt 0 ]; do
  [ "$#" -ge 2 ] || die "$1 needs a value; $usage"
  case "$1" in
    --mode) mode="$2" ;;
    --hold-seconds) hold="$2" ;;
    --state-root) state_root="$2" ;;
    --confirm-depart) confirm="$2" ;;
    *) die "unknown argument '$1'; $usage" ;;
  esac
  shift 2
done
case "$host" in
  *[!a-z0-9-]* | -*) die "host '$host' is not a valid host name" ;;
esac
[ -f "$hosts_dir/$host.env" ] || die "host '$host' is not declared in homelab-worker/hosts/"
case "$mode" in
  power-loss | network-loss) ;;
  *) die "mode '$mode' is not power-loss or network-loss" ;;
esac
case "$hold" in
  "" | *[!0-9]* | 0*) die "hold '$hold' is not a whole number of seconds from 60 to 3600" ;;
esac
if [ "${#hold}" -gt 4 ] || [ "$hold" -lt 60 ] || [ "$hold" -gt 3600 ]; then
  die "hold '$hold' is outside 60 to 3600 seconds: under 60 the control plane has not yet marked the node lost, over 3600 is not a bounded drill"
fi
case "$poll" in
  "" | *[!0-9]* | 0*) die "POLL_SECONDS '$poll' is not a positive whole number" ;;
esac
case "$wait_seconds" in
  "" | *[!0-9]* | 0*) die "WAIT_SECONDS '$wait_seconds' is not a positive whole number" ;;
esac
case "$state_root" in
  /?*) ;;
  *) die "state root '$state_root' is not an absolute directory path" ;;
esac
state_root="${state_root%/}"
worker="$host-homelab-worker"
# The fence. It is checked before the first read, so an unconfirmed run does
# not even contact the cluster or the VM.
[ "$confirm" = "$worker" ] ||
  die "this drill takes $worker out of the cluster; it needs --confirm-depart $worker (got '${confirm:-nothing}'). Nothing was read and nothing was changed"
# A pod in one of these namespaces is a factory sandbox holding a run.
factory_namespaces=" factory factory-mi-homelab "

in_vm() {
  limactl shell --workdir / "$worker" sudo "$@"
}

# --- reads ---------------------------------------------------------------------
# A bare `$(kubectl ...)` under set -e exits silently when kubectl fails, so
# every caller checks its read. kubectl here can be ssh underneath
# (remote-kubectl.sh), which would swallow a loop's input: stdin is closed.

# read_node: name|uid|Ready|unschedulable|k3s-role|factory|gate-share|churn-slot|taints
# for the worker's Node, or nothing when it is absent.
read_node() {
  kubectl get node "$worker" --ignore-not-found \
    -o 'jsonpath={.metadata.name}|{.metadata.uid}|{.status.conditions[?(@.type=="Ready")].status}|{.spec.unschedulable}|{.metadata.labels.k3s-role}|{.metadata.labels.ci-runner\.io/factory}|{.metadata.labels.homelab-worker\.livespec\.dev/gate-share-millicores}|{.status.allocatable.ci-runner\.io/churn-slot}|{range .spec.taints[*]}{.key}={.value}:{.effect} {end}' </dev/null
}

# read_pods: one line per pod in the cluster,
# namespace|name|uid|phase|node|owner kinds|owner names|restart counts.
read_pods() {
  kubectl get pods --all-namespaces \
    -o 'jsonpath={range .items[*]}{.metadata.namespace}|{.metadata.name}|{.metadata.uid}|{.status.phase}|{.spec.nodeName}|{.metadata.ownerReferences[*].kind}|{.metadata.ownerReferences[*].name}|{.status.containerStatuses[*].restartCount}{"\n"}{end}' </dev/null
}

# read_job <namespace> <name>: uid|succeeded|failed|active|suspend|backoffLimit,
# or nothing when the Job is absent.
read_job() {
  kubectl get job "$2" -n "$1" --ignore-not-found \
    -o 'jsonpath={.metadata.uid}|{.status.succeeded}|{.status.failed}|{.status.active}|{.spec.suspend}|{.spec.backoffLimit}' </dev/null
}

# job_text <record>: a read_job record in words.
job_text() {
  local uid succeeded failed active suspend _
  [ -n "$1" ] || {
    printf 'gone'
    return
  }
  IFS='|' read -r uid succeeded failed active suspend _ <<<"$1"
  printf 'succeeded=%s failed=%s active=%s suspended=%s uid=%s' \
    "${succeeded:-0}" "${failed:-0}" "${active:-0}" "${suspend:-false}" "$uid"
}

# enrolled_taints <taints>: the taints that are the worker's own, sorted. The
# node lifecycle controller's node.kubernetes.io/* taints come and go with
# readiness and are not part of the enrollment.
enrolled_taints() {
  printf '%s\n' "$1" | tr ' ' '\n' | grep -v -e '^$' -e '^node\.kubernetes\.io/' | sort | tr '\n' ' ' || true
}

# read_collector: sets c_endpoint (node.env's OTLP_PODS_ENDPOINT), c_bridge
# (the worker container's cni0 address) and c_listening (true when a TCP
# listener is bound to c_endpoint in the container). Each is empty when its
# read finds nothing; the reads change nothing.
read_collector() {
  local text listeners
  text="$(in_vm cat "$state_root/telemetry/node.env" 2>/dev/null)" || text=""
  c_endpoint="$(printf '%s\n' "$text" | sed -n 's/^OTLP_PODS_ENDPOINT=//p' | sed -n 1p)"
  c_bridge="$(in_vm docker exec "$worker" ip -4 -o addr show dev cni0 2>/dev/null |
    awk '{print $4}' | cut -d / -f 1 | sed -n 1p)" || c_bridge=""
  c_listening=""
  if [ -n "$c_endpoint" ]; then
    listeners="$(in_vm docker exec "$worker" ss -Hltn 2>/dev/null)" || listeners=""
    c_listening="$(printf '%s\n' "$listeners" | awk -v ep="$c_endpoint" '$4 == ep { found = 1 } END { if (found) print "true" }')"
  fi
}

node="$(read_node)" ||
  die "could not read Node $worker through kubectl; the cluster was not reached, nothing was changed"
IFS='|' read -r b_name b_uid b_ready b_unschedulable b_role b_factory b_share b_slots b_taints <<<"$node"
[ "$b_name" = "$worker" ] ||
  die "Node $worker is not registered; there is no worker to drill. Nothing was changed"
[ "$b_ready" = True ] ||
  die "Node $worker is not Ready (its Ready condition is '${b_ready:-absent}'); a departure drill starts from a healthy node. Nothing was changed"
[ "$b_unschedulable" != true ] ||
  die "Node $worker is cordoned; a drill on a cordoned node measures nothing, because no new work is placed on it. Uncordon it and let it take load first. Nothing was changed"

pods_before="$(read_pods)" ||
  die "could not read the cluster's pods through kubectl; the cluster was not reached, nothing was changed"
# The pods on the node: namespace|name|uid|phase|owner kind|owner name|restarts.
captured="$(printf '%s\n' "$pods_before" | awk -F'|' -v worker="$worker" '
  NF >= 5 && $5 == worker {
    split($6, kind, " "); split($7, owner, " ")
    restarts = 0; n = split($8, count, " ")
    for (i = 1; i <= n; i++) restarts += count[i]
    printf "%s|%s|%s|%s|%s|%s|%d\n", $1, $2, $3, $4, kind[1], owner[1], restarts
  }')"
job_names="$(printf '%s\n' "$captured" | awk -F'|' '$5 == "Job" { print $1 " " $6 }' | sort -u)"
jobs_before=""
while IFS=' ' read -r job_ns job_name <&3; do
  [ -n "$job_name" ] || continue
  record="$(read_job "$job_ns" "$job_name")" ||
    die "could not read Job $job_ns/$job_name through kubectl; nothing was changed"
  jobs_before="$jobs_before$job_ns $job_name $record
"
done 3<<EOF
$job_names
EOF

in_vm true ||
  die "could not reach VM $worker through limactl; nothing was changed"
if [ "$mode" = network-loss ]; then
  in_vm ip link show dev "$lan_iface" >/dev/null 2>&1 ||
    die "VM $worker has no $lan_iface interface to take down; nothing was changed"
fi
read_collector
b_enrolled_taints="$(enrolled_taints "$b_taints")"

say "BEFORE Node $worker: uid=$b_uid Ready=$b_ready taints=[${b_taints% }]"
say "BEFORE enrollment: k3s-role=${b_role:-<none>} ci-runner.io/factory=${b_factory:-<none>} gate-share-millicores=${b_share:-<none>} churn-slot=${b_slots:-<none>}"
say "BEFORE collector: node.env endpoint=${c_endpoint:-<none>} cni0=${c_bridge:-<none>} listening=${c_listening:-false}"
say "BEFORE pods on the node: $(printf '%s' "$captured" | grep -c . || true)"
say_lines "$(printf '%s\n' "$captured" | awk -F'|' 'NF { printf "pod %s/%s phase=%s owner=%s restarts=%s\n", $1, $2, $4, ($5 == "" ? "<none>" : $5 "/" $6), $7 }')"
say "BEFORE Jobs that own them: $(printf '%s' "$jobs_before" | grep -c . || true)"
while IFS=' ' read -r job_ns job_name record <&3; do
  [ -n "$job_name" ] || continue
  say "  job $job_ns/$job_name $(job_text "$record")"
done 3<<EOF
$jobs_before
EOF

# classify_work <pods now> <rejoined: 0|1>: one line per pod captured on the
# node BEFORE, classed from the given later read of every pod in the cluster.
classify_work() {
  printf '%s\n--\n%s\n' "$pods_before" "$1" | awk -F'|' -v worker="$worker" -v rejoined="$2" '
  $0 == "--" { after = 1; next }
  NF < 5 { next }
  { split($6, kind, " "); split($7, owner, " ") }
  !after {
    existed[$3] = 1
    if ($5 == worker) {
      n++
      ns[n] = $1; name[n] = $2; uid[n] = $3; phase[n] = $4
      key[n] = (kind[1] == "" ? "" : $1 "|" kind[1] "|" owner[1])
    }
    next
  }
  {
    now_phase[$3] = $4; now_node[$3] = $5; present[$3] = 1
    k = $1 "|" kind[1] "|" owner[1]
    if (kind[1] != "" && !($3 in existed) && $5 != "" && $5 != worker && !(k in replacement))
      replacement[k] = $1 "/" $2 " on " $5 " (" $4 ")"
  }
  END {
    for (i = 1; i <= n; i++) {
      new_pod = (key[i] != "" && key[i] in replacement) ? replacement[key[i]] : ""
      if (uid[i] in present) now = "phase=" now_phase[uid[i]] " node=" now_node[uid[i]]
      else now = "pod gone"
      if (phase[i] == "Succeeded") class = "finished-before-departure"
      else if (phase[i] == "Failed") class = "failed"
      else if (new_pod != "") class = "replaced-elsewhere"
      else if (!(uid[i] in present)) class = "gone"
      else if (now_phase[uid[i]] == "Failed") class = "failed"
      else if (now_phase[uid[i]] == "Succeeded") class = "finished-before-departure"
      else class = "still-bound-to-the-departed-node"
      if (rejoined)
        printf "%s: pod %s/%s (%s at capture) is, after the rejoin, %s; replacement on another node: %s\n", \
          class, ns[i], name[i], phase[i], now, (new_pod == "" ? "none" : new_pod)
      else
        printf "%s: pod %s/%s was %s, now %s; replacement on another node: %s\n", \
          class, ns[i], name[i], phase[i], now, (new_pod == "" ? "none" : new_pod)
    }
  }'
}

factory_pods="$(printf '%s\n' "$captured" | awk -F'|' -v spaces="$factory_namespaces" '
  NF && index(spaces, " " $1 " ") { print $1 "/" $2 }')"
if [ -n "$factory_pods" ]; then
  say "FACTORY: the node carries factory sandbox pods; a forced stop kills them, and each one's run is read at the factory server, not here:"
  say_lines "$factory_pods"
fi

# --- departure -----------------------------------------------------------------
departed=0
return_attempted=0

return_worker() {
  return_attempted=1
  case "$mode" in
    power-loss) limactl start --tty=false "$worker" ;;
    network-loss) in_vm ip link set dev "$lan_iface" up ;;
  esac
}

# Whatever ends the run after the departure began, the worker is brought back.
on_exit() {
  status=$?
  trap - EXIT
  if [ "$departed" = 1 ] && [ "$return_attempted" = 0 ]; then
    say "the drill stopped after the departure and before the return step (exit $status); attempting the return step now" >&2
    if return_worker; then
      say "the return step ran; the rejoin was not read back, so this run proves nothing" >&2
    else
      say "THE RETURN STEP FAILED: VM $worker is still away; return it by hand (see step 9 of this script's header)" >&2
    fi
  fi
  exit "$status"
}
trap on_exit EXIT
trap 'exit 130' HUP INT TERM

departed=1
case "$mode" in
  power-loss)
    limactl stop --force "$worker" ||
      die "limactl stop --force $worker failed; the departure did not happen as intended"
    ;;
  network-loss)
    in_vm ip link set dev "$lan_iface" down ||
      die "could not take $lan_iface down in VM $worker; the departure did not happen as intended"
    ;;
esac
departed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "DEPARTED at $departed_at ($mode); no cordon, no drain. Holding ${hold}s"

# --- hold ----------------------------------------------------------------------
waited=0
left_ready=""
while [ "$waited" -lt "$hold" ]; do
  step="$poll"
  [ "$((hold - waited))" -ge "$step" ] || step="$((hold - waited))"
  sleep "$step"
  waited="$((waited + step))"
  [ -z "$left_ready" ] || continue
  if node="$(read_node)"; then
    IFS='|' read -r _ _ ready _ <<<"$node"
    if [ "$ready" != True ]; then
      left_ready="$waited"
      say "Node $worker's Ready condition left True (now '${ready:-absent}') within ${waited}s of the departure"
    fi
  else
    say "could not read Node $worker ${waited}s into the hold; the hold continues"
  fi
done
[ -n "$left_ready" ] ||
  say "Node $worker's Ready condition never left True in the ${hold}s hold: the control plane did not see a departure"

# --- read-back of the work -----------------------------------------------------
pods_after="$(read_pods)" ||
  die "could not read the cluster's pods at the end of the hold; the evidence was not captured"
say "AFTER ${hold}s away, the pods captured on the node:"
say_lines "$(classify_work "$pods_after" 0)"
say "AFTER ${hold}s away, the Jobs that owned them:"
while IFS=' ' read -r job_ns job_name record <&3; do
  [ -n "$job_name" ] || continue
  now="$(read_job "$job_ns" "$job_name")" ||
    die "could not read Job $job_ns/$job_name at the end of the hold; the evidence was not captured"
  say "  job $job_ns/$job_name was $(job_text "$record"); now $(job_text "$now")"
done 3<<EOF
$jobs_before
EOF

# --- return --------------------------------------------------------------------
case "$mode" in
  power-loss) say "RETURN: limactl start $worker, and nothing else" ;;
  network-loss) say "RETURN: $lan_iface up in VM $worker, and nothing else (only the connected route comes back with it; see step 6 of this script's header)" ;;
esac
return_worker ||
  die "the return step failed; VM $worker is still away, return it by hand (see step 9 of this script's header)"
returned_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# --- rejoin read-back ----------------------------------------------------------
waited=0
a_name="" a_uid="" a_ready="" a_unschedulable="" a_role="" a_factory="" a_share="" a_slots="" a_taints=""
while :; do
  if node="$(read_node)"; then
    IFS='|' read -r a_name a_uid a_ready a_unschedulable a_role a_factory a_share a_slots a_taints <<<"$node"
    [ "$a_name" != "$worker" ] || [ "$a_ready" != True ] || break
  fi
  [ "$waited" -lt "$wait_seconds" ] || break
  sleep "$poll"
  waited="$((waited + poll))"
done

differences=""
differ() {
  differences="$differences$1
"
}

[ -n "$left_ready" ] ||
  differ "the Node's Ready condition never left True during the hold, so no departure was measured and its Ready now is not a rejoin"
if [ "$a_name" != "$worker" ] || [ "$a_ready" != True ]; then
  say "AFTER return at $returned_at: Node $worker is not Ready ${waited}s later (registered: $([ "$a_name" = "$worker" ] && printf yes || printf no), Ready='${a_ready:-absent}')"
  differ "Node $worker did not return Ready within ${wait_seconds}s of the return step (Ready is '${a_ready:-absent}')"
  say "the enrollment and collector read-back was not taken"
else
  a_enrolled_taints="$(enrolled_taints "$a_taints")"
  say "AFTER return at $returned_at: Node $worker Ready again within ${waited}s: uid=$a_uid ($([ "$a_uid" = "$b_uid" ] && printf 'the same Node object' || printf 'CHANGED, was %s' "$b_uid")) taints=[${a_taints% }] cordoned=${a_unschedulable:-false}"
  say "AFTER enrollment: k3s-role=${a_role:-<none>} ci-runner.io/factory=${a_factory:-<none>} gate-share-millicores=${a_share:-<none>} churn-slot=${a_slots:-<none>}"
  [ "$a_uid" = "$b_uid" ] ||
    differ "node uid changed: was $b_uid, now $a_uid (the Node was registered anew)"
  [ "$a_role" = "$b_role" ] ||
    differ "label k3s-role: was '${b_role}', now '${a_role}'"
  [ "$a_factory" = "$b_factory" ] ||
    differ "label ci-runner.io/factory: was '${b_factory}', now '${a_factory}'"
  [ "$a_share" = "$b_share" ] ||
    differ "label homelab-worker.livespec.dev/gate-share-millicores: was '${b_share}', now '${a_share}'"
  [ "$a_slots" = "$b_slots" ] ||
    differ "ci-runner.io/churn-slot allocatable: was '${b_slots}', now '${a_slots}'"
  [ "$a_enrolled_taints" = "$b_enrolled_taints" ] ||
    differ "taints: were [${b_enrolled_taints% }], now [${a_enrolled_taints% }]"
  [ "$a_unschedulable" != true ] ||
    differ "the Node is now cordoned"

  # The work, read a second time now that the node is back.
  if pods_rejoined="$(read_pods)"; then
    say "AFTER the rejoin, the pods captured on the node:"
    say_lines "$(classify_work "$pods_rejoined" 1)"
  else
    say "AFTER the rejoin, the cluster's pods could not be read: the work's fate after the rejoin was not captured"
    differ "the pods could not be read back after the rejoin"
  fi
  say "AFTER the rejoin, the Jobs that owned them:"
  while IFS=' ' read -r job_ns job_name record <&3; do
    [ -n "$job_name" ] || continue
    if ! now="$(read_job "$job_ns" "$job_name")"; then
      say "  job $job_ns/$job_name could not be read after the rejoin"
      differ "Job $job_ns/$job_name could not be read back after the rejoin"
      continue
    fi
    IFS='|' read -r _ _ now_failed _ _ now_backoff <<<"$now"
    fate=""
    if [ -n "$now" ] && [ "${now_backoff:-}" = 0 ] && [ "${now_failed:-0}" != 0 ]; then
      fate="; backoffLimit=0 and a failed pod: this Job does not retry, so its work is lost and its client reads the failure"
    elif [ -n "$now" ]; then
      fate="; backoffLimit=${now_backoff:-unset}"
    fi
    say "  job $job_ns/$job_name after the rejoin: $(job_text "$now")$fate"
  done 3<<EOF
$jobs_before
EOF
  if [ -n "$factory_pods" ]; then
    say "FACTORY after the rejoin: read each run's state at the factory server for these sandbox pods (their pod lines are above); this script cannot read a run:"
    say_lines "$factory_pods"
  fi

  running="$(in_vm docker inspect -f '{{.State.Running}}' "$worker" 2>/dev/null)" || running="absent"
  say "AFTER worker container $worker: running=$running"
  [ "$running" = true ] ||
    differ "worker container $worker is not running (State.Running is '$running')"

  # The bridge exists only once the restarted node runs a pod on the pod
  # network, and the collector unit binds a few seconds after the bridge is
  # up (measured 2026-11-13: Node Ready 20:17:44Z, listening 20:17:54Z, and a
  # single read in between failed a drill that had in fact passed). Both are
  # awaited inside the same bound; an endpoint mismatch is final at once.
  collector_pending() {
    [ -n "$c_endpoint" ] || return 1
    [ -n "$c_bridge" ] || return 0
    [ "${c_endpoint%:*}" = "$c_bridge" ] && [ "$c_listening" != true ]
  }
  read_collector
  while collector_pending && [ "$waited" -lt "$wait_seconds" ]; do
    sleep "$poll"
    waited="$((waited + poll))"
    read_collector
  done
  if [ -z "$c_endpoint" ]; then
    say "COLLECTOR not configured: $state_root/telemetry/node.env names no OTLP_PODS_ENDPOINT"
    differ "COLLECTOR: node.env names no OTLP_PODS_ENDPOINT"
  elif [ -z "$c_bridge" ]; then
    say "COLLECTOR not comparable: container $worker has no cni0 address ${waited}s after the return; node.env says $c_endpoint"
    differ "COLLECTOR: no cni0 address to compare node.env's $c_endpoint with"
  elif [ "${c_endpoint%:*}" != "$c_bridge" ]; then
    say "COLLECTOR endpoint mismatch: node.env says $c_endpoint, cni0 is now $c_bridge; nothing rewrote node.env on the return (listening on the stale endpoint: ${c_listening:-false})"
    differ "COLLECTOR: node.env endpoint $c_endpoint is not on the current cni0 address $c_bridge"
  elif [ "$c_listening" != true ]; then
    say "COLLECTOR not listening: node.env's $c_endpoint matches cni0 ($c_bridge), but nothing listens there ${waited}s after the return"
    differ "COLLECTOR: nothing listens on $c_endpoint"
  else
    say "COLLECTOR endpoint $c_endpoint matches cni0 ($c_bridge) and is listening"
  fi
fi

if [ -n "$differences" ]; then
  say "the worker did not come back as it left ($mode, departed $departed_at, returned $returned_at):" >&2
  printf '%s' "$differences" | sed "s/^/$prog:   /" >&2
  exit 1
fi
say "the worker left at $departed_at ($mode), was away ${hold}s, and after the one return command at $returned_at rejoined as it was: the same Node, taints, enrollment labels and churn-slot value, with its collector listening on the current cni0 address"
say "the classes printed above are the evidence for the work that was on it; this script does not judge them"
