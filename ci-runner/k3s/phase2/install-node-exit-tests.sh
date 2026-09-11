#!/usr/bin/env bash
# install-node-exit-tests.sh — prove the role-awareness of ./install-node.sh
# WITHOUT touching any host: that the step plan a `server` profile yields is
# byte-for-byte the plan the single-node era ran, that an `agent` profile's
# plan drops exactly the cluster-side and datastore steps and keeps the
# node-local ones, and that `--dry-run` executes none of them.
#
#   A. a server profile's --dry-run plan is the HISTORICAL ordered step list
#      (the installer invocations the numbering 1..10 with its sub-letters
#      names), every one RUN and tagged [server] EXCEPT the one agent-only
#      step — 1b agent-rejoin, the k3s-agent wedge watchdog — which the
#      self-authoritative server SKIPs with a reason, the mirror of the agent
#      skips below;
#   B. an agent profile's --dry-run plan OMITS the reconstruct converge — the
#      only step that applies Kueue ClusterQueues and ARC scale sets — plus
#      the secret reinjection unit, the tmpfs datastore, the iDRAC thermal step,
#      both cluster-wide scans and the ARC log archive, each with a logged
#      reason, and KEEPS k3s config, the kernel budgets, AppArmor (profile only),
#      the storage layout, the host tools, the churn-slot reapply timer (per-node
#      since R5, carrying an agent NOTE for its node-status-kubeconfig
#      prerequisite), sccache, the container hook and the scratch sweep;
#   B2. step 1's plan NAMES the file it installs, and names a DIFFERENT one per
#      role — config.yaml plus the local-storage skip marker on a server,
#      config.agent.yaml and NO marker on an agent. This is the one step that
#      is on both plans while doing something a role can be KILLED by: the
#      server file's `disable` key is not in k3s-agent's flag set, so an agent
#      handed it exits `flag provided but not defined: -disable` at its next
#      start (gmktec-xubuntu 2026-09-07, livespec-dev-tooling-vcv4). A plan
#      that says only "1/10 k3s config" cannot be read for that difference,
#      which is why the label carries the filename;
#   C. --dry-run executes nothing: not one installer runs, and not one of the
#      host-mutating tools they reach for is invoked — the only commands that
#      reach a real binary are the read-only `systemctl list-unit-files`
#      presence probe and the `systemctl is-failed` residual probe case E's
#      removal needs;
#   D. the profile is DATA and is validated as data — a missing key, an
#      unknown role, a non-numeric capacity and a missing file are each
#      refused, naming what was wrong;
#   E. an agent's SKIP also REMOVES the server-only units an earlier run of
#      this runbook installed here. A skip does not invoke the installer, so
#      the installer's own removal never runs on the node that has them: a
#      full exit-0 runbook run left enabled, failed timers on gmktec-xubuntu
#      2026-09-07 (livespec-dev-tooling-43sc). Since R5 the removable set is the
#      THREE genuinely server-only unit-installing steps — the two cluster-wide
#      scans and the ARC log archive; the churn-slot reapply timer is NO LONGER
#      among them, because churn-slot now installs a per-node timer on an agent,
#      so a reapply unit found here is legitimate and is LEFT (asserted below).
#      Under a stubbed systemctl those three are disabled and deleted, timer
#      before service, followed by one daemon-reload and then one `reset-failed`
#      per unit removed — without which the deleted units stay in `list-units
#      --state=failed` as `not-found failed` until the host reboots, which is
#      what the next stage-4 re-run found (livespec-dev-tooling-oc5g); under a
#      stub that reports nothing present AND nothing failed, no removal line is
#      printed at all; under a stub that reports nothing present but the three
#      timers STILL FAILED — the state a clear over the units REMOVED can
#      never converge (livespec-dev-tooling-ssbg) — the reset-failed lines are
#      what the REMOVE header carries; and a SERVER prints none even when the
#      stub says every unit is there.
#
# HOW IT STAYS OFF THE HOST. Every case runs `install-node.sh --dry-run`,
# which by construction invokes no installer. On top of that each case
# prepends a scratch PATH of TRIPWIRES for every host-mutating tool the
# installers underneath would reach (`install`, `systemctl`, `apparmor_parser`,
# `kubectl`, `sysctl`, `mount`, `apt-get`, `helm`, `rm`): a run that executed a
# step would leave a MUTATING line in the tripwire file, which case C asserts
# it does not. The suite never runs as root and never needs to.
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
for tool in install apparmor_parser kubectl sysctl mount apt-get helm rm; do
  # Single-quoted on purpose: the body is the FAKE's source, expanded when the
  # fake runs, not when this suite writes it.
  printf '#!/usr/bin/env bash\nprintf "%%s %%s\\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"; exit 0\n' \
    > "${FAKEBIN}/${tool}"
  chmod +x "${FAKEBIN}/${tool}"
