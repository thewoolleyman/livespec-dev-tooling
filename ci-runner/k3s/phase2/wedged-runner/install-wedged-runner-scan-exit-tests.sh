#!/usr/bin/env bash
# install-wedged-runner-scan-exit-tests.sh — prove the role-awareness AND the
# verify of ./install-wedged-runner-scan.sh WITHOUT touching any host: that a
# `server` invocation's sequence is the one this installer ran before it knew
# about roles, that an `agent` invocation REFUSES and removes any copy an
# earlier run left on the node, that `--dry-run` executes none of it, and that
# the step-4 verify FAILS on a timer that is not active instead of printing
# DONE.
#
#   A. a server plan is the PRE-CHANGE command sequence — the scan-script
#      install, the mode substitution, the timer install, the enable and the
#      verify — plus the one line this change adds, the timer's ActiveState
#      read, and it exits 0;
#   B. an agent invocation exits NON-ZERO, states the reason naming the SERVER's
#      wedged-runner timer, and, when the units are present on the node,
#      disables and removes BOTH of them (timer first) and reloads systemd; when
#      neither is present it says so and removes nothing;
#   C. --dry-run executes nothing: the only command that reaches a real binary
#      is the read-only `systemctl list-unit-files` presence probe;
#   D. the role and the mode are resolved from DATA and validated as data —
#      `--role`, the CLUSTER_ROLE environment variable, an unknown role, a role
#      given twice, a missing mode, an unknown mode, an extra positional and an
#      unknown option are each handled or refused, naming what was wrong;
#   E. THE DEFECT THIS WORK-ITEM WAS FILED FOR. A SERVER install whose timer
#      ends up anything other than `active` exits NON-ZERO and names the state
#      it found, where before this change it printed "DONE. timer armed" over a
#      timer reading `failed (Result: resources)` on gmktec-xubuntu.
#
# HOW IT STAYS OFF THE HOST. Cases A–D run `--dry-run`, which prints each
# command as a `+ ` line and executes none of them. Case E is the one case that
# runs the installer for real — it has to be, because the verify only runs on a
# real install — and it stays off the host by a different mechanism: every
# command that could mutate anything (`install`, `systemctl`, `journalctl`,
# `rm`) is a FAKE on a scratch PATH, `id` is a fake reporting root so the run
# needs no privilege, and TMPDIR points inside this suite's scratch directory,
# which is where the installer's staged unit file goes. The tripwire files
# record every fake invocation, and case C asserts the dry runs left no mutation
# in theirs. The suite never runs as root and never needs to.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/install-wedged-runner-scan.sh"
UNIT_DIR="/etc/systemd/system"
SERVICE="scan-wedged-runners.service"
TIMER="scan-wedged-runners.timer"

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
for tool in install rm journalctl; do
  # Single-quoted on purpose: the body is the FAKE's source, expanded when the
  # fake runs, not when this suite writes it.
  printf '#!/usr/bin/env bash\nprintf "%%s %%s\\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"; exit 0\n' \
    > "${FAKEBIN}/${tool}"
  chmod +x "${FAKEBIN}/${tool}"
done

# `id` is a fake so case E can drive the installer's REAL path without running
# this suite as root. It answers the one question the installer asks it — `id -u`
# — and nothing else, so it cannot make any other decision come out differently.
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "%s %s\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"' \
  'if [ "${1:-}" = -u ]; then printf "0\n"; fi' \
  'exit 0' \
  > "${FAKEBIN}/id"
chmod +x "${FAKEBIN}/id"

# The systemctl stub is the one fake the installer asks QUESTIONS of, so it is
# the one with return values:
#   list-unit-files NAME              the presence probe deciding whether an
#                                     agent has a stale copy to remove
#                                     (STUB_UNITS_PRESENT makes it answer yes);
#   show -p ActiveState --value NAME  the step-4 verify this change adds
#                                     (STUB_TIMER_STATE is the answer).
# Both branches of each decision are therefore assertable off a host that has
# neither unit and no timer at all.
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "%s %s\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"' \
  'if [ "${1:-}" = list-unit-files ] && [ -n "${STUB_UNITS_PRESENT:-}" ]; then' \
  '  printf "%s enabled enabled\n" "${@: -1}"' \
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

