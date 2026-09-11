#!/usr/bin/env bash
# install-reapply-unit-exit-tests.sh — prove the profile-driven, per-node
# behaviour of ./install-reapply-unit.sh WITHOUT touching any host: that a
# SERVER profile and an AGENT profile each produce the right install sequence
# (ordered against that role's own k3s unit, naming that node's profile), that
# both roles INSTALL rather than one refusing, that `--dry-run` executes nothing,
# and that the profile is validated as data.
#
#   A. a SERVER profile installs: the patch script, a copy of the profile, the
#      unit with `k3s.service` substituted in and the profile path in its
#      ExecStart, the timer, the enables, and a verify that reads back the
#      server's own node BY NAME — and it exits 0;
#   B. an AGENT profile installs the SAME shape with `k3s-agent.service` and the
#      agent's own node/profile — it INSTALLS (the pre-R5 refusal is gone) and
#      exits 0;
#   C. --dry-run executes nothing: the tripwire for every host-mutating tool this
#      installer reaches (`install`, `systemctl`, `rm`, `kubectl`) stays empty;
#   D. the profile is validated as data — a missing profile, a nonexistent path,
#      an extra argument, an unknown option, a non-numeric ADMISSION_CAPACITY_C,
#      an unknown CLUSTER_ROLE and an agent with an empty CHURN_KUBECONFIG_FILE
#      are each refused, naming what was wrong.
#
# HOW IT STAYS OFF THE HOST. Every case runs `--dry-run`, which prints each
# command as a `+ ` line and executes none of them, on top of a scratch PATH of
# TRIPWIRES for every host-mutating tool. The suite never runs as root and never
# needs to.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/install-reapply-unit.sh"
PROFILES="${HERE}/../../phase0-bare-metal/profiles"

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
for tool in install rm kubectl systemctl; do
  # Single-quoted on purpose: the body is the FAKE's source, expanded when the
  # fake runs, not when this suite writes it.
  printf '#!/usr/bin/env bash\nprintf "%%s %%s\\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"; exit 0\n' \
    > "${FAKEBIN}/${tool}"
  chmod +x "${FAKEBIN}/${tool}"
done

# The committed profiles copied into scratch under predictable names, so the
# printed command sequence has stable paths to assert. The SERVER is poweredge,
# the AGENT is gmktec; copying them keeps the assertions about the install SHAPE
# rather than about a capacity number that may be re-derived.
SERVER_PROFILE="${TMPROOT}/server.env"
AGENT_PROFILE="${TMPROOT}/agent.env"
cp "${PROFILES}/poweredge-xubuntu.env" "$SERVER_PROFILE"
cp "${PROFILES}/gmktec-xubuntu.env" "$AGENT_PROFILE"

run_plan() {  # run_plan ARGS... -> stdout+stderr in REPLY_OUT, code in REPLY_RC
  REPLY_OUT="$(PATH="${FAKEBIN}:${PATH}" "$SCRIPT" "$@" 2>&1)"
  REPLY_RC=$?
}

# command_lines OUTPUT -> the '+ ' command lines only, with this checkout's path
# and the scratch dir stripped, which ARE the plan's command sequence.
command_lines() {
  printf '%s\n' "$1" | grep -E '^\+ ' | sed -e "s#${HERE}/##g" -e "s#${TMPROOT}/##g"
}

# same DESCRIPTION EXPECTED ACTUAL — assert two multi-line blocks are equal and
# print the difference when they are not.
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
# A. A server profile installs, ordered against k3s.service.
#
# The list is a LITERAL rather than anything derived from the script under test:
# its whole job is to fail if a future edit changes what a SERVER installs, in
# what order, or with which arguments.
# ---------------------------------------------------------------------------
IFS= read -r -d '' EXPECTED_SERVER_COMMANDS <<'EOF'
+ install -d -m 0755 /usr/local/lib/ci-runner-k3s
+ install -m 0755 patch-node-churn-capacity.sh /usr/local/lib/ci-runner-k3s/patch-node-churn-capacity.sh
+ install -m 0644 server.env /usr/local/lib/ci-runner-k3s/server.env
+ sed -e s|K3S_UNIT_PLACEHOLDER|k3s.service|g -e s|PROFILE_PATH_PLACEHOLDER|/usr/local/lib/ci-runner-k3s/server.env|g reapply-node-extended-resource.service > /etc/systemd/system/reapply-node-extended-resource.service
+ install -m 0644 reapply-node-extended-resource.timer /etc/systemd/system/reapply-node-extended-resource.timer
+ systemctl daemon-reload
+ systemctl enable reapply-node-extended-resource.service
+ systemctl enable --now reapply-node-extended-resource.timer
+ systemctl start reapply-node-extended-resource.service
+ systemctl --no-pager status reapply-node-extended-resource.timer
+ kubectl get node poweredge-xubuntu -o jsonpath={.metadata.name}{"\t"}{.status.allocatable.ci-runner\.io/churn-slot}{"\n"}
EOF

