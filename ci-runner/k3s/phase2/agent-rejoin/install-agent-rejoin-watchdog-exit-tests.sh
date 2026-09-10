#!/usr/bin/env bash
# install-agent-rejoin-watchdog-exit-tests.sh — prove the role-awareness AND the
# verify of ./install-agent-rejoin-watchdog.sh WITHOUT touching any host: that an
# `agent` invocation installs the watchdog and its timer in a fixed sequence and
# asserts the timer is active, that a `server` invocation REFUSES and removes any
# copy an earlier run left, that `--dry-run` executes none of it, and that the
# verify FAILS on a timer that is not active instead of printing DONE.
#
#   A. an agent plan is the watchdog-script install, the two unit installs, the
#      enable, the status display and the timer's ActiveState read, and it
#      exits 0;
#   B. a server invocation exits NON-ZERO, states the reason (the server never
#      wedges), and, when the units are present, disables and removes BOTH of
#      them (timer first) then reloads and reset-fails each; when neither is
#      present it says so and removes nothing;
#   C. --dry-run executes nothing: the only command that reaches a real binary
#      is the read-only `systemctl list-unit-files` presence probe;
#   D. the role is resolved from DATA and validated as data — `--role`, the
#      CLUSTER_ROLE environment variable, an unknown role, a role given twice,
#      an extra positional and an unknown option are each handled or refused;
#   E. an AGENT install whose timer ends up anything other than `active` exits
#      NON-ZERO and names the state it found, rather than printing DONE over it.
#
# HOW IT STAYS OFF THE HOST. Cases A–D run `--dry-run`, which prints each command
# as a `+ ` line and executes none. Case E runs the installer for real — it has
# to, because the verify only runs on a real install — and stays off the host by
# a different mechanism: every mutating command (`install`, `systemctl`, `rm`) is
# a FAKE on a scratch PATH, `id` is a fake reporting root so the run needs no
# privilege, and TMPDIR points inside this suite's scratch dir. The tripwire
# records every fake invocation; case C asserts the dry runs left it empty.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/install-agent-rejoin-watchdog.sh"
SERVICE="agent-rejoin-watchdog.service"
TIMER="agent-rejoin-watchdog.timer"

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

TRIPWIRE="${TMPROOT}/tripwire"
: > "$TRIPWIRE"
export TRIPWIRE

FAKEBIN="${TMPROOT}/fakebin"
mkdir -p "$FAKEBIN"
for tool in install rm; do
  printf '#!/usr/bin/env bash\nprintf "%%s %%s\\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"; exit 0\n' \
    > "${FAKEBIN}/${tool}"
  chmod +x "${FAKEBIN}/${tool}"
done

# `id` is a fake so case E can drive the installer's REAL agent path without
# running this suite as root. It answers only `id -u` with 0.
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "%s %s\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"' \
  'if [ "${1:-}" = -u ]; then printf "0\n"; fi' \
  'exit 0' \
  > "${FAKEBIN}/id"
chmod +x "${FAKEBIN}/id"

# The systemctl stub is the one fake the installer asks QUESTIONS of:
#   list-unit-files NAME              the presence probe (STUB_UNITS_PRESENT
#                                     makes it answer yes);
#   is-failed NAME                    the residual probe for a unit the presence
#                                     probe did NOT report (STUB_UNITS_FAILED is
#                                     the space-separated list it answers
#                                     `failed` for; every other name draws
#                                     `inactive` and a non-zero exit);
#   show -p ActiveState --value NAME  the step-4 verify (STUB_TIMER_STATE is the
#                                     answer).
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "%s %s\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"' \
  'if [ "${1:-}" = list-unit-files ] && [ -n "${STUB_UNITS_PRESENT:-}" ]; then' \
  '  printf "%s enabled enabled\n" "${@: -1}"' \
  'fi' \
  'if [ "${1:-}" = is-failed ]; then' \
  '  for stub_unit in ${STUB_UNITS_FAILED:-}; do' \
  '    if [ "$stub_unit" = "${@: -1}" ]; then printf "failed\n"; exit 0; fi' \
  '  done' \
  '  printf "inactive\n"' \
  '  exit 1' \
  'fi' \
  'if [ "${1:-}" = show ] && [ -n "${STUB_TIMER_STATE:-}" ]; then' \
  '  printf "%s\n" "${STUB_TIMER_STATE}"' \
  'fi' \
  'exit 0' \
  > "${FAKEBIN}/systemctl"
chmod +x "${FAKEBIN}/systemctl"

