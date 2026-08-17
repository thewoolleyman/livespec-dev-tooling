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

printf '\n== T12-T14: the scrubbed hook environment is repaired before podman sees it ==\n'
# The container hooks hand the docker CLI the JOB CONTAINER's environment, so
# HOME points inside the container and PATH / XDG_RUNTIME_DIR are absent. podman
# derives real host paths from all three and dies without them (see the shim's
# header). Assert the REAL DOCKER is reached with a usable environment, whatever
# the shim was handed. Tested behaviorally — the fake records what it received.
FAKE_ENV="$TMP/fake-docker-env"
cat >"$FAKE_ENV" <<'EOF'
#!/usr/bin/env bash
{
  printf 'HOME=%s\n' "${HOME-<unset>}"
  printf 'PATH=%s\n' "${PATH-<unset>}"
  printf 'XDG_RUNTIME_DIR=%s\n' "${XDG_RUNTIME_DIR-<unset>}"
  printf 'CONTAINER_HOST=%s\n' "${CONTAINER_HOST-<unset>}"
} >"$FAKE_DOCKER_ENV_LOG"
exit 0
EOF
chmod +x "$FAKE_ENV"

# A PATH deliberately missing the system directories, and the container's HOME.
# XDG_RUNTIME_DIR is unset entirely. `ps` is chosen because it takes no lock, so
# this measures the environment and nothing else. PATH cannot be emptied outright:
# the shim's own `#!/usr/bin/env bash` needs to find bash.
env -u XDG_RUNTIME_DIR \
    HOME=/github/home \
    PATH=/nonexistent-hook-path:/bin \
    CI_RUNNER_REAL_DOCKER="$FAKE_ENV" \
    CI_RUNNER_PODMAN_LOCK="$LOCKFILE" \
    FAKE_DOCKER_ENV_LOG="$TMP/env.log" \
    timeout 3 "$SHIM" ps --all >/dev/null 2>&1

real_home="$(getent passwd "$(id -u)" | cut -d: -f6)"
if grep -qx "HOME=$real_home" "$TMP/env.log"; then
  ok "T12 the container's HOME is replaced with the invoking account's real home"
else
  bad "T12 HOME repaired (got: $(grep '^HOME=' "$TMP/env.log"))"
fi

if grep -q '^PATH=.*:/usr/bin' "$TMP/env.log"; then
  ok "T13 the system directories podman needs are present on PATH"
else
  bad "T13 PATH repaired (got: $(grep '^PATH=' "$TMP/env.log"))"
fi

if grep -qx "XDG_RUNTIME_DIR=/run/user/$(id -u)" "$TMP/env.log"; then
  ok "T14 an absent XDG_RUNTIME_DIR is defaulted to the per-user runtime dir"
else
  bad "T14 XDG_RUNTIME_DIR repaired (got: $(grep '^XDG_RUNTIME_DIR=' "$TMP/env.log"))"
fi

if grep -qx "CONTAINER_HOST=unix:///run/user/$(id -u)/podman/podman.sock" "$TMP/env.log"; then
  ok "T26 CONTAINER_HOST is derived from the repaired XDG_RUNTIME_DIR (routes through podman.service)"
else
  bad "T26 CONTAINER_HOST derived from XDG_RUNTIME_DIR (got: $(grep '^CONTAINER_HOST=' "$TMP/env.log"))"
fi

printf '\n== T27: CONTAINER_HOST is derived, never trusted from the inbound DOCKER_HOST ==\n'
# The container hooks hand this shim DOCKER_HOST pointing at whatever the job
# container sees, not necessarily the real host socket. CONTAINER_HOST must be
# computed from the (already-repaired) XDG_RUNTIME_DIR, exactly like HOME/PATH
# above — never copied from an inbound DOCKER_HOST/CONTAINER_HOST, foreign or
# otherwise.
: >"$TMP/env.log"
env -u XDG_RUNTIME_DIR \
    DOCKER_HOST="unix:///not/the/real/socket.sock" \
    CONTAINER_HOST="unix:///also/not/real.sock" \
    CI_RUNNER_REAL_DOCKER="$FAKE_ENV" \
    CI_RUNNER_PODMAN_LOCK="$LOCKFILE" \
    FAKE_DOCKER_ENV_LOG="$TMP/env.log" \
    timeout 3 "$SHIM" ps --all >/dev/null 2>&1