# command_lines OUTPUT -> the '+ ' command lines only, with this checkout's path
# stripped, which ARE the plan's command sequence.
command_lines() {
  printf '%s\n' "$1" | grep -E '^\+ ' | sed "s#${HERE}/##g"
}

# same DESCRIPTION EXPECTED ACTUAL — assert two multi-line blocks are equal and
# print the difference when they are not. The `IFS= read -r -d ''` expectations
# below keep the heredoc's trailing newline and a `$(...)` capture drops one, so
# that difference is normalized here rather than at every call site.
same() {
  local description="$1" expected="${2%$'\n'}" actual="$3"
  if [ "$expected" = "$actual" ]; then
    ok "$description"
  else
    no "$description"
    diff <(printf '%s\n' "$expected") <(printf '%s\n' "$actual") || true
  fi
}

# ---------------------------------------------------------------------------
# A. The server sequence is the pre-change one, plus the verify's read.
#
# This list is deliberately a LITERAL rather than anything derived from the
# script under test: its whole job is to fail if a future edit changes what a
# SERVER installs, in what order, or with which arguments.
# ---------------------------------------------------------------------------
IFS= read -r -d '' EXPECTED_SERVER_COMMANDS <<'EOF'
+ install -d -m 0755 /usr/local/lib/ci-runner-k3s
+ install -m 0755 scan-wedged-runners.sh /usr/local/lib/ci-runner-k3s/scan-wedged-runners.sh
+ sed s|MODE_PLACEHOLDER|--clear| scan-wedged-runners.service > <staged>/scan-wedged-runners.service
+ install -m 0644 <staged>/scan-wedged-runners.service /etc/systemd/system/scan-wedged-runners.service
+ install -m 0644 scan-wedged-runners.timer /etc/systemd/system/scan-wedged-runners.timer
+ systemctl daemon-reload
+ systemctl enable --now scan-wedged-runners.timer
+ systemctl start scan-wedged-runners.service
+ systemctl --no-pager status scan-wedged-runners.timer
+ journalctl -u scan-wedged-runners.service -n 40 --no-pager
+ systemctl show -p ActiveState --value scan-wedged-runners.timer
EOF

printf '== A. server: the pre-change command sequence, plus the verify read ==\n'
run_plan --dry-run --role server clear
if [ "$REPLY_RC" -ne 0 ]; then
  no "server --dry-run exits 0 (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
else
  ok "server --dry-run exits 0"
fi
SERVER_OUT="$REPLY_OUT"
SERVER_COMMANDS="$(command_lines "$SERVER_OUT")"
same "server command sequence equals the pre-change one plus the ActiveState read" \
  "$EXPECTED_SERVER_COMMANDS" "$SERVER_COMMANDS"

# No role at all is what a bare invocation meant before this script knew about
# roles, so it must still mean `server`.
run_plan --dry-run clear
if [ "$REPLY_RC" -eq 0 ] && [ "$(command_lines "$REPLY_OUT")" = "$SERVER_COMMANDS" ]; then
  ok "no role given defaults to server, the pre-change behaviour"
else
  no "no role given defaults to server, the pre-change behaviour"
fi

# `report` is the other half of the mode decision, and the substitution is the
# whole reason this installer exists.
run_plan --dry-run report
if printf '%s\n' "$REPLY_OUT" | grep -qF '+ sed s|MODE_PLACEHOLDER|| '; then
  ok "report mode substitutes the empty argument, clear substitutes --clear"
else
  no "report mode substitutes the empty argument, clear substitutes --clear"
