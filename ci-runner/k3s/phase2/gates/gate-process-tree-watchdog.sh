# shellcheck shell=bash
# gate-process-tree-watchdog.sh — keeps a gate Job's process tree in its log.
# render-gate-job.sh inlines this file's functions into the gate container's
# script. It is not executed on its own.
#
# WHY. A gate Job whose recipes finished but whose container never exits gets
# abandoned by the delegated client, which saves the last 200 log lines of
# every container before it deletes the Job (livespec-dev-tooling-yrjatv). The
# client holds no pods/exec credential, so the POD prints its own process tree
# and the saved lines carry it.
#
# WHEN. The end of the recipe run is not observable from here (a leaked child
# holding the output pipe stops the pipeline from ending), so the watchdog
# watches the recipe log's quiet time instead. Once the log has been quiet for
# GATE_PROCESS_TREE_QUIET_SECONDS (default 300) it prints the tree, and it
# prints it again every GATE_PROCESS_TREE_QUIET_SECONDS while the container stays
# quiet. A recipe that is silent for that long mid-run also gets a tree: it is
# bounded and harmless. The pod's preStop hook prints one more before the kill;
# the client has already saved its lines by then, so the saved tree is the last
# periodic one.
#
# BOUNDED. Each dump is a header plus at most GATE_PROCESS_TREE_MAX_LINES
# (default 60) lines of at most 200 columns, so a quiet container emits only
# trees and the last 200 lines always hold at least three of them.
gate_process_tree_dump() {
  echo ":: gate: process tree at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  { ps -eo pid,ppid,etime,stat,args --forest 2>&1 || true; } | cut -c1-200 | head -n "${GATE_PROCESS_TREE_MAX_LINES:-60}" || true
}
gate_process_tree_watchdog() {
  local activity="$1"
  local quiet="${GATE_PROCESS_TREE_QUIET_SECONDS:-300}"
  local tick="${GATE_PROCESS_TREE_TICK_SECONDS:-5}"
  local last_dump=0 now mtime since
  while :; do
    sleep "${tick}"
    now="$(date +%s)"
    mtime="$(stat -c %Y "${activity}" 2>/dev/null || echo "${now}")"
    since="${mtime}"
    if [ "${last_dump}" -gt "${since}" ]; then
      since="${last_dump}"
    fi
    if [ $((now - since)) -ge "${quiet}" ]; then
      gate_process_tree_dump
      last_dump="${now}"
    fi
  done
}
