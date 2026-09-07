#!/usr/bin/env bash
# install-arc-log-archive-exit-tests.sh — prove the role-awareness of
# ./install-arc-log-archive.sh WITHOUT touching any host: that a `server`
# invocation's sequence is the one this installer ran before it knew about
# roles, that an `agent` invocation REFUSES and removes any copy an earlier run
# left on the node, and that `--dry-run` executes none of it.
#
#   A. a server plan is the PRE-CHANGE command sequence — the archive-script
#      install, the two data directories, the two unit installs, the reload, the
#      enable and the verify pass — and it exits 0;
#   B. an agent invocation exits NON-ZERO, states the reason naming the SERVER's
#      archive timer and the admin kubeconfig, and, when the units are present
#      on the node, disables and removes BOTH of them (timer first) and reloads
#      systemd; when neither is present it says so and removes nothing. It
#      removes NEITHER data directory: those hold archived logs, and a removal
#      path that deleted them would be destroying evidence to tidy up after an
#      install;
#   C. --dry-run executes nothing: the only command that reaches a real binary
#      is the read-only `systemctl list-unit-files` presence probe;
#   D. the role is resolved from DATA and validated as data — `--role`, the
#      CLUSTER_ROLE environment variable, an unknown role, a role given twice, a
#      stray positional and an unknown option are each handled or refused,
#      naming what was wrong.
#
# HOW IT STAYS OFF THE HOST. Every case runs `--dry-run`, which prints each
# command as a `+ ` line and executes none of them. On top of that each case
# prepends a scratch PATH of TRIPWIRES for every host-mutating tool this
# installer reaches for (`install`, `systemctl`, `rm`, `journalctl`): a run that
# executed a step would leave a mutating line in the tripwire file, which case C
# asserts it does not. The suite never runs as root and never needs to.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/install-arc-log-archive.sh"
UNIT_DIR="/etc/systemd/system"
SERVICE="archive-arc-logs.service"
TIMER="archive-arc-logs.timer"

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

# The systemctl stub is the one fake with RETURN VALUES, because the installer
# asks it two questions: `list-unit-files NAME` is the presence probe deciding
# whether an agent has a stale copy to remove, and `is-failed NAME` is the
# residual probe asked of a unit the first one did NOT report. STUB_UNITS_PRESENT
# makes the first answer yes; STUB_UNITS_FAILED is the SPACE-SEPARATED list of
# names the second answers `failed` for, every other name drawing `inactive` and
# a non-zero exit as the real systemctl does. So both branches of both decisions
# are assertable off a host that has neither unit.
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
  'exit 0' \
  > "${FAKEBIN}/systemctl"
chmod +x "${FAKEBIN}/systemctl"

run_plan() {  # run_plan ARGS... -> stdout+stderr in REPLY_OUT, code in REPLY_RC
  REPLY_OUT="$(PATH="${FAKEBIN}:${PATH}" "$SCRIPT" "$@" 2>&1)"
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
# A. The server sequence is the pre-change one.
#
# This list is deliberately a LITERAL rather than anything derived from the
# script under test: its whole job is to fail if a future edit changes what a
# SERVER installs, in what order, or with which arguments.
# ---------------------------------------------------------------------------
IFS= read -r -d '' EXPECTED_SERVER_COMMANDS <<'EOF'
+ install -d -m 0755 /usr/local/lib/ci-runner-k3s
+ install -m 0755 archive-arc-logs.sh /usr/local/lib/ci-runner-k3s/archive-arc-logs.sh
+ install -d -m 0750 /var/log/arc-archive
+ install -d -m 0750 /var/lib/ci-runner-k3s/arc-log-archive
+ install -m 0644 archive-arc-logs.service /etc/systemd/system/archive-arc-logs.service
+ install -m 0644 archive-arc-logs.timer /etc/systemd/system/archive-arc-logs.timer
+ systemctl daemon-reload
+ systemctl enable --now archive-arc-logs.timer
+ systemctl start archive-arc-logs.service
+ systemctl --no-pager status archive-arc-logs.timer
+ journalctl -u archive-arc-logs.service -n 30 --no-pager
EOF

printf '== A. server: the pre-change command sequence ==\n'
run_plan --dry-run --role server
if [ "$REPLY_RC" -ne 0 ]; then
  no "server --dry-run exits 0 (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
else
  ok "server --dry-run exits 0"
fi
SERVER_OUT="$REPLY_OUT"
SERVER_COMMANDS="$(command_lines "$SERVER_OUT")"
same "server command sequence equals the pre-change one" \
  "$EXPECTED_SERVER_COMMANDS" "$SERVER_COMMANDS"

# No role at all is what a bare invocation meant before this script knew about
# roles, so it must still mean `server`.
run_plan --dry-run
if [ "$REPLY_RC" -eq 0 ] && [ "$(command_lines "$REPLY_OUT")" = "$SERVER_COMMANDS" ]; then
  ok "no role given defaults to server, the pre-change behaviour"
else
  no "no role given defaults to server, the pre-change behaviour"
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
+ systemctl disable --now archive-arc-logs.timer
+ rm -f /etc/systemd/system/archive-arc-logs.timer
+ systemctl disable --now archive-arc-logs.service
+ rm -f /etc/systemd/system/archive-arc-logs.service
+ systemctl daemon-reload
+ systemctl reset-failed archive-arc-logs.timer
+ systemctl reset-failed archive-arc-logs.service
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
  *"The SERVER's own ${TIMER} already archives them for every node"*)
    ok "the reason names the server's archive timer as what covers the pool" ;;
  *)
    no "the reason names the server's archive timer as what covers the pool" ;;