fi

if printf '%s\n' "$SERVER_OUT" | grep -qi 'refus'; then
  no "the server plan refuses nothing"
else
  ok "the server plan refuses nothing"
fi

# ---------------------------------------------------------------------------
# B. An agent is refused, and any copy on the node is removed.
#
# The removal order is part of the expectation: the TIMER goes first, so the
# service cannot be triggered between the two removals, and the reload is
# followed by a `reset-failed` for each unit removed. Without that last pass the
# deleted units stay in `systemctl list-units --state=failed` as `not-found
# failed` until the host reboots (livespec-dev-tooling-oc5g).
# ---------------------------------------------------------------------------
IFS= read -r -d '' EXPECTED_AGENT_REMOVAL <<'EOF'
+ systemctl disable --now scan-wedged-runners.timer
+ rm -f /etc/systemd/system/scan-wedged-runners.timer
+ systemctl disable --now scan-wedged-runners.service
+ rm -f /etc/systemd/system/scan-wedged-runners.service
+ systemctl daemon-reload
+ systemctl reset-failed scan-wedged-runners.timer
+ systemctl reset-failed scan-wedged-runners.service
EOF

printf '\n== B. agent: refused, and a stale copy removed ==\n'
# Exported, not a command prefix: the stub is a child process and reads it from
# the environment, and `VAR=x func` would leave it set for the whole suite.
export STUB_UNITS_PRESENT=1
run_plan --dry-run --role agent
unset STUB_UNITS_PRESENT
if [ "$REPLY_RC" -ne 0 ]; then
  ok "agent invocation exits non-zero (${REPLY_RC})"
else
  no "agent invocation exits non-zero (exited 0)"
fi
AGENT_OUT="$REPLY_OUT"
same "the units present: both are disabled and removed, timer first, then a reload and a reset-failed each" \
  "$EXPECTED_AGENT_REMOVAL" "$(command_lines "$AGENT_OUT")"
case "$AGENT_OUT" in
  *"refusing to install ${SERVICE} on an agent node"*)
    ok "the refusal names the unit and the role" ;;
  *)
    no "the refusal names the unit and the role: ${AGENT_OUT}" ;;
esac
case "$AGENT_OUT" in
  *"the SERVER's own ${TIMER} already performs every five minutes"*)
    ok "the reason names the server's wedged-runner timer as what sweeps the pool" ;;
  *)
    no "the reason names the server's wedged-runner timer as what sweeps the pool" ;;
esac
case "$AGENT_OUT" in
  *'Requires=k3s.service'*'k3s-agent.service'*)
    ok "the reason names the k3s unit an agent does not run" ;;
  *)
    no "the reason names the k3s unit an agent does not run" ;;
esac
# The refusal is a refusal to INSTALL: nothing in an agent's sequence writes a
# unit file or the scan script.
if command_lines "$AGENT_OUT" | grep -qE '^\+ (install|sed) '; then
  no "no command in the agent sequence installs anything"
else
  ok "no command in the agent sequence installs anything"
fi
# An agent needs no mode, because it installs nothing: the refusal must not be
# preceded by a complaint about a missing argument.
run_plan --dry-run --role agent clear
if [ "$REPLY_RC" -ne 0 ] && printf '%s\n' "$REPLY_OUT" | grep -qF "refusing to install ${SERVICE}"; then
  ok "an agent invocation carrying a mode is refused for the ROLE, not the mode"
else
  no "an agent invocation carrying a mode is refused for the ROLE, not the mode"
fi

# The other branch of the presence probe. It is only assertable on a host that
# does NOT have the units, and this suite is meant to be runnable on the pool's
# SERVER too — where they are installed, and where the probe is right to see
# them. So it is stated as a skip there rather than as a failure.
if [ -e "${UNIT_DIR}/${SERVICE}" ] || [ -e "${UNIT_DIR}/${TIMER}" ]; then
  printf '  SKIP  neither unit present: this host has them installed, so the probe reads them\n'