done

# The systemctl stub is the one fake with RETURN VALUES, because the runbook
# asks it two questions:
#   list-unit-files NAME  the presence probe deciding whether this node carries
#                         a stale server-only unit the skip has to remove.
#                         STUB_UNITS_PRESENT is the SPACE-SEPARATED list of
#                         names it answers yes for, rather than a boolean, so a
#                         case can put exactly the three timers gmktec was found
#                         carrying on the node and assert that the services
#                         beside them — which were NOT reported — are left out
#                         of the sequence;
#   is-failed NAME        the residual probe, asked of the units the first one
#                         did NOT report. STUB_UNITS_FAILED is the
#                         space-separated list it answers `failed` for; every
#                         other name draws `inactive` and a non-zero exit, as
#                         the real systemctl does.
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "%s %s\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"' \
  'if [ "${1:-}" = list-unit-files ]; then' \
  '  for stub_unit in ${STUB_UNITS_PRESENT:-}; do' \
  '    if [ "$stub_unit" = "${@: -1}" ]; then printf "%s enabled enabled\n" "$stub_unit"; fi' \
  '  done' \
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

# plan_lines OUTPUT -> the RUN/SKIP lines only, which ARE the step plan.
plan_lines() { printf '%s\n' "$1" | grep -E '^(RUN|SKIP) '; }

# command_lines OUTPUT -> the '+ ' command lines only, which ARE the sequence
# this run would execute. A plan that removes nothing has none at all.
command_lines() { printf '%s\n' "$1" | grep -E '^\+ ' || true; }

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
#
# ONE line has been re-worded since that transcription, and only re-worded:
# step 1 was "1/10 k3s server config" until livespec-dev-tooling-vcv4 gave the
# step a per-role FILE and put that filename in the label. The server's step 1
# still runs, still runs first, and still installs config.yaml plus the
# local-storage skip marker — the assertion below reads exactly that out of the
# line, so the wording change cannot hide a change of work.
# ---------------------------------------------------------------------------
read -r -d '' EXPECTED_SERVER_PLAN <<'EOF'
RUN  [server] 1/10 k3s config (server or agent) — installs k3s-config/config.yaml + the local-storage skip marker
SKIP [server] 1b/10 agent-rejoin liveness watchdog (agent only) — restarts a wedged k3s-agent so it re-registers after a control-plane datastore wipe
RUN  [server] 2/10 inotify instance budget + keyring quota
RUN  [server] 2b/10 storage layout (mount the LABEL-ed tiers + the five fstab lines + k3s drop-in; no-op when the tiers are live)
RUN  [server] 2c/10 iDRAC cooling configuration (racadm + fan loop automatic, third-party response off, Minimum Power profile)
RUN  [server] 2d/10 operator host tools (btop-loop into /usr/local/bin)
RUN  [server] 3/10 AppArmor profile + hook ConfigMap
RUN  [server] 4/10 churn-slot extended resource (capacity 32) + reapply timer
RUN  [server] 5/10 wedged-runner scan (clear)
RUN  [server] 5b/10 runner-pod lifecycle scan (report-only; no mode — see its installer's header)
RUN  [server] 6/10 ARC log archive
RUN  [server] 7/10 boot-time secret reinjection units — GitHub App + gate forge credential (enable only)
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

# Step 1 is FIRST and does the server work it always did: the server config file
# and the skip marker, both named in the line so a plan can be read for them.
SERVER_STEP1="$(printf '%s\n' "$SERVER_PLAN" | head -n 1)"
case "$SERVER_STEP1" in
  "RUN  [server] 1/10 k3s config"*"k3s-config/config.yaml"*"local-storage skip marker"*)
    ok "server step 1 is first and installs config.yaml + the local-storage skip marker" ;;
  *)
    no "server step 1 is first and installs config.yaml + the local-storage skip marker (got: ${SERVER_STEP1})" ;;
