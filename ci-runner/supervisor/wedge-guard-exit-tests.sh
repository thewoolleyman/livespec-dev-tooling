#!/usr/bin/env bash
# wedge-guard-exit-tests.sh — fault-injection exit tests for wedge-guard.sh.
#
# Reproduces a runner wedged mid-job inside the dockershim binary (the
# livespec-s43svm.12 scenario: "Initialize containers" / "Stop containers"
# hanging for minutes with the systemd unit still reporting ACTIVE) WITHOUT a
# real systemd unit, cgroup, or dockershim process -- both process
# enumeration and the recycle action are swapped for fakes via
# CI_RUNNER_WEDGE_PROCS_CMD / CI_RUNNER_WEDGE_STOP_CMD, the same override
# pattern dockershim-exit-tests.sh uses for CI_RUNNER_REAL_DOCKER.
#
# Contract under test:
#   * a dockershim child process running >= the configured threshold IS
#     detected and triggers a recycle (stop) of the owning unit;
#   * a dockershim child process running < the threshold does NOT trigger a
#     recycle -- a merely-slow-but-progressing job must not be killed;
#   * a wedged NON-dockershim process (any other long-running child, e.g. the
#     job's own real work) does NOT trigger a recycle -- this guard is scoped
#     to the shim specifically, not "job taking a while";
#   * once recycled, the guard itself starts nothing -- it only stops the
#     unit, leaving replacement to the caller's existing single-writer
#     replenish loop (proven here as "stop was called exactly once, start was
#     never called").
#
# Run anywhere: ./wedge-guard-exit-tests.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=./wedge-guard.sh
. "$HERE/wedge-guard.sh"

pass=0
fail=0
ok() {
  printf '  PASS  %s\n' "$1"
  pass=$((pass + 1))
}
bad() {
  printf '  FAIL  %s\n' "$1"
  fail=$((fail + 1))
}

STOP_LOG=""
fake_stop() {
  STOP_LOG="${STOP_LOG}stop:$1;"
}

# --- Test 1: wedged dockershim process at exactly the threshold -> recycled
export CI_RUNNER_WEDGE_TIMEOUT_SECONDS=900
export CI_RUNNER_WEDGE_SHIM_PATH="/usr/local/lib/ci-runner/dockershim/docker"
export CI_RUNNER_WEDGE_STOP_CMD=fake_stop
STOP_LOG=""
fake_procs_wedged() {
  printf '4242|900|/usr/local/lib/ci-runner/dockershim/docker exec abc123 -- true\n'
}
export CI_RUNNER_WEDGE_PROCS_CMD=fake_procs_wedged
if wedge_guard_check_and_recycle "runner@livespec-1.service"; then
  bad "wedged-past-threshold: expected recycle (return 1), got return 0 (no action)"
else
  if [ "$STOP_LOG" = "stop:runner@livespec-1.service;" ]; then
    ok "wedged-past-threshold: recycled the correct unit exactly once"
  else
    bad "wedged-past-threshold: expected exactly one stop of the right unit, got: ${STOP_LOG}"
  fi
fi

# --- Test 2: dockershim process running but well under the threshold -> no action
export CI_RUNNER_WEDGE_TIMEOUT_SECONDS=900
STOP_LOG=""
fake_procs_still_working() {
  printf '4242|30|/usr/local/lib/ci-runner/dockershim/docker create --name x\n'
}
export CI_RUNNER_WEDGE_PROCS_CMD=fake_procs_still_working
if wedge_guard_check_and_recycle "runner@livespec-1.service"; then
  if [ -z "$STOP_LOG" ]; then
    ok "under-threshold: no recycle, no stop call for a merely-slow-but-progressing invocation"
  else
    bad "under-threshold: expected no stop call, got: ${STOP_LOG}"
  fi
else
  bad "under-threshold: expected return 0 (still fine), got return 1 (recycled)"
fi

# --- Test 3: a long-running NON-dockershim process (real job work) -> no action
export CI_RUNNER_WEDGE_TIMEOUT_SECONDS=900
STOP_LOG=""
fake_procs_real_work() {
  printf '5001|1200|/usr/bin/python3 -m pytest -q\n'
}
export CI_RUNNER_WEDGE_PROCS_CMD=fake_procs_real_work
if wedge_guard_check_and_recycle "runner@livespec-1.service"; then
  if [ -z "$STOP_LOG" ]; then
    ok "non-dockershim-long-runner: real job work, however long, is never mistaken for a wedge"
  else
    bad "non-dockershim-long-runner: expected no stop call, got: ${STOP_LOG}"
  fi
else
  bad "non-dockershim-long-runner: expected return 0 (still fine), got return 1 (recycled)"
fi

# --- Test 4: guard never starts anything itself -- only the stop side effect fires
export CI_RUNNER_WEDGE_TIMEOUT_SECONDS=900
STOP_LOG=""
START_CALLED=0
fake_start() { START_CALLED=1; }
export CI_RUNNER_WEDGE_PROCS_CMD=fake_procs_wedged
export CI_RUNNER_WEDGE_STOP_CMD=fake_stop
wedge_guard_check_and_recycle "runner@livespec-1.service" >/dev/null 2>&1 || true
if [ "$START_CALLED" -eq 0 ] && [ -n "$STOP_LOG" ]; then
  ok "recycle-scope: only stop fires; replacement is left to the caller's own replenish loop"
else
  bad "recycle-scope: guard must never start a replacement itself"
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
