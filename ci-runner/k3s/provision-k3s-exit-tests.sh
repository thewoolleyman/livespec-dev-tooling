#!/usr/bin/env bash
# provision-k3s-exit-tests.sh — prove the role-awareness of ./provision-k3s.sh
# WITHOUT touching any host: that the step plan a `server` profile yields is
# byte-for-byte the plan the single-node era ran (the same six steps, in the
# same order, with the same k3s install command), that an `agent` profile's
# plan is the pinned k3s AGENT install carrying the join address, the token
# file, the node IP, the taints and the runner-role label, that the five
# server-only steps are skipped with a reason each, and that a join token that
# is missing or readable beyond its owner is REFUSED.
#
#   A. a server profile's --dry-run plan is the HISTORICAL ordered step list,
#      every one of them RUN, every line tagged [server], and its install
#      command is the pre-change one verbatim;
#   B. an agent profile's --dry-run plan RUNs exactly the k3s install and SKIPs
#      the five server steps with a logged reason each, and the install command
#      carries the pin, --server from CLUSTER_JOIN_ADDRESS, --token-file from
#      CLUSTER_TOKEN_FILE, --node-ip from NODE_ADDRESS, --node-taint from
#      NODE_TAINTS and the k3s-role=arc-runner-host label;
#   C. --dry-run executes nothing: no install runs, and not one of the
#      host-mutating tools the steps reach for is invoked;
#   D. the join token is a credential and is treated as one — an absent
#      CLUSTER_TOKEN_FILE and a group- or world-readable one are each refused,
#      naming the path; and the profile is validated as data;
#   E. the COMMITTED second node's profile,
#      `phase0-bare-metal/profiles/gmktec-xubuntu.env`, yields that node's join
#      through this same script: the plan names the node and the role it read,
#      and the install line carries the pin, the first node's API address, the
#      token file and `--node-ip 192.168.1.156` (the bare address, not the
#      profile's netplan CIDR), and — since R5 opened the node — NO `--node-taint`
#      at all, the once-present `NoSchedule` taint gone. B proves the agent
#      BRANCH with a fixture; only E proves the second NODE's committed data.
#
# HOW IT STAYS OFF THE HOST. Every case runs `provision-k3s.sh --dry-run`,
# which by construction executes no step. On top of that each case prepends a
# scratch PATH of TRIPWIRES for every host-mutating tool the steps underneath
# would reach (`curl`, `k3s`, `kubectl`, `helm`, `install`, `chmod`, `tar`,
# `findmnt`): a run that executed a step would leave the tripwire file
# non-empty, which case C asserts it does not. The suite never runs as root and
# never needs to.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/provision-k3s.sh"
SERVER_PROFILE="${HERE}/phase0-bare-metal/profiles/poweredge-xubuntu.env"

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
for tool in curl k3s kubectl helm install chmod tar findmnt; do
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

# plan_lines OUTPUT -> the RUN/SKIP lines and the planned commands, which ARE
# the plan.
plan_lines() { printf '%s\n' "$1" | grep -E '^(RUN|SKIP|     \+) '; }

# An agent profile: the committed server profile with its cluster and network
# keys flipped to the second node's facts. Written here rather than committed
# under profiles/ because a profile in that directory is a claim that a real
# node exists; this one is a fixture.
TOKEN_FILE="${TMPROOT}/join-token"
printf 'K10deadbeef::server:notasecret\n' > "$TOKEN_FILE"
chmod 0600 "$TOKEN_FILE"