if grep -qx "CONTAINER_HOST=unix:///run/user/$(id -u)/podman/podman.sock" "$TMP/env.log"; then
  ok "T27 an inbound (foreign) DOCKER_HOST/CONTAINER_HOST is never trusted, only the derived value is used"
else
  bad "T27 inbound DOCKER_HOST/CONTAINER_HOST ignored (got: $(grep '^CONTAINER_HOST=' "$TMP/env.log"))"
fi

printf '\n== T15-T18: missing bind SOURCES are created on create, as dockerd would ==\n'
# podman exits 125 on a bind source that does not exist; docker creates it. The
# runner emits _work/_actions and friends before creating them, so without this
# every containerized job on a cold slot dies at "Initialize containers".
bind_root="$TMP/binds"
rm -rf "$bind_root"

run_shim create \
  -v="$bind_root/equals-form:/__w/_actions" \
  -v "$bind_root/space-form:/__w/_tool" \
  -v="$bind_root/with-mode:/github/home:ro" \
  --entrypoint tail image:tag -f /dev/null >/dev/null

if [ -d "$bind_root/equals-form" ]; then
  ok "T15 a missing bind source in -v=SRC:DST form is created"
else
  bad "T15 a missing bind source in -v=SRC:DST form is created"
fi

if [ -d "$bind_root/space-form" ]; then
  ok "T16 a missing bind source in '-v SRC:DST' form is created"
else
  bad "T16 a missing bind source in '-v SRC:DST' form is created"
fi

if [ -d "$bind_root/with-mode" ] && [ ! -e "$bind_root/with-mode:" ]; then
  ok "T17 a :ro suffix is stripped rather than becoming part of the path"
else
  bad "T17 a :ro suffix is stripped rather than becoming part of the path"
fi

# A NAMED volume has no leading slash. podman manages those itself, and turning
# one into a directory in the CWD would be a silent mess.
: >"$TMP/argv.log"
( cd "$TMP" && run_shim create -v=named-volume:/data --entrypoint tail image:tag >/dev/null )
if [ ! -e "$TMP/named-volume" ]; then
  ok "T18 a named volume is NOT turned into a directory"
else
  bad "T18 a named volume is NOT turned into a directory"
fi

printf '\n== T23-T25: a bare -e HOME at create bakes the ORIGINAL HOME, not the shim'\''s repaired one ==\n'
# `docker create` carries `-e HOME` bare (no `=value`) in the real hook command.
# The shim must NOT let its own repaired (real-host) HOME leak into what gets
# baked into the container via that flag — only THIS shim's own process (talking
# to the podman socket) should see the repaired value. A fake docker records its
# argv; T23-T24 assert `-e HOME` was rewritten to an explicit value for `create`;
# T25 asserts non-create subcommands are left untouched (no rewrite needed there
# since the real argv for them never carries a bare `-e HOME`).
: >"$TMP/argv.log"
env CI_RUNNER_REAL_DOCKER="$FAKE" \
    CI_RUNNER_PODMAN_LOCK="$LOCKFILE" \
    FAKE_DOCKER_ARGV_LOG="$TMP/argv.log" \
    HOME=/github/home \
    timeout 3 "$SHIM" create --name c1 -e HOME -e CI=true image:tag >/dev/null 2>&1

if grep -qx 'create --name c1 -e HOME=/github/home -e CI=true image:tag' "$TMP/argv.log"; then
  ok "T23 a bare -e HOME at create is rewritten to the ORIGINAL HOME, not the shim's own"
else
  bad "T23 a bare -e HOME at create is rewritten to the ORIGINAL HOME, not the shim's own (got: $(cat "$TMP/argv.log"))"
fi

# An unset original HOME leaves the flag bare — nothing to preserve, and
# rewriting to an empty value would itself be a new failure mode.
: >"$TMP/argv.log"
env -u HOME CI_RUNNER_REAL_DOCKER="$FAKE" \
    CI_RUNNER_PODMAN_LOCK="$LOCKFILE" \
    FAKE_DOCKER_ARGV_LOG="$TMP/argv.log" \
    timeout 3 "$SHIM" create --name c2 -e HOME image:tag >/dev/null 2>&1