esac
case "$SERVER_STEP1" in
  *config.agent.yaml*) no "the server step-1 line must not name the agent file" ;;
  *) ok "the server step-1 line does not name the agent file" ;;
esac

# The one step a SERVER skips: the agent-only rejoin watchdog. Its reason must
# say WHY a server never wedges, the mirror of the agent skips' reasons, so the
# operator reads it from the plan rather than the source.
SERVER_REJOIN_REASON="$(printf '%s\n' "$REPLY_OUT" | grep -A1 -F 'SKIP [server] 1b/10 agent-rejoin' | tail -n 1)"
case "$SERVER_REJOIN_REASON" in
  "     reason: "*"never loses its own registration"*)
    ok "the server's agent-rejoin skip reason says why a server never wedges" ;;
  *)
    no "the server's agent-rejoin skip reason says why a server never wedges (got: ${SERVER_REJOIN_REASON})" ;;
esac

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

# The seven skipped steps, by the label fragment that identifies each. The
# reconstruct converge is the only step that applies Kueue ClusterQueues and
# ARC scale sets, so its absence is what omits Kueue and ARC from this plan.
# churn-slot (4/10) is NOT among them since R5: it installs a per-node reapply
# timer on an agent too (asserted as a RUN below).
for fragment in \
  "2c/10 iDRAC cooling configuration" \
  "5/10 wedged-runner scan" \
  "5b/10 runner-pod lifecycle scan" \
  "6/10 ARC log archive" \
  "7/10 boot-time secret reinjection units" \
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
if [ "$skip_count" -eq 7 ] && [ "$reason_count" -eq 7 ]; then
  ok "every one of the ${skip_count} skipped steps carries a logged reason"
else
  no "every skipped step carries a logged reason (skips=${skip_count} reasons=${reason_count})"
fi

# churn-slot RUNS on an agent since R5 (livespec-dev-tooling-xa6o): it installs a
# PER-NODE reapply timer (ordered against k3s-agent.service, patching this one
# node by name), so it is no longer the server-only step that once aborted the
# runbook at 4 of 10. It carries an agent NOTE naming the one prerequisite this
# runbook cannot satisfy from here — the node-status kubeconfig seed — so the
# operator reads the RUN and the caveat together.
if printf '%s\n' "$AGENT_PLAN" | grep -qF 'RUN  [agent] 4/10 churn-slot extended resource'; then
  ok "the agent plan RUNs churn-slot (per-node reapply timer), it no longer skips it"
else
  no "the agent plan RUNs churn-slot (per-node reapply timer)"
fi
CHURN_NOTE="$(printf '%s\n' "$AGENT_OUT" | grep -A1 -F 'RUN  [agent] 4/10 churn-slot extended resource' | tail -n 1)"
case "$CHURN_NOTE" in
  "     note: "*"node-status kubeconfig"*"seed-node-status-kubeconfig.sh"*)
    ok "the churn-slot agent note names the node-status kubeconfig seed prerequisite" ;;
  *)
    no "the churn-slot agent note names the node-status kubeconfig seed prerequisite (got: ${CHURN_NOTE})" ;;