agent_profile() {  # agent_profile DEST [SED-EXPR...]
  local dest="$1"; shift
  sed -e 's/^NODE_NAME=.*/NODE_NAME=agent-fixture/' \
      -e 's/^CLUSTER_ROLE=.*/CLUSTER_ROLE=agent/' \
      -e "s#^CLUSTER_JOIN_ADDRESS=.*#CLUSTER_JOIN_ADDRESS=https://192.168.1.200:6443#" \
      -e "s#^CLUSTER_TOKEN_FILE=.*#CLUSTER_TOKEN_FILE=${TOKEN_FILE}#" \
      -e 's#^NODE_TAINTS=.*#NODE_TAINTS=node-role/ci=pending:NoSchedule#' \
      -e 's#^NODE_NETWORK_INTERFACE=.*#NODE_NETWORK_INTERFACE=eno1#' \
      -e 's#^NODE_ADDRESS=.*#NODE_ADDRESS=192.168.1.156/24#' \
      "${@/#/-e}" "$SERVER_PROFILE" > "$dest"
}

AGENT_PROFILE="${TMPROOT}/agent-fixture.env"
agent_profile "$AGENT_PROFILE"

# ---------------------------------------------------------------------------
# A. The server plan is the historical one, in the historical order, with the
#    historical install command.
#
# This list is the pre-role-awareness script's `log` lines and its one piped
# install command, transcribed. It is deliberately a LITERAL rather than
# anything derived from the script under test: its whole job is to fail if a
# future edit reorders a step, drops one, or changes a single flag of the
# install the single-node runbook ran.
# ---------------------------------------------------------------------------
read -r -d '' EXPECTED_SERVER_PLAN <<'EOF'
RUN  [server] 0. Install the fleet's k3s server config BEFORE the first k3s start
RUN  [server] 1. Install k3s v1.36.2+k3s1 (idempotent — skip if already at this version)
     + curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION='v1.36.2+k3s1' INSTALL_K3S_EXEC='server --disable traefik --disable servicelb --node-label k3s-role=arc-runner-host' sh -s -
RUN  [server] 1b. Install helm v3.21.4 (idempotent — skip if already at this version)
RUN  [server] 2. Wait for the node to report Ready
RUN  [server] 2b. Label this node as the cache-tier carrier (idempotent)
RUN  [server] 3. Make kubectl usable for the provisioning admin (read access to KUBECONFIG)
EOF

printf '== A. server profile: the plan is the pre-change command sequence ==\n'
run_plan --dry-run "$SERVER_PROFILE"
if [ "$REPLY_RC" -ne 0 ]; then
  no "server --dry-run exits 0 (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
else
  ok "server --dry-run exits 0"
fi
SERVER_PLAN="$(plan_lines "$REPLY_OUT")"
if [ "$SERVER_PLAN" = "$EXPECTED_SERVER_PLAN" ]; then
  ok "server plan equals the historical ordered command sequence"
else
  no "server plan equals the historical ordered command sequence"
  diff <(printf '%s\n' "$EXPECTED_SERVER_PLAN") <(printf '%s\n' "$SERVER_PLAN") || true
fi
if printf '%s\n' "$REPLY_OUT" | grep -q '^role:     server$'; then
  ok "server plan header states the role it read from the profile"
else
  no "server plan header states the role it read from the profile"
fi
if printf '%s\n' "$SERVER_PLAN" | grep -q 'SKIP'; then
  no "a server skips nothing"
else
  ok "a server skips nothing"
fi

# ---------------------------------------------------------------------------
# B. The agent plan is the pinned agent install, and nothing the server owns.
# ---------------------------------------------------------------------------
printf '\n== B. agent profile: the pinned agent join, server-only steps out ==\n'
run_plan --dry-run "$AGENT_PROFILE"
if [ "$REPLY_RC" -ne 0 ]; then
  no "agent --dry-run exits 0 (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
else
  ok "agent --dry-run exits 0"
fi
AGENT_OUT="$REPLY_OUT"
AGENT_PLAN="$(plan_lines "$AGENT_OUT")"
AGENT_COMMAND="$(printf '%s\n' "$AGENT_OUT" | grep '^     + ' | sed -e 's/^     + //')"

