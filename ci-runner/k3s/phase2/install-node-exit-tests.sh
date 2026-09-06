#!/usr/bin/env bash
# install-node-exit-tests.sh — prove the role-awareness of ./install-node.sh
# WITHOUT touching any host: that the step plan a `server` profile yields is
# byte-for-byte the plan the single-node era ran, that an `agent` profile's
# plan drops exactly the cluster-side and datastore steps and keeps the
# node-local ones, and that `--dry-run` executes none of them.
#
#   A. a server profile's --dry-run plan is the HISTORICAL ordered step list
#      (the sixteen installer invocations the numbering 1..10 with its
#      sub-letters names), every one of them RUN, every line tagged [server];
#   B. an agent profile's --dry-run plan OMITS the reconstruct converge — the
#      only step that applies Kueue ClusterQueues and ARC scale sets — plus
#      the secret reinjection unit, the tmpfs datastore and the iDRAC thermal
#      step, each with a logged reason, and KEEPS k3s config, the kernel
#      budgets, AppArmor (profile only), the storage layout, the churn slot,
#      both scans and the sweep;
#   C. --dry-run executes nothing: not one installer runs, and not one of the
#      host-mutating tools they reach for is invoked;
#   D. the profile is DATA and is validated as data — a missing key, an
#      unknown role, a non-numeric capacity and a missing file are each
#      refused, naming what was wrong.
#
# HOW IT STAYS OFF THE HOST. Every case runs `install-node.sh --dry-run`,
# which by construction invokes no installer. On top of that each case
# prepends a scratch PATH of TRIPWIRES for every host-mutating tool the
# installers underneath would reach (`install`, `systemctl`, `apparmor_parser`,
# `kubectl`, `sysctl`, `mount`, `apt-get`, `helm`): a run that executed a step
# would leave the tripwire file non-empty, which case C asserts it does not.
# The suite never runs as root and never needs to.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/install-node.sh"
SERVER_PROFILE="${HERE}/../phase0-bare-metal/profiles/poweredge-xubuntu.env"

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
for tool in install systemctl apparmor_parser kubectl sysctl mount apt-get helm; do
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

# plan_lines OUTPUT -> the RUN/SKIP lines only, which ARE the step plan.
plan_lines() { printf '%s\n' "$1" | grep -E '^(RUN|SKIP) '; }

# An agent profile: the committed server profile with its cluster keys flipped.
# Written here rather than committed under profiles/ because a profile in that
# directory is a claim that a real node exists; this one is a fixture.
AGENT_PROFILE="${TMPROOT}/agent-fixture.env"
sed -e 's/^NODE_NAME=.*/NODE_NAME=agent-fixture/' \
    -e 's/^CLUSTER_ROLE=.*/CLUSTER_ROLE=agent/' \
    -e 's/^CLUSTER_JOIN_ADDRESS=.*/CLUSTER_JOIN_ADDRESS=https:\/\/10.0.0.1:6443/' \
    "$SERVER_PROFILE" > "$AGENT_PROFILE"