esac

# The three cluster-wide sweeps are read the same way and for the same reason:
# 5/10 reported an armed timer over one that had landed `failed`, and 5b/10
# aborted the runbook at its own verify, taking steps 6..10 with it
# (livespec-dev-tooling-qcq0). Each reason has to name the SERVER's timer as
# what already performs the sweep for this node, or the operator reading the
# skip cannot tell an omission from a gap in coverage.
assert_skip_reason_names_server() {  # ... STEP-LABEL-FRAGMENT TIMER-NAME
  local fragment="$1" timer="$2" reason
  reason="$(printf '%s\n' "$AGENT_OUT" | grep -A1 -F "SKIP [agent] ${fragment}" | tail -n 1)"
  case "$reason" in
    "     reason: "*"SERVER's own ${timer}"*)
      ok "the ${fragment} skip reason names the server's ${timer}" ;;
    *)
      no "the ${fragment} skip reason names the server's ${timer} (got: ${reason})" ;;
  esac
}
assert_skip_reason_names_server "5/10 wedged-runner" "scan-wedged-runners.timer"
assert_skip_reason_names_server "5b/10 runner-pod lifecycle" "scan-runner-pod-lifecycle.timer"
assert_skip_reason_names_server "6/10 ARC log archive" "archive-arc-logs.timer"

# Nothing in the agent plan applies the cluster-side Kueue or ARC objects: the
# reconstruct converge is gone, and no other RUN line names either of them.
if printf '%s\n' "$AGENT_PLAN" | grep '^RUN ' | grep -qiE 'kueue|scale set|clusterqueue'; then
  no "no RUN step in the agent plan applies Kueue queues or ARC scale sets"
else
  ok "no RUN step in the agent plan applies Kueue queues or ARC scale sets"
fi

for fragment in \
  "1/10 k3s config (server or agent) — installs k3s-config/config.agent.yaml" \
  "1b/10 agent-rejoin liveness watchdog (agent only)" \
  "2/10 inotify instance budget + keyring quota" \
  "2b/10 storage layout" \
  "2d/10 operator host tools" \
  "3/10 AppArmor profile only (--profile-only;" \
  "4/10 churn-slot extended resource" \
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

# B2. Step 1 runs on BOTH roles, and the agent's line names the agent file and
# the marker it does NOT write. The server file on an agent is what killed
# k3s-agent on gmktec-xubuntu (livespec-dev-tooling-vcv4), so this plan is read
# for the filename, not merely for the step's presence.
AGENT_STEP1="$(printf '%s\n' "$AGENT_PLAN" | head -n 1)"
case "$AGENT_STEP1" in
  "RUN  [agent] 1/10 k3s config"*"k3s-config/config.agent.yaml"*"NO local-storage skip marker"*)
    ok "agent step 1 is first and installs config.agent.yaml with NO skip marker" ;;
  *)
    no "agent step 1 is first and installs config.agent.yaml with NO skip marker (got: ${AGENT_STEP1})" ;;
esac
case "$AGENT_STEP1" in
  *"k3s-config/config.yaml"*)
    no "the agent step-1 line must not name the SERVER's config.yaml" ;;
  *)
    ok "the agent step-1 line does not name the SERVER's config.yaml" ;;
esac