for fragment in \
  "INSTALL_K3S_VERSION='v1.36.2+k3s1'" \
  "agent --server https://192.168.1.200:6443" \
  "--token-file ${TOKEN_FILE}" \
  "--node-ip 192.168.1.156" \
  "--node-taint node-role/ci=pending:NoSchedule" \
  "--node-label k3s-role=arc-runner-host"
do
  if printf '%s\n' "$AGENT_COMMAND" | grep -qF -- "$fragment"; then
    ok "the agent install command carries: ${fragment}"
  else
    no "the agent install command carries: ${fragment} (got: ${AGENT_COMMAND})"
  fi
done

# The token is read AT RUN TIME out of the file k3s is pointed at; the command
# never carries the token itself, and this tree never holds one.
if printf '%s\n' "$AGENT_COMMAND" | grep -qF 'K10deadbeef'; then
  no "the install command names the token FILE and never the token"
else
  ok "the install command names the token FILE and never the token"
fi

if printf '%s\n' "$AGENT_PLAN" | grep -qF "RUN  [agent] 1. Install k3s v1.36.2+k3s1 AGENT joining https://192.168.1.200:6443"; then
  ok "the agent RUNs the pinned agent install, naming the cluster it joins"
else
  no "the agent RUNs the pinned agent install, naming the cluster it joins"
fi

for fragment in \
  "0. Install the fleet's k3s server config" \
  "1b. Install helm v3.21.4" \
  "2. Wait for the node to report Ready" \
  "2b. Label this node as the cache-tier carrier" \
  "3. Make kubectl usable for the provisioning admin"
do
  if printf '%s\n' "$AGENT_PLAN" | grep -qF "SKIP [agent] ${fragment}"; then
    ok "agent SKIPs: ${fragment}"
  else
    no "agent SKIPs: ${fragment}"
  fi
  if printf '%s\n' "$AGENT_PLAN" | grep -qF "RUN  [agent] ${fragment}"; then
    no "agent plan must not RUN: ${fragment}"
  else
    ok "agent plan does not RUN: ${fragment}"
  fi
done

# No skipped step is silent: each SKIP line is followed by its reason.
skip_count="$(printf '%s\n' "$AGENT_PLAN" | grep -c '^SKIP ')"
reason_count="$(printf '%s\n' "$AGENT_OUT" | grep -c '^     reason: ')"
if [ "$skip_count" -eq 5 ] && [ "$reason_count" -eq 5 ]; then
  ok "every one of the ${skip_count} skipped steps carries a logged reason"
else
  no "every skipped step carries a logged reason (skips=${skip_count} reasons=${reason_count})"
fi

# The steps stay in the server's relative order — the agent plan is a filter of
# the runbook, never a re-ordering of it.
SERVER_ORDER="$(printf '%s\n' "$SERVER_PLAN" | grep '^RUN ' | sed -E 's/^RUN  \[server\] //')"
AGENT_ORDER="$(printf '%s\n' "$AGENT_PLAN" | grep -E '^(RUN|SKIP) ' | sed -E 's/^(RUN|SKIP)  ?\[agent\] //' \
  | sed -E 's/^(1\.) Install k3s (v[^ ]+) AGENT joining .*/\1 Install k3s \2 (idempotent — skip if already at this version)/')"
if [ "$SERVER_ORDER" = "$AGENT_ORDER" ]; then
  ok "the agent plan is the server plan filtered, in the same order"
else
  no "the agent plan is the server plan filtered, in the same order"
  diff <(printf '%s\n' "$SERVER_ORDER") <(printf '%s\n' "$AGENT_ORDER") || true
fi

# The pin comes from the PROFILE, not from the script: a node that pins no
# address gets no --node-ip, and a node that declares two taints gets two.
AUTO_IP_PROFILE="${TMPROOT}/agent-auto-ip.env"
agent_profile "$AUTO_IP_PROFILE" 's#^NODE_ADDRESS=.*#NODE_ADDRESS=auto#' \
  's#^NODE_NETWORK_INTERFACE=.*#NODE_NETWORK_INTERFACE=auto#'
