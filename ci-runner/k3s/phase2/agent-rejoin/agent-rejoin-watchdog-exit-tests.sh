#!/usr/bin/env bash
# agent-rejoin-watchdog-exit-tests.sh — prove the FOUR GATES of
# ./agent-rejoin-watchdog.sh WITHOUT touching any host: that it restarts the
# k3s-agent if and only if the process is up, the server is reachable, the wedge
# signature is present enough times in the window, and no restart is inside the
# cooldown.
#
# HOW IT STAYS OFF THE HOST. The three commands that reach the outside world are
# FAKES on a scratch PATH: `systemctl` (answers is-active from STUB_AGENT_ACTIVE
# and records a restart to the tripwire), `timeout` (the TCP-reachability probe,
# answers from STUB_SERVER_REACHABLE), and `journalctl` (prints STUB_JOURNAL so
# the real `grep -c` counts the signature). Everything else is real against files
# in this suite's scratch dir: the k3s config, the node-password and the cooldown
# stamp are real paths under TMPROOT, so real `date`/`stat`/`rm`/`grep` exercise
# the true logic. "Did it restart?" is read as a `systemctl restart` line in the
# tripwire.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/agent-rejoin-watchdog.sh"
NODE_NAME="testnode"
NEEDLE="node \"${NODE_NAME}\" not found"

pass=0; fail=0
ok() { printf '  PASS  %s\n' "$1"; pass=$((pass + 1)); }
no() { printf '  FAIL  %s\n' "$1"; fail=$((fail + 1)); }

