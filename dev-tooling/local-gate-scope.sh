#!/usr/bin/env bash
# local-gate-scope.sh — run a gate command inside the host's gate memory slice.
#
# Authority: the local gate concurrency limit in
# SPECIFICATION/non-functional-requirements.md, its Gate memory slice paragraph.
#
# Usage: local-gate-scope.sh <command> [args...]
#
# Where the login's service manager loads `local-gate.slice` and a probe scope
# can be created there, the command runs, with everything it starts, in a
# transient scope in that slice with OOMPolicy=continue. When `choom` exists it
# runs with oom_score_adj 500, so under host memory pressure the kernel ends a
# gate before the ledger server or an agent session. Raising the score needs no
# privilege.
#
# Anywhere else (macOS, a factory sandbox, a gate Job, a host without the
# slice) the command runs unchanged, with the same argv and environment. A
# launch that already runs inside the slice is not scoped a second time.
#
# OOMPolicy=continue matters: systemd 257 defaults to DefaultOOMPolicy=stop,
# under which one OOM-killed child stops the whole scope and the gate ends
# without a verdict.
#
# The slice and its bounds are host provisioning
# (ansible/roles/dev_host_memory_bounds); this script only uses them.
#
# Seams for tests: LIVESPEC_LOCAL_GATE_CGROUP_FILE (default /proc/self/cgroup).
set -uo pipefail

slice="local-gate.slice"
oom_score_adj=500
cgroup_file="${LIVESPEC_LOCAL_GATE_CGROUP_FILE:-/proc/self/cgroup}"

if [ "$#" -eq 0 ]; then
  echo "usage: local-gate-scope.sh <command> [args...]" >&2
  exit 64
fi

# Every launch through here marks itself, so a later launch can tell it has
# already been through this script.
export LIVESPEC_LOCAL_GATE_SCOPE=1

already_in_slice() {
  grep -q "/${slice}/" "$cgroup_file" 2>/dev/null
}

slice_usable() {
  [ "$(uname -s 2>/dev/null)" = "Linux" ] || return 1
  command -v systemd-run >/dev/null 2>&1 || return 1
  command -v systemctl >/dev/null 2>&1 || return 1
  [ "$(systemctl --user show -p LoadState --value "$slice" 2>/dev/null)" = "loaded" ] || return 1
  # The probe: a scope the manager refuses here is refused below too, so fall
  # back now rather than fail the gate on the real launch.
  systemd-run --user --scope --quiet --collect --slice="$slice" -- true >/dev/null 2>&1
}

if already_in_slice || ! slice_usable; then
  exec "$@"
fi

if command -v choom >/dev/null 2>&1; then
  exec systemd-run --user --scope --quiet --collect --slice="$slice" \
    -p OOMPolicy=continue -- choom -n "$oom_score_adj" -- "$@"
fi
exec systemd-run --user --scope --quiet --collect --slice="$slice" \
  -p OOMPolicy=continue -- "$@"