run_plan --dry-run "$AUTO_IP_PROFILE"
if [ "$REPLY_RC" -eq 0 ] && ! printf '%s\n' "$REPLY_OUT" | grep -qF -- '--node-ip'; then
  ok "NODE_ADDRESS=auto pins no --node-ip"
else
  no "NODE_ADDRESS=auto pins no --node-ip (rc=${REPLY_RC})"
fi

TWO_TAINTS_PROFILE="${TMPROOT}/agent-two-taints.env"
agent_profile "$TWO_TAINTS_PROFILE" \
  's#^NODE_TAINTS=.*#NODE_TAINTS=node-role/ci=pending:NoSchedule tier=none:NoExecute#'
run_plan --dry-run "$TWO_TAINTS_PROFILE"
if [ "$REPLY_RC" -eq 0 ] \
  && printf '%s\n' "$REPLY_OUT" | grep -qF -- '--node-taint node-role/ci=pending:NoSchedule --node-taint tier=none:NoExecute'; then
  ok "every NODE_TAINTS record becomes its own --node-taint"
else
  no "every NODE_TAINTS record becomes its own --node-taint (rc=${REPLY_RC})"
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
if printf '%s\n' "$AGENT_OUT" | grep -q 'NOTHING was executed'; then
  ok "the dry run says so in its own output"
else
  no "the dry run says so in its own output"
fi

# ---------------------------------------------------------------------------
# D. The join token is a credential; the profile is data.
# ---------------------------------------------------------------------------
printf '\n== D. token-file refusals and profile validation ==\n'

refuses() {  # refuses DESCRIPTION EXPECTED-FRAGMENT PROFILE
  run_plan --dry-run "$3"
  if [ "$REPLY_RC" -eq 0 ]; then
    no "$1 (exited 0)"
    return
  fi
  case "$REPLY_OUT" in
    *"$2"*) ok "$1" ;;
    *) no "$1 (message did not name it: ${REPLY_OUT})" ;;
  esac
}

MISSING_TOKEN="${TMPROOT}/agent-missing-token.env"
agent_profile "$MISSING_TOKEN" "s#^CLUSTER_TOKEN_FILE=.*#CLUSTER_TOKEN_FILE=${TMPROOT}/no-such-token#"
refuses "an absent CLUSTER_TOKEN_FILE is refused, naming the path" \
  "${TMPROOT}/no-such-token', which does not exist on this node" "$MISSING_TOKEN"

WIDE_TOKEN="${TMPROOT}/wide-token"
printf 'K10deadbeef::server:notasecret\n' > "$WIDE_TOKEN"
chmod 0644 "$WIDE_TOKEN"
WIDE_TOKEN_PROFILE="${TMPROOT}/agent-wide-token.env"
agent_profile "$WIDE_TOKEN_PROFILE" "s#^CLUSTER_TOKEN_FILE=.*#CLUSTER_TOKEN_FILE=${WIDE_TOKEN}#"
refuses "a world-readable CLUSTER_TOKEN_FILE is refused, naming the mode" \
  "is mode 644, readable beyond its owner" "$WIDE_TOKEN_PROFILE"

chmod 0640 "$WIDE_TOKEN"
refuses "a group-readable CLUSTER_TOKEN_FILE is refused too" \
  "is mode 640, readable beyond its owner" "$WIDE_TOKEN_PROFILE"

NO_TOKEN_KEY="${TMPROOT}/agent-no-token-key.env"
grep -v '^CLUSTER_TOKEN_FILE=' "$AGENT_PROFILE" > "$NO_TOKEN_KEY"
refuses "an agent profile naming no CLUSTER_TOKEN_FILE at all is refused" \
  "CLUSTER_ROLE=agent must name both CLUSTER_JOIN_ADDRESS and CLUSTER_TOKEN_FILE" "$NO_TOKEN_KEY"