printf '== A. server profile: the per-node install sequence, ordered against k3s.service ==\n'
run_plan --dry-run "$SERVER_PROFILE"
if [ "$REPLY_RC" -ne 0 ]; then
  no "server --dry-run exits 0 (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
else
  ok "server --dry-run exits 0"
fi
SERVER_OUT="$REPLY_OUT"
same "server command sequence names k3s.service and the server's own node" \
  "$EXPECTED_SERVER_COMMANDS" "$(command_lines "$SERVER_OUT")"
if printf '%s\n' "$SERVER_OUT" | grep -qi 'refus'; then
  no "the server plan refuses nothing"
else
  ok "the server plan refuses nothing"
fi

# ---------------------------------------------------------------------------
# B. An agent profile installs too, ordered against k3s-agent.service. The
# pre-R5 refusal is gone: the mechanism is per-node now, so an agent runs its
# own node-local timer.
# ---------------------------------------------------------------------------
IFS= read -r -d '' EXPECTED_AGENT_COMMANDS <<'EOF'
+ install -d -m 0755 /usr/local/lib/ci-runner-k3s
+ install -m 0755 patch-node-churn-capacity.sh /usr/local/lib/ci-runner-k3s/patch-node-churn-capacity.sh
+ install -m 0644 agent.env /usr/local/lib/ci-runner-k3s/agent.env
+ sed -e s|K3S_UNIT_PLACEHOLDER|k3s-agent.service|g -e s|PROFILE_PATH_PLACEHOLDER|/usr/local/lib/ci-runner-k3s/agent.env|g reapply-node-extended-resource.service > /etc/systemd/system/reapply-node-extended-resource.service
+ install -m 0644 reapply-node-extended-resource.timer /etc/systemd/system/reapply-node-extended-resource.timer
+ systemctl daemon-reload
+ systemctl enable reapply-node-extended-resource.service
+ systemctl enable --now reapply-node-extended-resource.timer
+ systemctl start reapply-node-extended-resource.service
+ systemctl --no-pager status reapply-node-extended-resource.timer
+ kubectl get node gmktec-xubuntu -o jsonpath={.metadata.name}{"\t"}{.status.allocatable.ci-runner\.io/churn-slot}{"\n"}
EOF

printf '\n== B. agent profile: the same shape, ordered against k3s-agent.service ==\n'
run_plan --dry-run "$AGENT_PROFILE"
if [ "$REPLY_RC" -ne 0 ]; then
  no "agent --dry-run exits 0 (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
else
  ok "agent --dry-run exits 0 (it installs, it does not refuse)"
fi
AGENT_OUT="$REPLY_OUT"
same "agent command sequence names k3s-agent.service and the agent's own node" \
  "$EXPECTED_AGENT_COMMANDS" "$(command_lines "$AGENT_OUT")"
if printf '%s\n' "$AGENT_OUT" | grep -qi 'refus'; then
  no "the agent plan refuses nothing"
else
  ok "the agent plan refuses nothing"
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
# D. The profile is data, and is validated as data.
# ---------------------------------------------------------------------------
printf '\n== D. profile validation ==\n'

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

refuses "no profile given is refused, naming what is missing" \
  "no profile given" --dry-run

refuses "a nonexistent profile path is refused, naming it" \
  "profile not found" --dry-run "${TMPROOT}/does-not-exist.env"

refuses "a second positional argument is refused rather than ignored" \
  "unexpected extra argument" --dry-run "$SERVER_PROFILE" "$AGENT_PROFILE"

refuses "an unknown option is refused with the usage line" \
  "unknown option '--force'" --dry-run --force "$SERVER_PROFILE"

BAD_CAPACITY="${TMPROOT}/bad-capacity.env"
sed 's#^ADMISSION_CAPACITY_C=.*#ADMISSION_CAPACITY_C=thirty-two#' "$SERVER_PROFILE" > "$BAD_CAPACITY"
refuses "a non-numeric ADMISSION_CAPACITY_C is refused, naming it" \
  "ADMISSION_CAPACITY_C must be a non-negative integer" --dry-run "$BAD_CAPACITY"

BAD_ROLE="${TMPROOT}/bad-role.env"
sed 's#^CLUSTER_ROLE=.*#CLUSTER_ROLE=worker#' "$SERVER_PROFILE" > "$BAD_ROLE"
refuses "an unknown CLUSTER_ROLE is refused, naming it" \
  "CLUSTER_ROLE must be 'server' or 'agent', got 'worker'" --dry-run "$BAD_ROLE"

NO_KUBECONFIG="${TMPROOT}/agent-no-kubeconfig.env"
sed 's#^CHURN_KUBECONFIG_FILE=.*#CHURN_KUBECONFIG_FILE=#' "$AGENT_PROFILE" > "$NO_KUBECONFIG"
refuses "an agent with an empty CHURN_KUBECONFIG_FILE is refused, naming the key" \
  "CHURN_KUBECONFIG_FILE is empty" --dry-run "$NO_KUBECONFIG"

# ---------------------------------------------------------------------------
printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