# B3. Step 1 is also where an agent's runtime can be disturbed, and the plan has
# to say what happens next. On gmktec-xubuntu 2026-09-07 this step replaced the
# agent config while k3s-agent.service was restart-looping; step 7c reached
# extract-externals.sh five seconds before containerd was serving and died at its
# first `ctr images pull` with `connect: connection refused`, so the runbook only
# "worked" on a second invocation (livespec-dev-tooling-4qp4). The agent's step-1
# line names the CHANGED-config condition, the unit and the socket it then waits
# for; the SERVER's does not, because a server's k3s is never disturbed here.
case "$AGENT_STEP1" in
  *CHANGED*"k3s-agent.service"*"containerd socket /run/k3s/containerd/containerd.sock"*)
    ok "agent step 1 says a changed config is followed by a wait for the unit and the containerd socket" ;;
  *)
    no "agent step 1 says a changed config is followed by a wait for the unit and the containerd socket (got: ${AGENT_STEP1})" ;;
esac
case "$SERVER_STEP1" in
  *"wait"*|*"containerd"*)
    no "the server step-1 line describes no wait (a server's k3s is not restarted here)" ;;
  *)
    ok "the server step-1 line describes no wait (a server's k3s is not restarted here)" ;;
esac

# The agent's steps stay in the server's relative order — the plan is a filter
# of the runbook, never a re-ordering of it. This comparison is about ORDER
# alone, so both the RUN/SKIP verb and the [role] tag are stripped from each
# side (a step the server SKIPs the agent RUNs, and vice-versa — 1b agent-rejoin
# is the one that flips), and the two steps whose LABEL differs by role (step
# 1's file, step 3's --profile-only) are normalized back to the server wording.
SERVER_ORDER="$(printf '%s\n' "$SERVER_PLAN" | sed -E 's/^(RUN|SKIP)  ?\[server\] //')"
AGENT_ORDER="$(printf '%s\n' "$AGENT_PLAN" \
  | sed -E 's/^(RUN|SKIP)  ?\[agent\] //' \
  | sed -E 's/^(3\/10) AppArmor profile only.*/\1 AppArmor profile + hook ConfigMap/' \
  | sed -E 's|^(1/10 k3s config \(server or agent\)).*|\1 — installs k3s-config/config.yaml + the local-storage skip marker|')"
if [ "$SERVER_ORDER" = "$AGENT_ORDER" ]; then
  ok "the agent plan is the server plan filtered, in the same order"
else
  no "the agent plan is the server plan filtered, in the same order"
  diff <(printf '%s\n' "$SERVER_ORDER") <(printf '%s\n' "$AGENT_ORDER") || true
fi

# ---------------------------------------------------------------------------
# C. --dry-run executed nothing.
#
# The tripwire is no longer expected EMPTY: the stale-unit presence probe and
# the is-failed probe beside it are READS, and both are performed under
# --dry-run on purpose so the removal sequence a dry run prints is the one this
# host actually needs (case E). What must be absent is every MUTATION.
# ---------------------------------------------------------------------------
printf '\n== C. --dry-run executes nothing ==\n'
if grep -qvE '^systemctl (list-unit-files|is-failed) ' "$TRIPWIRE"; then
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
# E. The agent SKIP removes the server-only units an earlier run left here.
#
# A skip is a statement about what this run will INSTALL; it says nothing about
# what an earlier run already put on the node, and because a skip never invokes
# the installer, the installer's own agent-side removal never runs on the node
# that actually has the units. gmktec-xubuntu 2026-09-07: a full runbook run
# exited 0 and left server-only timers `enabled`/`failed` with `Unit k3s.service
# not found` (livespec-dev-tooling-43sc). Since R5 the removable set is the three
# genuinely server-only steps — the two scans and the ARC log archive; the
# reapply timer is NOT removed here any more, because churn-slot installs it
# per-node on an agent (a separate assertion below proves it is LEFT).
# ---------------------------------------------------------------------------
printf '\n== E. the agent skip removes the stale server-only units ==\n'

UNIT_DIR="/etc/systemd/system"

# The three server-only timers a skipped step would remove. Their SERVICES are
# deliberately not in this stub's answer, so the assertion below also proves
# each unit is probed on its own rather than removed as a hard-coded pair.
GMKTEC_STALE_TIMERS="scan-wedged-runners.timer scan-runner-pod-lifecycle.timer archive-arc-logs.timer"