BAD_TAINT="${TMPROOT}/agent-bad-taint.env"
agent_profile "$BAD_TAINT" 's#^NODE_TAINTS=.*#NODE_TAINTS=node-role/ci#'
refuses "a NODE_TAINTS record that is not key=value:Effect is refused, naming it" \
  "NODE_TAINTS record 'node-role/ci' is not <key>=<value>:<Effect>" "$BAD_TAINT"

BAD_ROLE="${TMPROOT}/bad-role.env"
sed -e 's/^CLUSTER_ROLE=.*/CLUSTER_ROLE=worker/' "$SERVER_PROFILE" > "$BAD_ROLE"
refuses "a CLUSTER_ROLE that is neither server nor agent is refused, naming it" \
  "CLUSTER_ROLE must be 'server' or 'agent', got 'worker'" "$BAD_ROLE"

NOT_DATA="${TMPROOT}/not-data.env"
{ cat "$SERVER_PROFILE"; printf 'rm -rf /\n'; } > "$NOT_DATA"
refuses "a line that is not KEY=value is refused rather than sourced" \
  "not a KEY=value line" "$NOT_DATA"

refuses "a missing profile is refused, naming the path" \
  "profile not found" "${TMPROOT}/does-not-exist.env"

run_plan --dry-run
if [ "$REPLY_RC" -ne 0 ] && printf '%s\n' "$REPLY_OUT" | grep -q 'no profile given'; then
  ok "no profile at all is refused with the usage line"
else
  no "no profile at all is refused with the usage line"
fi

# ---------------------------------------------------------------------------
# E. The COMMITTED second node's profile, not a fixture derived from the first.
#
# Section B proved the agent BRANCH using a fixture this suite writes. That
# fixture is deliberately not the real thing: it is the first node's profile
# with its cluster keys flipped, so it proves the code and says nothing about
# whether `phase0-bare-metal/profiles/gmktec-xubuntu.env` — the second pool
# node as committed DATA — actually yields the join the second node needs.
# This section runs the committed file.
#
# ONE SUBSTITUTION, AND WHY IT IS NOT A CHEAT. The committed profile names
# CLUSTER_TOKEN_FILE=/etc/rancher/k3s/agent-join-token, a path on THE NODE
# holding a cluster credential this tree does not carry and this suite must not
# create. provision-k3s.sh refuses an absent token file in `--dry-run` too — on
# purpose, so an operator cannot be handed a plan that could not have run — so
# a suite that pointed at the committed path would be asserting that refusal
# and nothing else. The copy below therefore redirects that ONE key at a
# scratch 0600 file and asserts (E1) both that the committed value is the
# documented node path and that the copy differs from the committed file on
# exactly that one line. Every other value in the plan is the committed one.
# ---------------------------------------------------------------------------
printf '\n== E. the committed gmktec-xubuntu profile: the second node as data ==\n'

GMKTEC_COMMITTED="${HERE}/phase0-bare-metal/profiles/gmktec-xubuntu.env"
GMKTEC_TOKEN="${TMPROOT}/gmktec-join-token"
printf 'K10deadbeef::server:notasecret\n' > "$GMKTEC_TOKEN"
chmod 0600 "$GMKTEC_TOKEN"

GMKTEC_PROFILE="${TMPROOT}/gmktec-with-scratch-token.env"
sed "s#^CLUSTER_TOKEN_FILE=.*#CLUSTER_TOKEN_FILE=${GMKTEC_TOKEN}#" \
  "$GMKTEC_COMMITTED" > "$GMKTEC_PROFILE"

substituted="$(diff "$GMKTEC_COMMITTED" "$GMKTEC_PROFILE" | grep -c '^[<>]')"
if grep -qxF 'CLUSTER_TOKEN_FILE=/etc/rancher/k3s/agent-join-token' "$GMKTEC_COMMITTED" \
   && [ "$substituted" -eq 2 ]; then
  ok "E1  the committed profile names the node's own token path, and only that line is substituted"
