#!/usr/bin/env bash
# window.sh <action> <host> — the M4 window route's ON-HOST half
# (livespec-dev-tooling-nn4yxt). ansible/homelab-worker-window.yml runs it on
# the worker's Mac from the delivered release directory, with PATH, the
# cluster-reaching kubectl and the join values set from inventory. It wraps
# remove-worker.sh, join-worker.sh and departure-drill.sh and fences each to
# the one node <host>-homelab-worker.
#
# Actions (each acts on that node only):
#   snapshot  record gates-cq (kubectl get clusterqueue gates-cq -o json) under
#             WINDOW_STATE_DIR with the UTC time it was taken, as the window's
#             before-state. Refuses to overwrite an existing snapshot, so the
#             before-state is never replaced by a mid-window state.
#   join      join-worker.sh <host> --api-server $WINDOW_API_SERVER --server-ca
#             $WINDOW_SERVER_CA. Refuses unless a snapshot taken for this window
#             exists and is younger than WINDOW_MAX_AGE_SECONDS (default 86400),
#             because the join runs converge-worker-queues.sh, which patches gates-cq.
#   drill     departure-drill.sh <host> --confirm-depart <node>
#   remove    remove-worker.sh <host> (it refuses an uncordoned node)
#   check     the revert TRIGGER: the node must be Ready within
#             WINDOW_BOUND_SECONDS (a failed read is retried 3 times and is not
#             "not Ready"), and no non-terminal pod a DaemonSet does not own may
#             be bound to it. Either failure runs `revert` and exits 3.
#   revert    cordon the node, depart it (remove-worker.sh), and ONLY IF THE
#             DEPARTURE SUCCEEDED restore gates-cq from the snapshot, then archive
#             the snapshot as gates-cq-before.<UTC>.json. remove-worker.sh refuses
#             while a Running or Pending pod no DaemonSet owns is on the node, and it
#             never evicts. So a revert triggered by such a pod ends INCOMPLETE,
#             exits non-zero, and leaves the node cordoned and enrolled and gates-cq
#             as it is. The operator then moves the work (ansible/k3s-window-drain.yml,
#             action evacuate, or waits for it) and re-runs revert.
#
# The restore is a JSON patch of the one thing converge-worker-queues.sh changes,
# the flavor list of gates-cq's cpu resource group, taken from the snapshot, so
# any other edit made to gates-cq since the snapshot is kept. It refuses when the
# snapshot names a ResourceFlavor that no longer exists. kubectl runs through
# remote-kubectl.sh, which forwards only arguments and stdin, so nothing here
# passes a local file path to kubectl.
#
# Environment: WINDOW_NODE_CONFIRM (must equal <host>-homelab-worker),
# WINDOW_STATE_DIR, WINDOW_API_SERVER, WINDOW_SERVER_CA, WINDOW_BOUND_SECONDS
# (default 600), WINDOW_POLL_SECONDS (default 15), WINDOW_MAX_AGE_SECONDS,
# WINDOW_RETRY_SECONDS (default 2), WINDOW_SCRIPTS_DIR (default: this script's
# directory), HOMELAB_WORKER_HOSTS_DIR.
# Written for bash 3.2 (the macOS system bash); no mapfile.
set -euo pipefail

prog="window"
hw="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
scripts="${WINDOW_SCRIPTS_DIR:-$hw}"
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$hw/hosts}"
bound="${WINDOW_BOUND_SECONDS:-600}"
poll="${WINDOW_POLL_SECONDS:-15}"
max_age="${WINDOW_MAX_AGE_SECONDS:-86400}"
retry_sleep="${WINDOW_RETRY_SECONDS:-2}"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}
say() {
  printf '%s: %s\n' "$prog" "$*"
}

[ "$#" -eq 2 ] || die "usage: $prog snapshot|join|drill|remove|check|revert <host>"
action="$1"
host="$2"
case "$host" in
  *[!a-z0-9-]* | -* | "") die "host '$host' is not a valid host name" ;;