TMPROOT="$(mktemp -d)"
case "$TMPROOT" in
  /tmp/*|/var/tmp/*) ;;
  *) echo "FATAL: mktemp -d returned an unexpected path '${TMPROOT}'" >&2; exit 1 ;;
esac
cleanup() { rm -rf "$TMPROOT"; }
trap cleanup EXIT

FAKEBIN="${TMPROOT}/fakebin"
mkdir -p "$FAKEBIN"
TRIPWIRE="${TMPROOT}/tripwire"
export TRIPWIRE

# systemctl: is-active answers from STUB_AGENT_ACTIVE; restart records; anything
# else is a silent success (the watchdog issues no other systemctl call).
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'if [ "${1:-}" = is-active ]; then' \
  '  [ -n "${STUB_AGENT_ACTIVE:-}" ] && exit 0 || exit 3' \
  'fi' \
  'if [ "${1:-}" = restart ]; then' \
  '  printf "systemctl restart %s\n" "${2:-}" >> "$TRIPWIRE"; exit 0' \
  'fi' \
  'exit 0' \
  > "${FAKEBIN}/systemctl"
chmod +x "${FAKEBIN}/systemctl"

# timeout: the reachability probe. Exit 0 (reachable) from STUB_SERVER_REACHABLE,
# else non-zero (unreachable). It never runs the bash it was handed.
printf '%s\n' \
  '#!/usr/bin/env bash' \
  '[ -n "${STUB_SERVER_REACHABLE:-}" ] && exit 0 || exit 1' \
  > "${FAKEBIN}/timeout"
chmod +x "${FAKEBIN}/timeout"

# journalctl: print STUB_JOURNAL verbatim so the watchdog's real `grep -c`
# counts the signature lines.
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "%s" "${STUB_JOURNAL:-}"' \
  > "${FAKEBIN}/journalctl"
chmod +x "${FAKEBIN}/journalctl"

CONFIG="${TMPROOT}/config.yaml"
printf 'server: https://192.168.1.200:6443\n' > "$CONFIG"
NODE_PASSWORD="${TMPROOT}/node-password"
STAMP="${TMPROOT}/stamp"

# journal_with N -> N copies of the wedge signature (plus benign noise).
journal_with() {
  local n="$1" out="" i
  for ((i = 0; i < n; i++)); do out+="Sep 10 boot k3s[1]: ${NEEDLE}"$'\n'; done
  out+="Sep 10 boot k3s[1]: some other line"$'\n'
  printf '%s' "$out"
}

# run_watchdog -> reset the tripwire first, so each case reads only its own
# restart, then run the watchdog under the fakes. The verdict is the tripwire,
# not the exit code, so the code is intentionally not captured.
run_watchdog() {
  : > "$TRIPWIRE"
  PATH="${FAKEBIN}:${PATH}" \
    REJOIN_NODE_NAME="$NODE_NAME" \
    REJOIN_K3S_CONFIG="$CONFIG" \
    REJOIN_NODE_PASSWORD="$NODE_PASSWORD" \
    REJOIN_STAMP="$STAMP" \
    REJOIN_WINDOW_SEC=180 REJOIN_MIN_HITS=5 REJOIN_RATE_LIMIT_SEC=300 \
    "$SCRIPT" >/dev/null 2>&1 || true
}
restarted() { grep -q '^systemctl restart' "$TRIPWIRE"; }

printf '== agent-rejoin-watchdog four-gate logic ==\n'

# The one case that must act: all four gates hold.
rm -f "$STAMP"
export STUB_AGENT_ACTIVE=1 STUB_SERVER_REACHABLE=1
STUB_JOURNAL="$(journal_with 6)" run_watchdog
if restarted; then ok "wedged (active, reachable, 6 hits, no cooldown) -> restarts the agent"; else no "wedged case did not restart"; fi
[ ! -e "$NODE_PASSWORD" ] || no "the wedged case should have removed the node-password"
[ -f "$STAMP" ] && ok "the wedged case wrote the cooldown stamp" || no "the wedged case wrote no stamp"

# Gate 1: agent down -> Restart=always owns it, this watchdog does not act.
rm -f "$STAMP"
unset STUB_AGENT_ACTIVE; export STUB_SERVER_REACHABLE=1
STUB_JOURNAL="$(journal_with 6)" run_watchdog
restarted && no "agent-down should NOT restart" || ok "agent down -> no restart (Restart=always owns an exited process)"

# Gate 2: server unreachable -> nothing to rejoin to, wait it out.
rm -f "$STAMP"
export STUB_AGENT_ACTIVE=1; unset STUB_SERVER_REACHABLE
STUB_JOURNAL="$(journal_with 6)" run_watchdog
restarted && no "unreachable server should NOT restart" || ok "server unreachable -> no restart"

# Gate 3: too few signature hits -> not the wedge.
rm -f "$STAMP"
export STUB_AGENT_ACTIVE=1 STUB_SERVER_REACHABLE=1
STUB_JOURNAL="$(journal_with 2)" run_watchdog
restarted && no "2 hits (< 5) should NOT restart" || ok "below the hit threshold -> no restart"

# Gate 3: a healthy agent logs the signature zero times.
rm -f "$STAMP"
STUB_JOURNAL="Sep 10 boot k3s[1]: registered node testnode"$'\n' run_watchdog
restarted && no "healthy journal should NOT restart" || ok "healthy (no signature) -> no restart"

# Gate 4: a restart inside the cooldown holds off a second one.
export STUB_AGENT_ACTIVE=1 STUB_SERVER_REACHABLE=1
: > "$STAMP"; touch -d '30 seconds ago' "$STAMP"
STUB_JOURNAL="$(journal_with 6)" run_watchdog
restarted && no "a restart 30s ago (< 300s cooldown) should NOT restart again" || ok "within the cooldown -> holds off a second restart"

# Gate 4: past the cooldown, the same wedge acts again.
: > "$STAMP"; touch -d '10 minutes ago' "$STAMP"
STUB_JOURNAL="$(journal_with 6)" run_watchdog
restarted && ok "past the cooldown -> restarts again" || no "past the cooldown it should restart again"

# A config with no server line is not a joined agent -> nothing to do.
rm -f "$STAMP"
printf 'token-file: /x\n' > "${TMPROOT}/noserver.yaml"
: > "$TRIPWIRE"
PATH="${FAKEBIN}:${PATH}" REJOIN_NODE_NAME="$NODE_NAME" REJOIN_K3S_CONFIG="${TMPROOT}/noserver.yaml" \
  REJOIN_NODE_PASSWORD="$NODE_PASSWORD" REJOIN_STAMP="$STAMP" \
  "$SCRIPT" >/dev/null 2>&1
restarted && no "a config with no server line should NOT restart" || ok "no server line in config -> no restart"

printf '\n== summary: %d passed, %d failed ==\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