else
  no "E1  the committed profile names the node's own token path, and only that line is substituted (${substituted} line(s) differ)"
fi

run_plan --dry-run "$GMKTEC_PROFILE"
GMKTEC_OUT="$REPLY_OUT"
GMKTEC_RC="$REPLY_RC"
GMKTEC_COMMAND="$(printf '%s\n' "$GMKTEC_OUT" | grep '^     + ' | sed -e 's/^     + //')"

if [ "$GMKTEC_RC" -eq 0 ]; then
  ok "E2  --dry-run against the committed gmktec profile exits 0"
else
  no "E2  --dry-run against the committed gmktec profile exits 0 (rc=${GMKTEC_RC})"
  printf '%s\n' "$GMKTEC_OUT"
fi

# The header states the node and the role it read, so the plan an operator
# reads names which machine it is for.
for header in 'node:     gmktec-xubuntu' 'role:     agent' \
              'join:     https://192.168.1.200:6443'; do
  if printf '%s\n' "$GMKTEC_OUT" | grep -qxF "$header"; then
    ok "E3  the plan header states: ${header}"
  else
    no "E3  the plan header states: ${header}"
  fi
done

# The install line itself — the pin, the server it joins, the token FILE, the
# node IP taken from the profile's netplan CIDR, and the runner-role label the
# phase2 node pins resolve against. There is NO --node-taint any more: R5
# (livespec-dev-tooling-xa6o) emptied this profile's NODE_TAINTS when it opened
# the node for general CI churn, so the once-present
# `node-role/ci=pending:NoSchedule` is gone — asserted as an absence just below.
for fragment in \
  "INSTALL_K3S_VERSION='v1.36.2+k3s1'" \
  "agent --server https://192.168.1.200:6443" \
  "--token-file ${GMKTEC_TOKEN}" \
  "--node-ip 192.168.1.156" \
  "--node-label k3s-role=arc-runner-host"
do
  if printf '%s\n' "$GMKTEC_COMMAND" | grep -qF -- "$fragment"; then
    ok "E4  the gmktec agent install line carries: ${fragment}"
  else
    no "E4  the gmktec agent install line carries: ${fragment} (got: ${GMKTEC_COMMAND})"
  fi
done

# R5 opened this node, so its NODE_TAINTS is empty and the install line carries
# no --node-taint at all — the taint that kept it closed is gone.
if printf '%s\n' "$GMKTEC_COMMAND" | grep -qF -- '--node-taint'; then
  no "E4b  the opened gmktec profile emits NO --node-taint (got: ${GMKTEC_COMMAND})"
else
  ok "E4b  the opened gmktec profile emits NO --node-taint"
fi

# `--node-ip` is the bare address, never the /24 the profile states: the CIDR is
# what netplan wants and what k3s would reject.
if printf '%s\n' "$GMKTEC_COMMAND" | grep -qF -- '192.168.1.156/24'; then
  no "E5  the install line pins the bare address, not the netplan CIDR"
else
  ok "E5  the install line pins the bare address, not the netplan CIDR"
fi

# The five server-only steps are the server's on this node too.
gmktec_skips="$(printf '%s\n' "$GMKTEC_OUT" | grep -c '^SKIP \[agent\] ')"
if [ "$gmktec_skips" -eq 5 ]; then
  ok "E6  the committed profile skips the five steps that are the server's"
else
  no "E6  the committed profile skips the five steps that are the server's (${gmktec_skips} skipped)"
fi

if [ -s "$TRIPWIRE" ]; then
  no "E7  section E executed no host-mutating command"
  cat "$TRIPWIRE"
else
  ok "E7  section E executed no host-mutating command"
fi

# ---------------------------------------------------------------------------
printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