else
  run_plan --dry-run --role agent
  if [ "$REPLY_RC" -ne 0 ] && [ -z "$(command_lines "$REPLY_OUT")" ]; then
    ok "neither unit present: the refusal stands and nothing is removed"
  else
    no "neither unit present: the refusal stands and nothing is removed"
  fi
  case "$REPLY_OUT" in
    *"nothing to remove"*) ok "the empty removal says so rather than staying silent" ;;
    *) no "the empty removal says so rather than staying silent" ;;
  esac
fi

# ---------------------------------------------------------------------------
# C. --dry-run executed nothing.
#
# The tripwire is not expected EMPTY: the presence probe is a read, and a read
# is performed under --dry-run on purpose so the removal sequence a dry run
# prints is the one this host actually needs. What must be absent is every
# MUTATION.
# ---------------------------------------------------------------------------
printf '\n== C. --dry-run executes nothing ==\n'
if grep -qvE '^systemctl list-unit-files ' "$TRIPWIRE"; then
  no "the dry runs executed no host-mutating command"
  cat "$TRIPWIRE"
else
  ok "the dry runs executed no host-mutating command"
fi
for role_out in "$SERVER_OUT" "$AGENT_OUT"; do
  if printf '%s\n' "$role_out" | grep -q 'NOTHING was executed'; then
    ok "the dry run says so in its own output"
  else
    no "the dry run says so in its own output"
  fi
done

# ---------------------------------------------------------------------------
# D. The role and the mode are data, and are validated as data.
# ---------------------------------------------------------------------------
printf '\n== D. role and mode resolution and validation ==\n'

# The environment variable is the same choice made by the profile's own key
# name, for an operator who exports the profile rather than passing a flag.
REPLY_OUT="$(CLUSTER_ROLE=agent PATH="${FAKEBIN}:${PATH}" "$SCRIPT" --dry-run 2>&1)"
REPLY_RC=$?
if [ "$REPLY_RC" -ne 0 ] && printf '%s\n' "$REPLY_OUT" | grep -qF "refusing to install ${SERVICE} on an agent node"; then
  ok "CLUSTER_ROLE=agent in the environment refuses exactly as --role agent does"
else
  no "CLUSTER_ROLE=agent in the environment refuses exactly as --role agent does"
fi
REPLY_OUT="$(CLUSTER_ROLE=agent PATH="${FAKEBIN}:${PATH}" "$SCRIPT" --dry-run --role server clear 2>&1)"
REPLY_RC=$?
if [ "$REPLY_RC" -eq 0 ] && [ "$(command_lines "$REPLY_OUT")" = "$SERVER_COMMANDS" ]; then
  ok "an explicit --role wins over the environment variable"
else
  no "an explicit --role wins over the environment variable"
fi

refuses() {  # refuses DESCRIPTION EXPECTED-FRAGMENT ARGS...
  local description="$1" fragment="$2"
  shift 2
  run_plan "$@"
  if [ "$REPLY_RC" -eq 0 ]; then
    no "${description} (exited 0)"
    return
  fi
  case "$REPLY_OUT" in
    *"$fragment"*) ok "$description" ;;
    *) no "${description} (message did not name it: ${REPLY_OUT})" ;;
  esac
}

refuses "an unknown --role value is refused, naming it" \
  "role must be 'server' or 'agent', got 'worker'" --dry-run --role worker clear

refuses "--role given twice is refused rather than silently ranked" \
  "--role given more than once" --dry-run --role server --role agent clear

refuses "--role with no value is refused with the usage line" \
  "--role needs a value" --dry-run --role

refuses "a server with no mode is refused, naming what is missing" \
  "no MODE given" --dry-run --role server

refuses "an unknown mode is refused, naming it" \
  "MODE must be 'report' or 'clear', got 'delete'" --dry-run delete

