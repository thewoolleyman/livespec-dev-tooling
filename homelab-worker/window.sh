#!/usr/bin/env bash
# window.sh <action> <host> — the M4 window route's ON-HOST half
# (livespec-dev-tooling-nn4yxt). ansible/homelab-worker-window.yml runs it on
# the worker's Mac from the delivered release directory, with PATH, the
# cluster-reaching kubectl and the join values set from inventory. It wraps
# remove-worker.sh, join-worker.sh and departure-drill.sh and fences each to
# the one node <host>-homelab-worker.
#
# Actions (each acts on that node only):
#   snapshot  record gates-cq (kubectl get clusterqueue gates-cq -o json, with the
#             server-set metadata stripped) under WINDOW_STATE_DIR. Refuses to
#             overwrite an existing snapshot, so the before-state is never
#             replaced by a mid-window state.
#   join      join-worker.sh <host> --api-server $WINDOW_API_SERVER --server-ca
#             $WINDOW_SERVER_CA
#   drill     departure-drill.sh <host> --confirm-depart <node>
#   remove    remove-worker.sh <host> (it refuses an uncordoned node)
#   check     the revert TRIGGER: the node must be Ready within
#             WINDOW_BOUND_SECONDS, and no pod a DaemonSet does not own may be
#             bound to it. Either failure runs `revert` and exits 3 with a report.
#   revert    cordon the node, depart it (remove-worker.sh), restore gates-cq
#             from the snapshot. The restore runs even when the departure fails.
#
# Environment: WINDOW_NODE_CONFIRM (must equal <host>-homelab-worker),
# WINDOW_STATE_DIR, WINDOW_API_SERVER, WINDOW_SERVER_CA, WINDOW_BOUND_SECONDS
# (default 600), WINDOW_POLL_SECONDS (default 15), WINDOW_SCRIPTS_DIR (default:
# this script's directory), HOMELAB_WORKER_HOSTS_DIR.
# Written for bash 3.2 (the macOS system bash); no mapfile.
set -euo pipefail

prog="window"
hw="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
scripts="${WINDOW_SCRIPTS_DIR:-$hw}"
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$hw/hosts}"
bound="${WINDOW_BOUND_SECONDS:-600}"
poll="${WINDOW_POLL_SECONDS:-15}"

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

# ready: 0 when the node's Ready condition is True. A failed read is not-ready.
ready() {
  local out
  out="$(kubectl get node "$node" -o json 2>/dev/null)" || return 1
  printf '%s' "$out" | python3 -c '
import json, sys
n = json.load(sys.stdin)
sys.exit(0 if any(c.get("type") == "Ready" and c.get("status") == "True"
                  for c in n.get("status", {}).get("conditions", [])) else 1)'
}

# foreign_pods: namespace/name of each pod bound to the node that no DaemonSet
# owns (a pod with no owner counts). Fails loudly when the read fails.
foreign_pods() {
  local out
  out="$(kubectl get pods --all-namespaces --field-selector "spec.nodeName=$node" -o json)" ||
    return 1
  printf '%s' "$out" | python3 -c '
import json, sys
for p in json.load(sys.stdin).get("items", []):
    if not any(o.get("kind") == "DaemonSet" for o in p["metadata"].get("ownerReferences", [])):
        print("%s/%s" % (p["metadata"]["namespace"], p["metadata"]["name"]))'
}

do_snapshot() {
  mkdir -p "$state"
  [ ! -e "$snap" ] || die "a before-snapshot already exists at $snap; refusing to replace it (revert the window, or delete it deliberately)"
  local out
  out="$(kubectl get clusterqueue gates-cq -o json)" || die "could not read gates-cq; no snapshot was taken"
  printf '%s' "$out" | python3 -c '
import json, sys
q = json.load(sys.stdin)
for k in ("resourceVersion", "uid", "creationTimestamp", "generation", "managedFields", "selfLink"):
    q["metadata"].pop(k, None)
q.pop("status", None)
json.dump(q, sys.stdout, indent=1)' >"$snap.tmp"
  mv "$snap.tmp" "$snap"
  say "snapshot of gates-cq written to $snap"
}

# restore_queue: put gates-cq back as the snapshot recorded it. Refuses, leaving
# the queue untouched, when the snapshot names a ResourceFlavor that no longer
# exists (converge-worker-queues.sh deletes the retired gates-worker-arm64-flavor),
# since a queue naming a missing flavor is inactive.
restore_queue() {
  [ -f "$snap" ] || { say "RESTORE FAILED: no before-snapshot at $snap"; return 1; }
  local flavor
  for flavor in $(python3 -c '
import json, sys
q = json.load(open(sys.argv[1]))
for g in q["spec"]["resourceGroups"]:
    for f in g["flavors"]:
        print(f["name"])' "$snap" | sort -u); do
    kubectl get resourceflavor "$flavor" >/dev/null 2>&1 || {
      say "RESTORE FAILED: the snapshot names ResourceFlavor $flavor, which does not exist; gates-cq was left as it is"
      return 1
    }
  done
  kubectl replace -f "$snap" >/dev/null || { say "RESTORE FAILED: kubectl replace of $snap failed"; return 1; }
  say "gates-cq restored from $snap"
}

do_revert() {
  local rc=0
  say "REVERT: departing $node and restoring gates-cq"
  kubectl cordon "$node" >/dev/null || say "could not cordon $node; the removal below will refuse an uncordoned node"
  "$scripts/remove-worker.sh" "$host" || {
    say "REVERT: the departure of $node FAILED; it is still enrolled, read the output above"
    rc=1
  }
  restore_queue || rc=1
  [ "$rc" -eq 0 ] && say "REVERT: complete" || say "REVERT: INCOMPLETE, see the lines above"
  return "$rc"
}

do_check() {
  local deadline foreign
  deadline=$(($(date +%s) + bound))
  while :; do
    foreign="$(foreign_pods)" || die "could not read the pods on $node; no verdict"
    if [ -n "$foreign" ]; then
      say "TRIGGER: non-DaemonSet pod(s) landed on $node:"
      printf '%s\n' "$foreign" | sed "s/^/$prog:   /"
      do_revert || true
      exit 3
    fi
    if ready; then
      say "ok: $node is Ready and carries only DaemonSet pods"
      return 0
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      say "TRIGGER: $node is not Ready within ${bound}s"
      do_revert || true
      exit 3
    fi
    sleep "$poll"
  done
}

case "$action" in
  snapshot) do_snapshot ;;
  join)
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