# The daemon-reload is not the last line: each removed unit is then cleared
# from systemd's failed list, in the same order it was removed. Deleting a unit
# file and reloading leaves the unit in `systemctl list-units --state=failed`
# as `not-found failed` until `reset-failed` runs or the host reboots
# (livespec-dev-tooling-oc5g).
IFS= read -r -d '' EXPECTED_TIMER_REMOVAL <<'EOF'
+ systemctl disable --now scan-wedged-runners.timer
+ rm -f /etc/systemd/system/scan-wedged-runners.timer
+ systemctl disable --now scan-runner-pod-lifecycle.timer
+ rm -f /etc/systemd/system/scan-runner-pod-lifecycle.timer
+ systemctl disable --now archive-arc-logs.timer
+ rm -f /etc/systemd/system/archive-arc-logs.timer
+ systemctl daemon-reload
+ systemctl reset-failed scan-wedged-runners.timer
+ systemctl reset-failed scan-runner-pod-lifecycle.timer
+ systemctl reset-failed archive-arc-logs.timer
EOF

# The whole set, for a node that carries both halves of all THREE skipped
# unit-installing steps. The TIMER precedes the service it triggers in every
# pair, so nothing can fire between the two removals, and ONE daemon-reload
# closes the set rather than one per installer — followed by one reset-failed
# per unit removed, in removal order.
IFS= read -r -d '' EXPECTED_FULL_REMOVAL <<'EOF'
+ systemctl disable --now scan-wedged-runners.timer
+ rm -f /etc/systemd/system/scan-wedged-runners.timer
+ systemctl disable --now scan-wedged-runners.service
+ rm -f /etc/systemd/system/scan-wedged-runners.service
+ systemctl disable --now scan-runner-pod-lifecycle.timer
+ rm -f /etc/systemd/system/scan-runner-pod-lifecycle.timer
+ systemctl disable --now scan-runner-pod-lifecycle.service
+ rm -f /etc/systemd/system/scan-runner-pod-lifecycle.service
+ systemctl disable --now archive-arc-logs.timer
+ rm -f /etc/systemd/system/archive-arc-logs.timer
+ systemctl disable --now archive-arc-logs.service
+ rm -f /etc/systemd/system/archive-arc-logs.service
+ systemctl daemon-reload
+ systemctl reset-failed scan-wedged-runners.timer
+ systemctl reset-failed scan-wedged-runners.service
+ systemctl reset-failed scan-runner-pod-lifecycle.timer
+ systemctl reset-failed scan-runner-pod-lifecycle.service
+ systemctl reset-failed archive-arc-logs.timer
+ systemctl reset-failed archive-arc-logs.service
EOF

# And the residual node: nothing installed, so nothing is disabled, no file is
# unlinked and systemd is NOT reloaded — there is no change for a reload to
# publish. The three timers the stub reports still failed are cleared, in the
# order the skip names them.
IFS= read -r -d '' EXPECTED_RESIDUAL_CLEAR <<'EOF'
+ systemctl reset-failed scan-wedged-runners.timer
+ systemctl reset-failed scan-runner-pod-lifecycle.timer
+ systemctl reset-failed archive-arc-logs.timer
EOF

# Exported, not a command prefix: the stub is a child process and reads it from
# the environment, and `VAR=x func` would leave it set for the whole suite.
export STUB_UNITS_PRESENT="$GMKTEC_STALE_TIMERS"
run_plan --dry-run "$AGENT_PROFILE"
unset STUB_UNITS_PRESENT
if [ "$REPLY_RC" -eq 0 ]; then
  ok "the agent dry run still exits 0 with stale units to remove"
else
  no "the agent dry run still exits 0 with stale units to remove (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi
same "the three server-only timers are disabled and removed, then one daemon-reload, then a reset-failed each" \
  "$EXPECTED_TIMER_REMOVAL" "$(command_lines "$REPLY_OUT")"

