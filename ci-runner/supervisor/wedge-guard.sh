#!/usr/bin/env bash
# wedge-guard.sh — mid-job liveness guard for the ephemeral CI-runner pool.
#
# Closes a gap distinct from the pre-dispatch dockershim health check
# (dockershim-exit-tests.sh / the .10 fail-closed readiness check): a runner
# that PASSES readiness and is then assigned a job can still wedge INSIDE the
# custom container-hook binary (ci-runner/dockershim/docker) mid-job, most
# often during the Actions runner's own "Initialize containers" / "Stop
# containers" steps, which invoke the shim's `create`/`start`/`rm`/`exec`
# paths. Before this guard, ci-runner-supervisor.sh's wait loop
# (`while systemctl is-active --quiet "$unit"; do sleep 5; done`) had no
# notion of "stuck" — a wedged unit sat there holding its slot indefinitely,
# invisible to the supervisor, since systemd reports it ACTIVE the whole time.
#
# Evidence motivating the generous default threshold (livespec-s43svm.12,
# 2026-08-14): livespec-overseer PR #902 showed "Initialize containers"
# taking up to ~480s and "Stop containers" up to ~525s on a heavily
# IO-contended host (iowait 65-89% observed live, not CPU-bound: load ~42 on
# a 72-core host). Root-caused to host-wide IO contention under concurrent CI
# load, NOT a regression in the dockershim "preenvfix" patch (diffed and
# reviewed 2026-08-14 -- that patch only ADDED bounded fixes: env-var repair,
# bind-source mkdir, a <=10s bounded exec retry -- nothing unbounded). This
# guard is therefore a bounded LIVENESS BACKSTOP for whatever residual or
# future cause produces a multi-minute+ stall, not a fix for a specific bug in
# the shim itself.
#
# Detection strategy: a wedge inside the shim shows up as a SINGLE dockershim
# invocation (a child process running the shim binary itself) that has been
# running, uninterrupted, longer than CI_RUNNER_WEDGE_TIMEOUT_SECONDS. This is
# a precise signal distinct from "the job is just doing a lot of real work" --
# real `just check` work never runs INSIDE the shim process itself, only
# through it briefly per docker/podman call.
#
# Both process enumeration and the recycle action are overridable
# (CI_RUNNER_WEDGE_PROCS_CMD / CI_RUNNER_WEDGE_STOP_CMD) so this file's exit
# tests (wedge-guard-exit-tests.sh) can fault-inject a wedged process without
# a real systemd unit, cgroup, or dockershim invocation -- the same pattern
# dockershim-exit-tests.sh uses for CI_RUNNER_REAL_DOCKER.
set -uo pipefail

# Generous by design: real Initialize/Stop-containers stalls observed under
# fleet-wide contention topped out around 525s (~9min). 900s (15min) gives
# real slow-but-progressing jobs headroom while still bounding how long a
# genuinely wedged runner can silently hold a slot.
CI_RUNNER_WEDGE_TIMEOUT_SECONDS="${CI_RUNNER_WEDGE_TIMEOUT_SECONDS:-900}"
CI_RUNNER_WEDGE_SHIM_PATH="${CI_RUNNER_WEDGE_SHIM_PATH:-/usr/local/lib/ci-runner/dockershim/docker}"

# Overridable for fault-injection tests. MUST emit one line per candidate
# process as "<pid>|<etimes>|<cmdline>" (etimes = elapsed seconds, matching
# `ps -o etimes=`), scoped to the given unit's process tree. Real default
# walks the unit's own systemd cgroup.
CI_RUNNER_WEDGE_PROCS_CMD="${CI_RUNNER_WEDGE_PROCS_CMD:-_wedge_guard_real_procs}"

# Overridable for tests: recycles (force-stops) the wedged unit. Real default
# is `systemctl stop`, which returns control to ci-runner-supervisor.sh's
# EXISTING single-writer `while :; do run_one ... || sleep 10; done` loop --
# this guard never mints or starts a replacement itself, so replacement stays
# on the fleet's normal paced, single-writer replenishment path.
CI_RUNNER_WEDGE_STOP_CMD="${CI_RUNNER_WEDGE_STOP_CMD:-_wedge_guard_real_stop}"

_wedge_guard_real_procs() {
  local unit="$1" cgroup pid cmdline etimes
  cgroup="$(systemctl show -p ControlGroup --value "$unit" 2>/dev/null)" || return 0
  [ -n "$cgroup" ] || return 0
  [ -r "/sys/fs/cgroup${cgroup}/cgroup.procs" ] || return 0
  while read -r pid; do
    [ -n "$pid" ] || continue
    [ -r "/proc/$pid/cmdline" ] || continue
    cmdline="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null)" || continue
    etimes="$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d ' ')"
    [ -n "$etimes" ] || continue
    printf '%s|%s|%s\n' "$pid" "$etimes" "$cmdline"
  done <"/sys/fs/cgroup${cgroup}/cgroup.procs"
}

_wedge_guard_real_stop() {
  systemctl stop "$1"
}

# Pure detection: prints the wedged pid on stdout and returns 0 when found;
# returns 1 and prints nothing otherwise. Never mutates state.
wedge_guard_detect() {
  local unit="$1" pid etimes cmdline
  while IFS='|' read -r pid etimes cmdline; do
    [ -n "$pid" ] || continue
    case "$cmdline" in
      *"$CI_RUNNER_WEDGE_SHIM_PATH"*)
        if [ "${etimes:-0}" -ge "$CI_RUNNER_WEDGE_TIMEOUT_SECONDS" ] 2>/dev/null; then
          printf '%s\n' "$pid"
          return 0
        fi
        ;;
    esac
  done < <("$CI_RUNNER_WEDGE_PROCS_CMD" "$unit")
  return 1
}

# Detect + recycle in one step, for ci-runner-supervisor.sh's wait loop.
# Returns 0 ("still fine, keep waiting") when nothing is wedged. Returns 1
# ("recycled") after force-stopping a wedged unit -- the caller's own loop
# then re-mints and restarts it at the normal paced rate; this function
# starts nothing itself.
wedge_guard_check_and_recycle() {
  local unit="$1" pid
  pid="$(wedge_guard_detect "$unit")" || return 0
  printf 'wedge-guard: unit %s wedged in dockershim (pid %s, elapsed >= %ss) -- force-recycling\n' \
    "$unit" "$pid" "$CI_RUNNER_WEDGE_TIMEOUT_SECONDS" >&2
  "$CI_RUNNER_WEDGE_STOP_CMD" "$unit"
  return 1
}