run_plan() {  # run_plan ARGS... -> stdout+stderr in REPLY_OUT, code in REPLY_RC
  REPLY_OUT="$(PATH="${FAKEBIN}:${PATH}" TMPDIR="$TMPROOT" "$SCRIPT" "$@" 2>&1)"
  REPLY_RC=$?
}

command_lines() {  # the '+ ' command lines only, with this checkout's path stripped
  printf '%s\n' "$1" | grep -E '^\+ ' | sed "s#${HERE}/##g"
}

same() {  # same DESCRIPTION EXPECTED ACTUAL
  local description="$1" expected="${2%$'\n'}" actual="$3"
  if [ "$expected" = "$actual" ]; then
    ok "$description"
  else
    no "$description"
    diff <(printf '%s\n' "$expected") <(printf '%s\n' "$actual") || true
  fi
}

# ---------------------------------------------------------------------------
# A. The agent sequence: install the script and both units, enable, verify.
# A LITERAL, so a future edit that changes what an agent installs, in what order,
# or with which arguments, fails here.
# ---------------------------------------------------------------------------
IFS= read -r -d '' EXPECTED_AGENT_COMMANDS <<'EOF'
+ install -d -m 0755 /usr/local/lib/ci-runner-k3s
+ install -m 0755 agent-rejoin-watchdog.sh /usr/local/lib/ci-runner-k3s/agent-rejoin-watchdog.sh
+ install -m 0644 agent-rejoin-watchdog.service /etc/systemd/system/agent-rejoin-watchdog.service
+ install -m 0644 agent-rejoin-watchdog.timer /etc/systemd/system/agent-rejoin-watchdog.timer
+ systemctl daemon-reload
+ systemctl enable --now agent-rejoin-watchdog.timer
+ systemctl --no-pager status agent-rejoin-watchdog.timer
+ systemctl show -p ActiveState --value agent-rejoin-watchdog.timer
EOF

printf '== A. agent: install the watchdog and arm the timer ==\n'
run_plan --dry-run --role agent
if [ "$REPLY_RC" -ne 0 ]; then
  no "agent --dry-run exits 0 (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
else
  ok "agent --dry-run exits 0"
fi
AGENT_OUT="$REPLY_OUT"
AGENT_COMMANDS="$(command_lines "$AGENT_OUT")"
same "agent command sequence installs the script, both units, enables and verifies" \
  "$EXPECTED_AGENT_COMMANDS" "$AGENT_COMMANDS"
if printf '%s\n' "$AGENT_OUT" | grep -qi 'refus'; then
  no "the agent plan refuses nothing"
else
  ok "the agent plan refuses nothing"
fi

# ---------------------------------------------------------------------------
# B. A server is refused, and any copy on the node is removed (timer first, then
# a reload and a reset-failed each).
# ---------------------------------------------------------------------------
IFS= read -r -d '' EXPECTED_SERVER_REMOVAL <<'EOF'
+ systemctl disable --now agent-rejoin-watchdog.timer
+ rm -f /etc/systemd/system/agent-rejoin-watchdog.timer
+ systemctl disable --now agent-rejoin-watchdog.service
+ rm -f /etc/systemd/system/agent-rejoin-watchdog.service
+ systemctl daemon-reload
+ systemctl reset-failed agent-rejoin-watchdog.timer
+ systemctl reset-failed agent-rejoin-watchdog.service
EOF

printf '\n== B. server: refused, and a stale copy removed ==\n'
export STUB_UNITS_PRESENT=1
run_plan --dry-run --role server
unset STUB_UNITS_PRESENT
if [ "$REPLY_RC" -ne 0 ]; then
  ok "server invocation exits non-zero (${REPLY_RC})"
else
  no "server invocation exits non-zero (exited 0)"
fi
SERVER_OUT="$REPLY_OUT"
same "the units present: both are disabled and removed, timer first, then a reload and a reset-failed each" \
  "$EXPECTED_SERVER_REMOVAL" "$(command_lines "$SERVER_OUT")"
case "$SERVER_OUT" in
  *"refusing to install ${SERVICE} on a server node"*)
    ok "the refusal names the unit and the role" ;;
  *)
    no "the refusal names the unit and the role: ${SERVER_OUT}" ;;
esac
case "$SERVER_OUT" in
  *"never loses its own registration"*)
    ok "the refusal reason explains why a server never wedges" ;;
  *)
    no "the refusal reason explains why a server never wedges" ;;
esac