# Every unit named in that sequence, read back out of it so the stub and the
# expectation cannot disagree.
ALL_STALE_UNITS="$(printf '%s' "$EXPECTED_FULL_REMOVAL" \
  | sed -n -E 's/^\+ systemctl disable --now //p' | tr '\n' ' ')"

export STUB_UNITS_PRESENT="$ALL_STALE_UNITS"
run_plan --dry-run "$AGENT_PROFILE"
unset STUB_UNITS_PRESENT
same "both halves of all three skipped unit-installing steps go, timer before service, each reset-failed after the reload" \
  "$EXPECTED_FULL_REMOVAL" "$(command_lines "$REPLY_OUT")"

# THE R5 ASSERTION: even when the stub reports the reapply units present, the
# agent skip does NOT remove them — churn-slot installs the reapply timer
# per-node on an agent, so it is legitimate, not stale. A node carrying the
# reapply pair PLUS the three server-only steps removes only the latter.
export STUB_UNITS_PRESENT="reapply-node-extended-resource.timer reapply-node-extended-resource.service ${ALL_STALE_UNITS}"
run_plan --dry-run "$AGENT_PROFILE"
unset STUB_UNITS_PRESENT
if command_lines "$REPLY_OUT" | grep -qF 'reapply-node-extended-resource'; then
  no "the agent skip leaves the per-node reapply units alone (it removed a reapply unit)"
  command_lines "$REPLY_OUT" | grep -F 'reapply-node-extended-resource'
else
  ok "the agent skip leaves the per-node reapply units alone (churn-slot installs them)"
fi
same "with the reapply units present too, only the three server-only steps are removed" \
  "$EXPECTED_FULL_REMOVAL" "$(command_lines "$REPLY_OUT")"

# The other branch of the presence probe. It is only assertable on a host that
# does NOT have the units, and this suite is meant to be runnable on the pool's
# SERVER too — where they are installed, and where the probe is right to see
# them. So it is stated as a skip there rather than as a failure.
stale_unit_on_this_host=0
for unit in $(printf '%s\n' "$EXPECTED_FULL_REMOVAL" | grep -E '^\+ rm -f ' | sed -E 's|^\+ rm -f ||'); do
  [ -e "$unit" ] && stale_unit_on_this_host=1
done
if [ "$stale_unit_on_this_host" -eq 1 ]; then
  printf '  SKIP  no units present: this host has some installed, so the probe reads them\n'
else
  run_plan --dry-run "$AGENT_PROFILE"
  if [ "$REPLY_RC" -eq 0 ] && [ -z "$(command_lines "$REPLY_OUT")" ]; then
    ok "no stale unit present: the agent plan prints no removal line at all"
  else
    no "no stale unit present: the agent plan prints no removal line at all"
    command_lines "$REPLY_OUT"
  fi
  case "$REPLY_OUT" in
    *"nothing to remove"*) ok "the empty removal says so rather than staying silent" ;;
    *) no "the empty removal says so rather than staying silent" ;;
  esac

  # The RESIDUAL state, and the one this case was reopened for. gmktec-xubuntu
  # 2026-09-07 at tree c13617d0: the unit files had been deleted by the PREVIOUS
  # runbook run, so the presence probe reported nothing and the skip printed
  # `nothing to remove` — while `systemctl list-units --state=failed` still
  # listed the same three timers as `not-found failed`. A clear over the units
  # REMOVED IN THIS INVOCATION can never converge that node, because by then
  # there is nothing left to remove (livespec-dev-tooling-ssbg). What the REMOVE
  # header has to carry on such a node is the reset-failed lines.
  export STUB_UNITS_FAILED="$GMKTEC_STALE_TIMERS"
  run_plan --dry-run "$AGENT_PROFILE"
  unset STUB_UNITS_FAILED
  if [ "$REPLY_RC" -eq 0 ]; then
    ok "the agent dry run still exits 0 with only residual failed state to clear"
  else
    no "the agent dry run still exits 0 with only residual failed state to clear (got ${REPLY_RC})"
    printf '%s\n' "$REPLY_OUT"
  fi
  same "the units already gone but still failed are cleared, and nothing is disabled, unlinked or reloaded" \
    "$EXPECTED_RESIDUAL_CLEAR" "$(command_lines "$REPLY_OUT")"
  # UNDER THE REMOVE HEADER, not merely somewhere in the output: the header is
  # what tells an operator reading a runbook run which step these lines belong
  # to, and the removal is the last thing an agent plan does.
  if printf '%s\n' "$REPLY_OUT" \
       | sed -n '/^#### \[agent\] REMOVE /,$p' \
       | grep -qF '+ systemctl reset-failed scan-wedged-runners.timer'; then
    ok "the reset-failed lines are printed under the REMOVE header"
  else
    no "the reset-failed lines are printed under the REMOVE header"
    printf '%s\n' "$REPLY_OUT"
  fi
  case "$REPLY_OUT" in
    *"nothing to remove"*) no "a run that cleared something does not also say there was nothing to do" ;;
    *) ok "a run that cleared something does not also say there was nothing to do" ;;
  esac
