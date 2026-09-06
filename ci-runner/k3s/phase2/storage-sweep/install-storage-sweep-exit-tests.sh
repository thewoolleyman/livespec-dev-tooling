#!/usr/bin/env bash
# install-storage-sweep-exit-tests.sh — prove the role-awareness of
# ./install-storage-sweep.sh WITHOUT touching any host: that a `server`
# profile's plan is the command sequence and the unit ordering this installer
# had before it knew about roles, that an `agent` profile's plan applies no
# tmpfs-datastore pre-gate and orders the unit against `k3s-agent.service`, and
# that `--dry-run` executes none of it.
#
#   A. a server plan is the PRE-CHANGE command sequence, byte for byte, and its
#      role-resolved ordering is the base unit's — `Before=k3s.service`,
#      `After=` the server datastore mount, `RequiresMountsFor=` the storage
#      root;
#   B. an agent plan SKIPS the datastore pre-gate with a reason, is ordered
#      `Before=k3s-agent.service`, names neither `k3s.service` nor the server
#      datastore mount anywhere, and adds exactly the drop-in install that makes
#      that ordering true;
#   C. --dry-run executes nothing: not one host-mutating command runs;
#   D. the role is resolved from DATA and validated as data — the committed
#      profiles, an explicit `--role`, a profile with no CLUSTER_ROLE, an
#      unknown role, both inputs at once, a missing profile and an unknown
#      option are each handled or refused, naming what was wrong.
#
# HOW IT STAYS OFF THE HOST. Every case runs `--dry-run`, which by construction
# executes no command. On top of that each case prepends a scratch PATH of
# TRIPWIRES for every host-mutating tool this installer reaches for (`install`,
# `systemctl`): a run that executed a step would leave the tripwire file
# non-empty, which case C asserts it does not. The suite never runs as root and
# never needs to.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/install-storage-sweep.sh"
PROFILES="${HERE}/../../phase0-bare-metal/profiles"
SERVER_PROFILE="${PROFILES}/poweredge-xubuntu.env"
AGENT_PROFILE="${PROFILES}/gmktec-xubuntu.env"
MOUNT_UNIT_NAME="var-lib-rancher-k3s-server-db.mount"

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
for tool in install systemctl; do
  # Single-quoted on purpose: the body is the FAKE's source, expanded when the
  # fake runs, not when this suite writes it.
  printf '#!/usr/bin/env bash\nprintf "%%s %%s\\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"; exit 0\n' \
    > "${FAKEBIN}/${tool}"
  chmod +x "${FAKEBIN}/${tool}"
done

run_plan() {  # run_plan ARGS... -> stdout+stderr in REPLY_OUT, code in REPLY_RC
  REPLY_OUT="$(PATH="${FAKEBIN}:${PATH}" "$SCRIPT" "$@" 2>&1)"
  REPLY_RC=$?
}

# command_lines OUTPUT -> the indented command lines only, with this checkout's
# path stripped, which ARE the plan's command sequence.
command_lines() {
  printf '%s\n' "$1" | grep -E '^  [a-z]' | sed "s#${HERE}/##g"
}

# ordering_lines OUTPUT -> the role-resolved unit ordering directives only.
ordering_lines() { printf '%s\n' "$1" | grep -E '^  [A-Z][A-Za-z]*='; }

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
# A. The server plan is the pre-change command sequence and ordering.
#
# Both lists are deliberately LITERALS rather than anything derived from the
# artifacts under test: their whole job is to fail if a future edit changes what
# a SERVER installs or how its unit is ordered. The command sequence below is
# the pre-role-awareness script's own sequence transcribed — its pre-gate, its
# two installs, the daemon-reload, the enable, and the is-enabled verification.
# ---------------------------------------------------------------------------
IFS= read -r -d '' EXPECTED_SERVER_COMMANDS <<'EOF'
  systemctl is-enabled --quiet var-lib-rancher-k3s-server-db.mount
  install -d -m 0755 /usr/local/lib/ci-runner-k3s
  install -m 0755 sweep-runner-scratch.sh /usr/local/lib/ci-runner-k3s/sweep-runner-scratch.sh
  install -m 0644 sweep-runner-scratch.service /etc/systemd/system/sweep-runner-scratch.service
  systemctl daemon-reload
  systemctl enable sweep-runner-scratch.service
  systemctl is-enabled sweep-runner-scratch.service
EOF

IFS= read -r -d '' EXPECTED_SERVER_ORDERING <<'EOF'
  Before=k3s.service
  After=var-lib-rancher-k3s-server-db.mount
  RequiresMountsFor=/var/lib/rancher/k3s/storage
EOF

printf '== A. server profile: the pre-change command sequence and ordering ==\n'
run_plan --dry-run "$SERVER_PROFILE"
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
SERVER_ORDERING="$(ordering_lines "$SERVER_OUT")"
same "server unit ordering equals the base unit's" \
  "$EXPECTED_SERVER_ORDERING" "$SERVER_ORDERING"
if printf '%s\n' "$SERVER_OUT" | grep -q '^role:    server$'; then
  ok "server plan header states the role it read from the profile"
else
  no "server plan header states the role it read from the profile"
fi
if printf '%s\n' "$SERVER_OUT" | grep -q 'SKIPPED'; then
  no "the server plan skips nothing"
else
  ok "the server plan skips nothing"
fi