# ---------------------------------------------------------------------------
# A. The server plan is the historical one, in the historical order.
#
# This list is the pre-role-awareness script's `log` lines, transcribed. It is
# deliberately a LITERAL rather than anything derived from the script under
# test: its whole job is to fail if a future edit reorders or drops a step the
# single-node runbook ran.
# ---------------------------------------------------------------------------
read -r -d '' EXPECTED_SERVER_PLAN <<'EOF'
RUN  [server] 1/10 k3s server config
RUN  [server] 2/10 inotify instance budget + keyring quota
RUN  [server] 2b/10 storage layout (LABEL fstab lines + k3s drop-in; no-op when the tiers are live)
RUN  [server] 2c/10 iDRAC cooling configuration (racadm + fan loop automatic, third-party response off, Minimum Power profile)
RUN  [server] 2d/10 operator host tools (btop-loop into /usr/local/bin)
RUN  [server] 3/10 AppArmor profile + hook ConfigMap
RUN  [server] 4/10 churn-slot extended resource (capacity 32) + reapply timer
RUN  [server] 5/10 wedged-runner scan (clear)
RUN  [server] 5b/10 runner-pod lifecycle scan (report-only; no mode — see its installer's header)
RUN  [server] 6/10 ARC log archive
RUN  [server] 7/10 boot-time GitHub App secret reinjection unit (enable only)
RUN  [server] 7b/10 pool-provided sccache binary (node-local; mounted read-only into every job)
RUN  [server] 7c/10 fleet-patched ARC container hook + externals extraction from the pinned runner image
RUN  [server] 8/10 reconstruct-on-boot converge unit + artifacts (enable only)
RUN  [server] 9/10 tmpfs datastore mount (enable only, never started here)
RUN  [server] 10/10 boot-time orphaned-scratch sweep (enable only)
EOF

printf '== A. server profile: the plan is the pre-change ten-step runbook ==\n'
run_plan --dry-run "$SERVER_PROFILE"
if [ "$REPLY_RC" -ne 0 ]; then
  no "server --dry-run exits 0 (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
else
  ok "server --dry-run exits 0"
fi
SERVER_PLAN="$(plan_lines "$REPLY_OUT")"
if [ "$SERVER_PLAN" = "$EXPECTED_SERVER_PLAN" ]; then
  ok "server step plan equals the historical ordered step list"
else
  no "server step plan equals the historical ordered step list"
  diff <(printf '%s\n' "$EXPECTED_SERVER_PLAN") <(printf '%s\n' "$SERVER_PLAN") || true
fi
if printf '%s\n' "$REPLY_OUT" | grep -q '^role:     server$'; then
  ok "server plan header states the role it read from the profile"
else
  no "server plan header states the role it read from the profile"
fi
if printf '%s\n' "$REPLY_OUT" | grep -q '^capacity: 32 '; then
  ok "capacity comes from the profile's ADMISSION_CAPACITY_C"
else
  no "capacity comes from the profile's ADMISSION_CAPACITY_C"
fi

# ---------------------------------------------------------------------------
# B. The agent plan drops the cluster-side and datastore steps, keeps the
#    node-local ones, and gives a reason for every drop.
# ---------------------------------------------------------------------------
printf '\n== B. agent profile: cluster-side steps out, node-local steps in ==\n'
run_plan --dry-run "$AGENT_PROFILE"
if [ "$REPLY_RC" -ne 0 ]; then
  no "agent --dry-run exits 0 (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
else
  ok "agent --dry-run exits 0"
fi
AGENT_OUT="$REPLY_OUT"
AGENT_PLAN="$(plan_lines "$AGENT_OUT")"

# The four skipped steps, by the label fragment that identifies each. The
# reconstruct converge is the only step that applies Kueue ClusterQueues and
# ARC scale sets, so its absence is what omits Kueue and ARC from this plan.
for fragment in \
  "2c/10 iDRAC cooling configuration" \
  "7/10 boot-time GitHub App secret reinjection unit" \
  "8/10 reconstruct-on-boot converge unit" \
  "9/10 tmpfs datastore mount"
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
if [ "$skip_count" -eq 4 ] && [ "$reason_count" -eq 4 ]; then
  ok "every one of the ${skip_count} skipped steps carries a logged reason"
else
  no "every skipped step carries a logged reason (skips=${skip_count} reasons=${reason_count})"
fi

# Nothing in the agent plan applies the cluster-side Kueue or ARC objects: the
# reconstruct converge is gone, and no other RUN line names either of them.
if printf '%s\n' "$AGENT_PLAN" | grep '^RUN ' | grep -qiE 'kueue|scale set|clusterqueue'; then
  no "no RUN step in the agent plan applies Kueue queues or ARC scale sets"
else
  ok "no RUN step in the agent plan applies Kueue queues or ARC scale sets"
fi

for fragment in \
  "1/10 k3s server config" \
  "2/10 inotify instance budget + keyring quota" \
  "2b/10 storage layout" \
  "2d/10 operator host tools" \
  "3/10 AppArmor profile only (--profile-only;" \
  "4/10 churn-slot extended resource (capacity 32) + reapply timer" \
  "5/10 wedged-runner scan (clear)" \
  "5b/10 runner-pod lifecycle scan" \
  "6/10 ARC log archive" \
  "7b/10 pool-provided sccache binary" \
  "7c/10 fleet-patched ARC container hook" \
  "10/10 boot-time orphaned-scratch sweep"
do
  if printf '%s\n' "$AGENT_PLAN" | grep -qF "RUN  [agent] ${fragment}"; then
    ok "agent RUNs: ${fragment}"
  else
    no "agent RUNs: ${fragment}"
  fi
done

# The agent's steps stay in the server's relative order — the plan is a filter
# of the runbook, never a re-ordering of it.
SERVER_ORDER="$(printf '%s\n' "$SERVER_PLAN" | sed -E 's/^RUN  \[server\] //')"
AGENT_ORDER="$(printf '%s\n' "$AGENT_PLAN" | sed -E 's/^(RUN|SKIP)  ?\[agent\] //' | sed -E 's/^(3\/10) AppArmor profile only.*/\1 AppArmor profile + hook ConfigMap/')"
if [ "$SERVER_ORDER" = "$AGENT_ORDER" ]; then
  ok "the agent plan is the server plan filtered, in the same order"
else
  no "the agent plan is the server plan filtered, in the same order"
  diff <(printf '%s\n' "$SERVER_ORDER") <(printf '%s\n' "$AGENT_ORDER") || true
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
# D. The profile is data, and is validated as data.
# ---------------------------------------------------------------------------
printf '\n== D. profile validation ==\n'

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

NO_ROLE="${TMPROOT}/no-role.env"
grep -v '^CLUSTER_ROLE=' "$SERVER_PROFILE" > "$NO_ROLE"
refuses "a profile with no CLUSTER_ROLE is refused, naming the key" \
  "missing required profile key 'CLUSTER_ROLE'" "$NO_ROLE"

BAD_ROLE="${TMPROOT}/bad-role.env"
sed -e 's/^CLUSTER_ROLE=.*/CLUSTER_ROLE=worker/' "$SERVER_PROFILE" > "$BAD_ROLE"
refuses "a CLUSTER_ROLE that is neither server nor agent is refused, naming it" \
  "CLUSTER_ROLE must be 'server' or 'agent', got 'worker'" "$BAD_ROLE"

BAD_CAPACITY="${TMPROOT}/bad-capacity.env"
sed -e 's/^ADMISSION_CAPACITY_C=.*/ADMISSION_CAPACITY_C=thirty-two/' "$SERVER_PROFILE" > "$BAD_CAPACITY"
refuses "a non-numeric ADMISSION_CAPACITY_C is refused, naming it" \
  "ADMISSION_CAPACITY_C must be a non-negative integer" "$BAD_CAPACITY"

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
printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