fi

# A SERVER skips nothing, so it has nothing to clean up — even on a host where
# every one of these units is present, which is exactly the pool's server.
export STUB_UNITS_PRESENT="$ALL_STALE_UNITS"
run_plan --dry-run "$SERVER_PROFILE"
unset STUB_UNITS_PRESENT
if [ "$REPLY_RC" -eq 0 ] && [ -z "$(command_lines "$REPLY_OUT")" ]; then
  ok "a server prints no removal line even when every unit is reported present"
else
  no "a server prints no removal line even when every unit is reported present"
  command_lines "$REPLY_OUT"
fi

# The unit NAMES are stated in two places — the runbook's skip table and the
# installer that owns each unit — so they are compared here. A rename in one
# without the other would otherwise leave the skip removing a unit that no
# longer exists while the real one stayed enabled and failed, which is the
# defect this case exists for, wearing a different hat.
assert_installer_units_are_removed() {  # ... INSTALLER-PATH
  local installer="$1" declared unit
  declared="$(grep -E '^(SERVICE|TIMER)="[^"]+"$' "${HERE}/${installer}" | sed -E 's/^(SERVICE|TIMER)="([^"]+)"$/\2/')"
  if [ -z "$declared" ]; then
    no "${installer} declares a SERVICE and a TIMER this suite can read"
    return
  fi
  for unit in $declared; do
    if printf '%s\n' "$EXPECTED_FULL_REMOVAL" | grep -qF "+ rm -f ${UNIT_DIR}/${unit}"; then
      ok "the skip removes ${unit}, the unit ${installer} installs"
    else
      no "the skip removes ${unit}, the unit ${installer} installs"
    fi
  done
}
# NOT install-reapply-unit.sh: since R5 its reapply units install per-node on an
# agent (churn-slot runs, it does not skip), so they are legitimately absent from
# the skip-removal set the three genuinely server-only installers populate.
assert_installer_units_are_removed wedged-runner/install-wedged-runner-scan.sh
assert_installer_units_are_removed runner-pod-lifecycle/install-runner-pod-lifecycle-scan.sh
assert_installer_units_are_removed arc-log-archive/install-arc-log-archive.sh

# Case C again, now that every removal case has run: printing a removal is not
# performing one, and the only commands any of them reached are still the two
# reads.
if grep -qvE '^systemctl (list-unit-files|is-failed) ' "$TRIPWIRE"; then
  no "the removal dry runs executed no host-mutating command either"
  cat "$TRIPWIRE"
else
  ok "the removal dry runs executed no host-mutating command either"
fi

# ---------------------------------------------------------------------------
printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