# ---------------------------------------------------------------------------
# B. The agent plan drops the datastore pre-gate and is ordered against the
#    agent's k3s unit.
# ---------------------------------------------------------------------------
IFS= read -r -d '' EXPECTED_AGENT_COMMANDS <<'EOF'
  install -d -m 0755 /usr/local/lib/ci-runner-k3s
  install -m 0755 sweep-runner-scratch.sh /usr/local/lib/ci-runner-k3s/sweep-runner-scratch.sh
  install -m 0644 sweep-runner-scratch.service /etc/systemd/system/sweep-runner-scratch.service
  install -d -m 0755 /etc/systemd/system/sweep-runner-scratch.service.d
  install -m 0644 agent-ordering.conf /etc/systemd/system/sweep-runner-scratch.service.d/10-agent-ordering.conf
  systemctl daemon-reload
  systemctl enable sweep-runner-scratch.service
  systemctl is-enabled sweep-runner-scratch.service
EOF

IFS= read -r -d '' EXPECTED_AGENT_ORDERING <<'EOF'
  Before=k3s-agent.service
  RequiresMountsFor=/var/lib/rancher/k3s/storage
EOF

printf '\n== B. agent profile: no datastore pre-gate, ordered against k3s-agent.service ==\n'
run_plan --dry-run "$AGENT_PROFILE"
if [ "$REPLY_RC" -ne 0 ]; then
  no "agent --dry-run exits 0 (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
else
  ok "agent --dry-run exits 0"
fi
AGENT_OUT="$REPLY_OUT"
AGENT_COMMANDS="$(command_lines "$AGENT_OUT")"
same "agent command sequence is the server's minus the pre-gate, plus the drop-in" \
  "$EXPECTED_AGENT_COMMANDS" "$AGENT_COMMANDS"
AGENT_ORDERING="$(ordering_lines "$AGENT_OUT")"
same "agent unit ordering names k3s-agent.service and no server datastore mount" \
  "$EXPECTED_AGENT_ORDERING" "$AGENT_ORDERING"

# The pre-gate is not merely absent from the command list: no command in the
# agent plan mentions the datastore mount at all, and the skip carries a reason.
if printf '%s\n' "$AGENT_COMMANDS" | grep -qF "$MOUNT_UNIT_NAME"; then
  no "no agent command touches the tmpfs datastore mount"
else
  ok "no agent command touches the tmpfs datastore mount"
fi
if printf '%s\n' "$AGENT_OUT" | grep -q '^  SKIPPED \[agent\]: .*datastore'; then
  ok "the skipped pre-gate carries a logged reason"
else
  no "the skipped pre-gate carries a logged reason"
fi
# `k3s.service` is a PREFIX of nothing else here, but `k3s-agent.service` is not
# a match for it, so a plain grep would be ambiguous; anchor on the directive.
if printf '%s\n' "$AGENT_ORDERING" | grep -qx '  Before=k3s.service'; then
  no "the agent unit is not ordered against the server's k3s.service"
else
  ok "the agent unit is not ordered against the server's k3s.service"
fi

# ---------------------------------------------------------------------------
# C. --dry-run executed nothing.
# ---------------------------------------------------------------------------
printf '\n== C. --dry-run executes nothing ==\n'
if [ -s "$TRIPWIRE" ]; then
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

# --role is the same choice made explicitly: it must yield the same plan the
# matching profile does, or the two inputs have drifted apart.
run_plan --dry-run --role agent
if [ "$REPLY_RC" -eq 0 ] && [ "$(command_lines "$REPLY_OUT")" = "$AGENT_COMMANDS" ]; then
  ok "--role agent yields the same plan the agent profile does"
else
  no "--role agent yields the same plan the agent profile does"
fi
run_plan --dry-run --role server
if [ "$REPLY_RC" -eq 0 ] && [ "$(command_lines "$REPLY_OUT")" = "$SERVER_COMMANDS" ]; then
  ok "--role server yields the same plan the server profile does"
else
  no "--role server yields the same plan the server profile does"
fi

# No role at all is what a bare invocation meant before this script knew about
# roles, so it must still mean `server`.
run_plan --dry-run
if [ "$REPLY_RC" -eq 0 ] && [ "$(command_lines "$REPLY_OUT")" = "$SERVER_COMMANDS" ]; then
  ok "no role given defaults to server, the pre-change behaviour"
else
  no "no role given defaults to server, the pre-change behaviour"
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

NO_ROLE="${TMPROOT}/no-role.env"
grep -v '^CLUSTER_ROLE=' "$AGENT_PROFILE" > "$NO_ROLE"
refuses "a profile with no CLUSTER_ROLE is refused, naming the key" \
  "missing required profile key 'CLUSTER_ROLE'" --dry-run "$NO_ROLE"

BAD_ROLE="${TMPROOT}/bad-role.env"
sed -e 's/^CLUSTER_ROLE=.*/CLUSTER_ROLE=worker/' "$AGENT_PROFILE" > "$BAD_ROLE"
refuses "a CLUSTER_ROLE that is neither server nor agent is refused, naming it" \
  "role must be 'server' or 'agent', got 'worker'" --dry-run "$BAD_ROLE"

refuses "an unknown --role value is refused, naming it" \
  "role must be 'server' or 'agent', got 'worker'" --dry-run --role worker

refuses "a role given twice, two ways, is refused rather than silently ranked" \
  "give either --role or a PROFILE, not both" --dry-run --role server "$AGENT_PROFILE"

refuses "a missing profile is refused, naming the path" \
  "profile not found" --dry-run "${TMPROOT}/does-not-exist.env"

refuses "an unknown option is refused with the usage line" \
  "unknown option '--sweep-now'" --dry-run --sweep-now

# ---------------------------------------------------------------------------
printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