esac
[ -f "$hosts_dir/$host.env" ] || die "host '$host' is not declared in homelab-worker/hosts/"
node="$host-homelab-worker"
[ "${WINDOW_NODE_CONFIRM:-}" = "$node" ] ||
  die "WINDOW_NODE_CONFIRM is '${WINDOW_NODE_CONFIRM:-}', not '$node': refusing, nothing was changed"
state="${WINDOW_STATE_DIR:-}"
[ -n "$state" ] || die "WINDOW_STATE_DIR is not set"
snap="$state/gates-cq-before.json"

# ready: 0 when the node's Ready condition is True, 1 when it is not True, 2 when
# the node could not be read in 3 tries (a failed read is not "not Ready").
ready() {
  local out i=0
  while [ "$i" -lt 3 ]; do
    if out="$(kubectl get node "$node" -o json 2>/dev/null)"; then
      printf '%s' "$out" | python3 -c '
import json, sys
n = json.load(sys.stdin)
sys.exit(0 if any(c.get("type") == "Ready" and c.get("status") == "True"
                  for c in n.get("status", {}).get("conditions", [])) else 1)' && return 0
      return 1
    fi
    i=$((i + 1))
    [ "$i" -ge 3 ] || sleep "$retry_sleep"
  done
  return 2
}

# foreign_pods: namespace/name of each non-terminal pod bound to the node that no
# DaemonSet owns (a pod with no owner counts; Succeeded and Failed pods do not,
# as in remove-worker.sh). Fails loudly when the read fails.
foreign_pods() {
  local out
  out="$(kubectl get pods --all-namespaces --field-selector "spec.nodeName=$node" -o json)" ||
    return 1
  printf '%s' "$out" | python3 -c '
import json, sys
for p in json.load(sys.stdin).get("items", []):
    if p.get("status", {}).get("phase") in ("Succeeded", "Failed"):
        continue
    if not any(o.get("kind") == "DaemonSet" for o in p["metadata"].get("ownerReferences", [])):
        print("%s/%s" % (p["metadata"]["namespace"], p["metadata"]["name"]))'
}

do_snapshot() {
  mkdir -p "$state"
  [ ! -e "$snap" ] || die "a before-snapshot already exists at $snap; refusing to replace it (revert the window, or archive it deliberately)"
  local out
  out="$(kubectl get clusterqueue gates-cq -o json)" || die "could not read gates-cq; no snapshot was taken"
  printf '%s' "$out" | python3 -c '
import datetime, json, sys, time
q = json.load(sys.stdin)
for k in ("resourceVersion", "uid", "creationTimestamp", "generation", "managedFields", "selfLink"):
    q["metadata"].pop(k, None)
q.pop("status", None)
now = datetime.datetime.now(datetime.timezone.utc)
json.dump({"taken_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "taken_at_epoch": int(time.time()),
           "queue": q}, sys.stdout, indent=1)' >"$snap.tmp"
  mv "$snap.tmp" "$snap"
  say "snapshot of gates-cq written to $snap"
}

# snapshot_problem: prints why the window has no usable before-snapshot, else nothing.
snapshot_problem() {
  [ -f "$snap" ] || { echo "no before-snapshot at $snap"; return 0; }
  python3 -c '
import json, sys, time
age = time.time() - json.load(open(sys.argv[1]))["taken_at_epoch"]
if age > int(sys.argv[2]):
    print("the before-snapshot at %s is %d s old, over the %s s window limit" % (sys.argv[1], age, sys.argv[2]))' "$snap" "$max_age"
}

