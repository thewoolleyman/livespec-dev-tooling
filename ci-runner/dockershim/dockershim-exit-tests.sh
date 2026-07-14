#!/usr/bin/env bash
# dockershim-exit-tests.sh — exit tests for the docker serialization shim.
#
# The shim exists to kill ONE bug: podman's `network prune` walks the GLOBAL
# container database, so it fails when a concurrent job removes a container
# mid-scan ("no container with ID <other job's id> found in database"). See
# ci-runner/dockershim/docker for the full write-up.
#
# The contract it must hold is a readers-writer lock, and that contract is easy
# to "simplify" back into the flake — drop the lock on `rm`, or downgrade prune
# from exclusive to shared, and everything still LOOKS fine until 12 jobs run at
# once. So we test the contract behaviorally rather than by reading the source:
# hold a lock on the shim's lockfile from outside, then assert which invocations
# BLOCK on it and which sail straight past.
#
#   * `network prune`             must take an EXCLUSIVE lock (blocks on any holder)
#   * `create` / `rm` / `network` must take a SHARED lock    (blocks only on exclusive)
#   * everything else             must NOT lock at all       (never blocks)
#
# Needs no podman and no runner: the real docker is swapped for a fake via
# CI_RUNNER_REAL_DOCKER. Run it anywhere: ./dockershim-exit-tests.sh
set -uo pipefail

SHIM="$(cd "$(dirname "$0")" && pwd)/docker"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

LOCKFILE="$TMP/podman-db.lock"
: >"$LOCKFILE"

# Fake docker: records its argv, exits 0. Proves pass-through as a side effect.
FAKE="$TMP/fake-docker"
cat >"$FAKE" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_DOCKER_ARGV_LOG"
exit 0
EOF
chmod +x "$FAKE"

pass=0
fail=0
ok()   { printf '  PASS  %s\n' "$1"; pass=$((pass + 1)); }
bad()  { printf '  FAIL  %s\n' "$1"; fail=$((fail + 1)); }

# Run the shim with a wall-clock cap. Exit 124 (timeout) == "it blocked on the
# lock"; 0 == "it ran through". A 3s cap against a 30s lock holder is unambiguous.
run_shim() {
  env CI_RUNNER_REAL_DOCKER="$FAKE" \
      CI_RUNNER_PODMAN_LOCK="$LOCKFILE" \
      FAKE_DOCKER_ARGV_LOG="$TMP/argv.log" \
      timeout 3 "$SHIM" "$@" >/dev/null 2>&1
  printf '%s' "$?"
}

# Hold the lock in the given mode for 30s; echo the holder's pid.
hold_lock() {
  # stdout/stderr MUST go to /dev/null: this runs under $(...), and a background
  # child inheriting the capture pipe keeps it open, so the command substitution
  # would wait out the full sleep and hand back an already-RELEASED lock.
  /usr/bin/flock "$1" "$LOCKFILE" sleep 30 >/dev/null 2>&1 &
  local pid=$!
  # Give flock a moment to actually acquire before the assertions race it.
  local waited=0
  while [ "$waited" -lt 20 ]; do
    /usr/bin/flock -n -x "$LOCKFILE" true 2>/dev/null || break
    sleep 0.1
    waited=$((waited + 1))
  done
  printf '%s' "$pid"
}

# Drop the lock and do not return until it is genuinely free. Killing the flock
# pid is NOT enough: flock hands the open lock fd to the command it runs, so the
# `sleep` child keeps holding the lock after its flock parent dies — and every
# later assertion would then be silently racing a lock it thinks it released.
release_lock() {
  pkill -P "$1" 2>/dev/null
  kill "$1" 2>/dev/null
  local waited=0
  while [ "$waited" -lt 50 ]; do
    /usr/bin/flock -n -x "$LOCKFILE" true 2>/dev/null && return 0
    sleep 0.1
    waited=$((waited + 1))
  done
  printf '  ERROR lock never released — remaining assertions would be meaningless\n'
  exit 1
}

expect_blocks() {
  local label="$1"; shift
  local rc; rc="$(run_shim "$@")"
  [ "$rc" = "124" ] && ok "$label" || bad "$label (expected to block on the lock; exit=$rc)"
}
expect_runs() {
  local label="$1"; shift
  local rc; rc="$(run_shim "$@")"
  [ "$rc" = "0" ] && ok "$label" || bad "$label (expected to run through; exit=$rc)"
}

printf '\n== T1-T3: an EXCLUSIVE holder blocks every DB-mutating call ==\n'
holder="$(hold_lock -x)"
expect_blocks "T1 network prune blocks behind an exclusive holder" network prune --force --filter label=x
expect_blocks "T2 rm blocks behind an exclusive holder"            rm --force deadbeef
expect_blocks "T3 create blocks behind an exclusive holder"        create --label=x img
release_lock "$holder"

printf '\n== T4-T6: a SHARED holder blocks ONLY the prune ==\n'
# This is the whole point: removals must stay concurrent with each other (they
# never raced), while the prune waits for every one of them to finish.
holder="$(hold_lock -s)"
expect_blocks "T4 network prune blocks behind a shared holder (it needs exclusive)" network prune --force --filter label=x
expect_runs   "T5 rm runs concurrently with another shared holder"                  rm --force deadbeef
expect_runs   "T6 create runs concurrently with another shared holder"              create --label=x img
release_lock "$holder"

printf '\n== T7-T9: non-mutating calls are never locked (parallelism is the point) ==\n'
# `exec` runs the actual job steps and `pull` fetches the image — locking either
# would serialize the CI matrix this runner pool exists to parallelize.
holder="$(hold_lock -x)"
expect_runs "T7 exec is unlocked even behind an exclusive holder"    exec -i c1 /bin/true
expect_runs "T8 pull is unlocked even behind an exclusive holder"    pull ghcr.io/x/y:z
expect_runs "T9 ps is unlocked even behind an exclusive holder"      ps --all --quiet --filter label=x
release_lock "$holder"

printf '\n== T10: argv reaches the real docker verbatim ==\n'
: >"$TMP/argv.log"
run_shim network prune --force --filter label=abc123 >/dev/null
if grep -qx 'network prune --force --filter label=abc123' "$TMP/argv.log"; then
  ok "T10 args pass through to the real docker unchanged"
else
  bad "T10 args pass through to the real docker unchanged (got: $(cat "$TMP/argv.log"))"
fi

printf '\n== T11: an uncontended prune does not stall ==\n'
# The lock must be effectively free when nothing else is running — otherwise the
# fix would tax every single-job run.
expect_runs "T11 network prune runs immediately when nothing holds the lock" network prune --force --filter label=x

printf '\nresult: %s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