# A bare invocation (no role) defaults to server and so refuses — the safe
# default for an agent-only installer.
run_plan --dry-run
if [ "$REPLY_RC" -ne 0 ] && printf '%s\n' "$REPLY_OUT" | grep -qi 'refus'; then
  ok "no role given defaults to server, which refuses"
else
  no "no role given defaults to server, which refuses"
fi

# When neither unit is present, the server path removes nothing and says so.
run_plan --dry-run --role server
case "$REPLY_OUT" in
  *"nothing to remove"*) ok "a clean server removes nothing and says so" ;;
  *) no "a clean server removes nothing and says so" ;;
esac

# ---------------------------------------------------------------------------
# C. --dry-run executes nothing but the read-only presence probe.
# ---------------------------------------------------------------------------
printf '\n== C. --dry-run mutates nothing ==\n'
: > "$TRIPWIRE"
run_plan --dry-run --role agent
run_plan --dry-run --role server
TRIPWIRE_LINES="$(grep -vE '^systemctl (list-unit-files|is-failed)' "$TRIPWIRE" || true)"
if [ -z "$TRIPWIRE_LINES" ]; then
  ok "the only binaries a dry run reaches are the read-only systemctl probes"
else
  no "a dry run reached a mutating binary:"
  printf '%s\n' "$TRIPWIRE_LINES"
fi

# ---------------------------------------------------------------------------
# D. Role is resolved from data and validated as data.
# ---------------------------------------------------------------------------
printf '\n== D. role parsing ==\n'
run_plan --dry-run --role agent
[ "$REPLY_RC" -eq 0 ] && ok "--role agent is accepted" || no "--role agent is accepted"

REPLY_OUT="$(PATH="${FAKEBIN}:${PATH}" TMPDIR="$TMPROOT" CLUSTER_ROLE=agent "$SCRIPT" --dry-run 2>&1)"; REPLY_RC=$?
if [ "$REPLY_RC" -eq 0 ] && printf '%s\n' "$REPLY_OUT" | grep -qF 'systemctl enable --now agent-rejoin-watchdog.timer'; then
  ok "CLUSTER_ROLE=agent is honoured when --role is absent"
else
  no "CLUSTER_ROLE=agent is honoured when --role is absent"
fi

run_plan --dry-run --role bogus
if [ "$REPLY_RC" -ne 0 ] && printf '%s\n' "$REPLY_OUT" | grep -qF "got 'bogus'"; then
  ok "an unknown role is refused, naming it"
else
  no "an unknown role is refused, naming it"
fi

run_plan --dry-run --role agent --role server
if [ "$REPLY_RC" -ne 0 ] && printf '%s\n' "$REPLY_OUT" | grep -qi 'given more than once'; then
  ok "a role given twice is refused"
else
  no "a role given twice is refused"
fi

run_plan --dry-run --role agent extra
if [ "$REPLY_RC" -ne 0 ] && printf '%s\n' "$REPLY_OUT" | grep -qi 'unexpected extra argument'; then
  ok "an extra positional is refused"
else
  no "an extra positional is refused"
fi

run_plan --dry-run --frobnicate
if [ "$REPLY_RC" -ne 0 ] && printf '%s\n' "$REPLY_OUT" | grep -qi "unknown option"; then
  ok "an unknown option is refused"
else
  no "an unknown option is refused"
fi

# ---------------------------------------------------------------------------
# E. The agent verify FAILS on a timer that is not active.
# ---------------------------------------------------------------------------
printf '\n== E. the verify fails on a timer that is not active ==\n'
export STUB_TIMER_STATE=failed
run_plan --role agent
unset STUB_TIMER_STATE
if [ "$REPLY_RC" -ne 0 ] && printf '%s\n' "$REPLY_OUT" | grep -qF "${TIMER} is 'failed'"; then
  ok "a real agent install whose timer is 'failed' exits non-zero, naming the state"
else
  no "a real agent install whose timer is 'failed' exits non-zero, naming the state: rc=${REPLY_RC}"
fi

export STUB_TIMER_STATE=active
run_plan --role agent
unset STUB_TIMER_STATE
if [ "$REPLY_RC" -eq 0 ] && printf '%s\n' "$REPLY_OUT" | grep -qF 'DONE.'; then
  ok "a real agent install whose timer is 'active' exits 0 and reports DONE"
else
  no "a real agent install whose timer is 'active' exits 0 and reports DONE: rc=${REPLY_RC}"
fi

# ---------------------------------------------------------------------------
printf '\n== summary: %d passed, %d failed ==\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