refuses "a second positional argument is refused rather than ignored" \
  "unexpected extra argument 'report'" --dry-run clear report

refuses "an unknown option is refused with the usage line" \
  "unknown option '--force'" --dry-run --force clear

# ---------------------------------------------------------------------------
# E. The verify ASSERTS. This is the defect livespec-dev-tooling-qcq0 was filed
#    for: on gmktec-xubuntu the timer landed `failed (Result: resources)` and
#    this installer printed DONE over it, because step 4 displayed the status
#    and never read it.
#
#    These two cases are the only ones that run the installer for real. Nothing
#    they invoke is a real binary: `install`, `systemctl`, `journalctl`, `rm`
#    and `id` are all fakes on the scratch PATH, and TMPDIR is inside this
#    suite's scratch directory, so the staged unit file never leaves it.
# ---------------------------------------------------------------------------
printf '\n== E. the verify fails on a timer that is not active ==\n'

REAL_TRIPWIRE="${TMPROOT}/tripwire-real"
: > "$REAL_TRIPWIRE"

run_for_real() {  # run_for_real TIMER-STATE ARGS...
  local state="$1"
  shift
  REPLY_OUT="$(PATH="${FAKEBIN}:${PATH}" TMPDIR="$TMPROOT" TRIPWIRE="$REAL_TRIPWIRE" \
    STUB_TIMER_STATE="$state" "$SCRIPT" "$@" 2>&1)"
  REPLY_RC=$?
}

run_for_real active clear
if [ "$REPLY_RC" -eq 0 ]; then
  ok "an active timer completes the install (exit 0)"
else
  no "an active timer completes the install (got ${REPLY_RC}): ${REPLY_OUT}"
fi
case "$REPLY_OUT" in
  *"DONE. ${TIMER} armed"*) ok "an active timer is the ONLY state that reports DONE" ;;
  *) no "an active timer is the ONLY state that reports DONE: ${REPLY_OUT}" ;;
esac

# `failed` is the exact state gmktec-xubuntu's timer reached, and `inactive` is
# the other way an install can silently not arm. Both must be fatal, and both
# must say WHICH one they found — the two mean different things to the operator.
for bad_state in failed inactive; do
  run_for_real "$bad_state" clear
  if [ "$REPLY_RC" -ne 0 ]; then
    ok "a '${bad_state}' timer exits non-zero (${REPLY_RC}) instead of printing DONE"
  else
    no "a '${bad_state}' timer exits non-zero instead of printing DONE (exited 0)"
  fi
  case "$REPLY_OUT" in
    *"${TIMER} is '${bad_state}', expected 'active'"*)
      ok "the failure names the timer and the state it found ('${bad_state}')" ;;
    *)
      no "the failure names the timer and the state it found ('${bad_state}'): ${REPLY_OUT}" ;;
  esac
  case "$REPLY_OUT" in
    *"DONE. ${TIMER} armed"*) no "a '${bad_state}' timer must not also print DONE" ;;
    *) ok "a '${bad_state}' timer prints no DONE line" ;;
  esac
done

# The real runs stayed inside the fakes: nothing they invoked was a real binary,
# so every write this installer makes outside a temporary directory is accounted
# for by a tripwire line rather than by a file on this host.
if [ -s "$REAL_TRIPWIRE" ] && ! grep -qvE '^(install|systemctl|journalctl|rm|id) ' "$REAL_TRIPWIRE"; then
  ok "every command the real runs executed was a fake, and every fake was recorded"
else
  no "every command the real runs executed was a fake, and every fake was recorded"
  cat "$REAL_TRIPWIRE"
fi
if [ -e "${UNIT_DIR}/${SERVICE}.staged" ]; then
  no "the real runs staged nothing into ${UNIT_DIR}"
else
  ok "the real runs staged nothing into ${UNIT_DIR}"
fi

# ---------------------------------------------------------------------------
printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