if grep -qx 'create --name c2 -e HOME image:tag' "$TMP/argv.log"; then
  ok "T24 an unset original HOME leaves the -e HOME flag bare rather than rewriting to empty"
else
  bad "T24 an unset original HOME leaves the -e HOME flag bare rather than rewriting to empty (got: $(cat "$TMP/argv.log"))"
fi

# Non-create subcommands never carry a bare -e HOME in the real hooks, and the
# rewrite must not fire for them regardless.
: >"$TMP/argv.log"
env CI_RUNNER_REAL_DOCKER="$FAKE" \
    CI_RUNNER_PODMAN_LOCK="$LOCKFILE" \
    FAKE_DOCKER_ARGV_LOG="$TMP/argv.log" \
    HOME=/github/home \
    timeout 3 "$SHIM" exec c1 sh -c 'echo hi' >/dev/null 2>&1

if grep -qx "exec c1 sh -c echo hi" "$TMP/argv.log"; then
  ok "T25 exec argv is never rewritten (a bare -e HOME never appears there)"
else
  bad "T25 exec argv is never rewritten (got: $(cat "$TMP/argv.log"))"
fi

printf '\n== T19-T22: the rootless-netns teardown failure is tolerated, but ONLY it ==\n'
# podman removes the container and then fails killing its own network helper,
# exiting 125 on work that already succeeded. The shim translates that ONE error
# to success — and must not translate anything else, nor translate it when a
# container actually survived. A fake docker stands in for podman: FAKE_RM_ERROR
# picks the failure text, FAKE_INSPECT_EXIT decides whether the container is
# still present.
FAKE_RM="$TMP/fake-docker-rm"
cat >"$FAKE_RM" <<'EOF'
#!/usr/bin/env bash
for a in "$@"; do
  if [ "$a" = "inspect" ]; then exit "${FAKE_INSPECT_EXIT:-1}"; fi
done
printf '%s\n' "${FAKE_RM_ERROR:-}" >&2
exit 125
EOF
chmod +x "$FAKE_RM"

NETNS_ERR='Error: cleaning up container abc: removing container abc network: 1 error occurred:
	* rootless netns: kill network process: permission denied'

run_rm() {
  env CI_RUNNER_REAL_DOCKER="$FAKE_RM" \
      CI_RUNNER_PODMAN_LOCK="$LOCKFILE" \
      FAKE_RM_ERROR="$1" \
      FAKE_INSPECT_EXIT="$2" \
      timeout 5 "$SHIM" rm --force abc >/dev/null 2>&1
  printf '%s' "$?"
}

# Container gone (inspect fails) + the netns error -> tolerated.
got="$(run_rm "$NETNS_ERR" 1)"
if [ "$got" = "0" ]; then
  ok "T19 the netns teardown failure is tolerated when the container is gone"
else
  bad "T19 the netns teardown failure is tolerated when the container is gone (exit $got)"
fi

# The SAME error, but the container survived (inspect succeeds) -> NOT tolerated.
got="$(run_rm "$NETNS_ERR" 0)"
if [ "$got" = "125" ]; then
  ok "T20 it is NOT tolerated when a container survives the rm"
else
  bad "T20 it is NOT tolerated when a container survives the rm (exit $got)"
fi

# A different failure, container gone -> still NOT tolerated.
got="$(run_rm "Error: container abc is in use by another container" 1)"
if [ "$got" = "125" ]; then
  ok "T21 an unrelated rm failure is never tolerated"
else
  bad "T21 an unrelated rm failure is never tolerated (exit $got)"
fi

# A successful rm still exits 0 and still passes argv through.
: >"$TMP/argv.log"
got="$(run_shim rm --force deadbeef)"
if [ "$got" = "0" ] && grep -qx 'rm --force deadbeef' "$TMP/argv.log"; then
  ok "T22 a successful rm still exits 0 with argv passed through unchanged"
else
  bad "T22 a successful rm still exits 0 with argv passed through unchanged (exit $got)"
fi

printf '\nresult: %s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