esac
case "$AGENT_OUT" in
  *'KUBECONFIG=/etc/rancher/k3s/k3s.yaml'*)
    ok "the reason names the admin kubeconfig an agent does not hold" ;;
  *)
    no "the reason names the admin kubeconfig an agent does not hold" ;;
esac
# The one way this installer's refusal differs from its two scan siblings': the
# ARCHIVED LOGS stay. A removal path that deleted them would be destroying
# evidence to tidy up after an install.
if printf '%s\n' "$AGENT_OUT" | grep -qE '^\+ rm .*(/var/log/arc-archive|/var/lib/ci-runner-k3s)'; then
  no "no command in the agent sequence removes an archive or state directory"
else
  ok "no command in the agent sequence removes an archive or state directory"
fi
# The refusal is a refusal to INSTALL: nothing in an agent's sequence writes a
# unit file, the archive script, or either data directory.
if command_lines "$AGENT_OUT" | grep -qE '^\+ install '; then
  no "no command in the agent sequence installs anything"
else
  ok "no command in the agent sequence installs anything"
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

  # The RESIDUAL case, which is the same not-present branch with systemd still
  # reporting the units failed: an EARLIER run deleted the files and left the
  # failed state behind, so this run has nothing to remove and one thing to
  # clear. gmktec-xubuntu was found exactly there on 2026-09-07
  # (livespec-dev-tooling-ssbg). Nothing is disabled, unlinked or reloaded --
  # there is no change on the node for a reload to publish.
  export STUB_UNITS_FAILED="${TIMER} ${SERVICE}"
  run_plan --dry-run --role agent
  unset STUB_UNITS_FAILED
  same "not installed but still failed: each unit is cleared, and only cleared" \
    "$(printf '+ systemctl reset-failed %s\n+ systemctl reset-failed %s\n' "$TIMER" "$SERVICE")" \
    "$(command_lines "$REPLY_OUT")"
  case "$REPLY_OUT" in
    *"nothing to remove"*) no "a run that cleared something does not also say there was nothing to do" ;;
    *) ok "a run that cleared something does not also say there was nothing to do" ;;
  esac
fi

# ---------------------------------------------------------------------------
# C. --dry-run executed nothing.
#
# The tripwire is not expected EMPTY: the presence probe and the is-failed probe
# are READS, and a read is performed under --dry-run on purpose so the removal
# sequence a dry run prints is the one this host actually needs. What must be
# absent is every MUTATION.
# ---------------------------------------------------------------------------
printf '\n== C. --dry-run executes nothing ==\n'
if grep -qvE '^systemctl (list-unit-files|is-failed) ' "$TRIPWIRE"; then
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
# D. The role is data, and is validated as data.
# ---------------------------------------------------------------------------
printf '\n== D. role resolution and validation ==\n'

# The environment variable is the same choice made by the profile's own key
# name, for an operator who exports the profile rather than passing a flag.
REPLY_OUT="$(CLUSTER_ROLE=agent PATH="${FAKEBIN}:${PATH}" "$SCRIPT" --dry-run 2>&1)"
REPLY_RC=$?
if [ "$REPLY_RC" -ne 0 ] && printf '%s\n' "$REPLY_OUT" | grep -qF "refusing to install ${SERVICE} on an agent node"; then
  ok "CLUSTER_ROLE=agent in the environment refuses exactly as --role agent does"
else
  no "CLUSTER_ROLE=agent in the environment refuses exactly as --role agent does"
fi
REPLY_OUT="$(CLUSTER_ROLE=agent PATH="${FAKEBIN}:${PATH}" "$SCRIPT" --dry-run --role server 2>&1)"
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
  "role must be 'server' or 'agent', got 'worker'" --dry-run --role worker

refuses "--role given twice is refused rather than silently ranked" \
  "--role given more than once" --dry-run --role server --role agent

refuses "--role with no value is refused with the usage line" \
  "--role needs a value" --dry-run --role

# This installer takes NO positional argument — the report/clear mode its
# wedged-runner sibling requires is a decision an append-only archive does not
# have — so a stray one is a mistake rather than a mode.
refuses "a positional argument is refused rather than ignored" \
  "unexpected argument 'clear'" --dry-run clear

refuses "an unknown option is refused with the usage line" \
  "unknown option '--force'" --dry-run --force

# ---------------------------------------------------------------------------
printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