# restore_queue: put back the flavor list of gates-cq's cpu resource group as the
# snapshot recorded it, leaving everything else on gates-cq alone. Refuses, with
# the queue untouched, on a missing or stale snapshot, or when the snapshot names
# a ResourceFlavor that no longer exists (converge-worker-queues.sh deletes the
# retired gates-worker-arm64-flavor, and a queue naming a missing flavor is
# inactive).
restore_queue() {
  local problem flavor live patch
  problem="$(snapshot_problem)"
  [ -z "$problem" ] || { say "RESTORE FAILED: $problem"; return 1; }
  for flavor in $(python3 -c '
import json, sys
q = json.load(open(sys.argv[1]))["queue"]
for g in q["spec"]["resourceGroups"]:
    for f in g["flavors"]:
        print(f["name"])' "$snap" | sort -u); do
    kubectl get resourceflavor "$flavor" >/dev/null 2>&1 || {
      say "RESTORE FAILED: the snapshot names ResourceFlavor $flavor, which does not exist; gates-cq was left as it is"
      return 1
    }
  done
  live="$(kubectl get clusterqueue gates-cq -o json)" || { say "RESTORE FAILED: could not read gates-cq"; return 1; }
  patch="$(printf '%s' "$live" | python3 -c '
import json, sys
live = json.load(sys.stdin)
snap = json.load(open(sys.argv[1]))["queue"]
def cpu(q):
    return next(i for i, g in enumerate(q["spec"]["resourceGroups"]) if "cpu" in g.get("coveredResources", []))
want = snap["spec"]["resourceGroups"][cpu(snap)]["flavors"]
print(json.dumps([{"op": "replace", "path": "/spec/resourceGroups/%d/flavors" % cpu(live), "value": want}]))' "$snap")" ||
    { say "RESTORE FAILED: could not build the patch"; return 1; }
  kubectl patch clusterqueue gates-cq --type=json -p "$patch" >/dev/null || { say "RESTORE FAILED: kubectl patch of gates-cq failed"; return 1; }
  say "gates-cq cpu-group flavors restored from $snap"
}

do_revert() {
  say "REVERT: departing $node and restoring gates-cq"
  kubectl cordon "$node" >/dev/null || say "could not cordon $node; the removal below will refuse an uncordoned node"
  if ! "$scripts/remove-worker.sh" "$host"; then
    say "REVERT INCOMPLETE: the departure of $node failed or was refused (it never evicts). $node is still enrolled and cordoned, and gates-cq was NOT restored. Move the work off it (ansible/k3s-window-drain.yml, action evacuate, or wait for it to finish) and run revert again."
    return 1
  fi
  restore_queue || { say "REVERT INCOMPLETE: $node departed but gates-cq was not restored; fix the cause above and run revert again"; return 1; }
  mv "$snap" "$state/gates-cq-before.$(date -u +%Y%m%dT%H%M%SZ).json"
  say "REVERT: complete; the snapshot was archived under $state"
}

do_check() {
  local deadline foreign rc
  deadline=$(($(date +%s) + bound))
  while :; do
    foreign="$(foreign_pods)" || die "could not read the pods on $node; no verdict"
    if [ -n "$foreign" ]; then
      say "TRIGGER: non-DaemonSet pod(s) landed on $node:"
      printf '%s\n' "$foreign" | sed "s/^/$prog:   /"
      do_revert || true
      exit 3
    fi
    rc=0
    ready || rc=$?
    if [ "$rc" -eq 0 ]; then
      say "ok: $node is Ready and carries only DaemonSet pods"
      return 0
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      if [ "$rc" -eq 2 ]; then
        say "TRIGGER: $node could not be read within ${bound}s"
      else
        say "TRIGGER: $node is not Ready within ${bound}s"
      fi
      do_revert || true
      exit 3
    fi
    sleep "$poll"
  done
}

case "$action" in
  snapshot) do_snapshot ;;
  join)
    problem="$(snapshot_problem)"
    [ -z "$problem" ] || die "refusing to join: $problem (run the snapshot action for this window first)"
    [ -n "${WINDOW_API_SERVER:-}" ] || die "WINDOW_API_SERVER is not set"
    [ -n "${WINDOW_SERVER_CA:-}" ] || die "WINDOW_SERVER_CA is not set"
    exec "$scripts/join-worker.sh" "$host" --api-server "$WINDOW_API_SERVER" --server-ca "$WINDOW_SERVER_CA"
    ;;
  drill) exec "$scripts/departure-drill.sh" "$host" --confirm-depart "$node" ;;
  remove) exec "$scripts/remove-worker.sh" "$host" ;;
  check) do_check ;;
  revert) do_revert ;;
  *) die "unknown action '$action'" ;;
esac
