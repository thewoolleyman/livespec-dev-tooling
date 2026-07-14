#!/usr/bin/env bash
# trigger-surface-exit-tests.sh — prove the gate lane's trust boundary.
#
# The contained CI lane's containment is provable by confining the runner
# (../isolation-exit-tests.sh). The gate runner is PRIVILEGED by design, so its
# containment is a different claim entirely: *nothing untrusted can ever reach it*.
# These tests prove exactly that claim, and nothing weaker.
#
# The discrimination under test is that a runner LABEL is merely a request any
# workflow may write, so the label can never be the boundary; the supervisor must
# inspect the WORKFLOW IDENTITY and the EVENT before granting privileged compute.
#
# Exit 0 iff every non-skipped test passes. Re-runnable; mutates nothing durable
# (the polkit probe installs and removes one inert /bin/true unit).
set -uo pipefail

SUP="${GATE_RUNNER_SUPERVISOR:-/usr/local/lib/ci-runner/gate-runner-supervisor.sh}"
[ -x "$SUP" ] || SUP="$(cd "$(dirname "$0")" && pwd)/gate-runner-supervisor.sh"
GATE_REPO="${GATE_RUNNER_REPO:-thewoolleyman/livespec-orchestrator-beads-fabro}"
WF=".github/workflows/acceptance-live-golden-master.yml"

pass=0; fail=0; skip=0
ok()   { printf '  PASS  %s\n' "$1"; pass=$((pass+1)); }
no()   { printf '  FAIL  %s\n' "$1"; fail=$((fail+1)); }
sk()   { printf '  SKIP  %s (%s)\n' "$1" "$2"; skip=$((skip+1)); }

# Feed a synthetic `GET /actions/runs` payload to the supervisor's trust filter and
# report which run id (if any) it would mint a privileged runner for.
selects() { printf '%s' "$1" | "$SUP" --select-trusted; }

run() {  # run <name> <expected-id-or-empty> <payload>
  local name="$1" want="$2" got
  got="$(selects "$3")"
  if [ "$got" = "$want" ]; then ok "$name"; else
    no "$name — expected '[${want}]', got '[${got}]'"
  fi
}

wfrun() {  # wfrun <id> <event> <path> <head_branch>
  jq -nc --arg id "$1" --arg e "$2" --arg p "$3" --arg b "$4" \
    '{id:($id|tonumber), event:$e, path:$p, head_branch:$b}'
}
payload() { local IFS=,; jq -nc --argjson r "[$*]" '{workflow_runs:$r}'; }  # IFS=, so multi-run payloads are valid JSON

echo "== Trust-filter tests: what may obtain a privileged runner =="

run "T1  repository_dispatch on the gate workflow, master -> MINTS" \
  "101" "$(payload "$(wfrun 101 repository_dispatch "$WF" master)")"

run "T2  workflow_dispatch (operator, write-gated) on master -> MINTS" \
  "102" "$(payload "$(wfrun 102 workflow_dispatch "$WF" master)")"

run "T3  fork pull_request on the gate workflow -> NEVER mints" \
  "" "$(payload "$(wfrun 103 pull_request "$WF" attacker-branch)")"

# The sharp one: a fork may name its head branch "master". If the branch check were
# the only guard, this would slip through. The EVENT check is what stops it.
run "T4  fork pull_request whose head_branch is literally 'master' -> NEVER mints" \
  "" "$(payload "$(wfrun 104 pull_request "$WF" master)")"

run "T5  trusted event but a DIFFERENT workflow (ci.yml) -> NEVER mints" \
  "" "$(payload "$(wfrun 105 workflow_dispatch .github/workflows/ci.yml master)")"

run "T6  gate workflow, trusted event, but NOT master -> NEVER mints" \
  "" "$(payload "$(wfrun 106 workflow_dispatch "$WF" some-branch)")"

run "T7  schedule event on the gate workflow -> NEVER mints" \
  "" "$(payload "$(wfrun 107 schedule "$WF" master)")"

run "T8  empty queue -> mints nothing" "" '{"workflow_runs":[]}'

run "T9  untrusted run queued FIRST, trusted second -> mints ONLY the trusted one" \
  "110" "$(payload "$(wfrun 109 pull_request "$WF" master)" "$(wfrun 110 repository_dispatch "$WF" master)")"

echo
echo "== Live host tests =="

# T10 — the core standing claim: with nothing trusted queued, NO privileged runner
# is registered on the gate repo. A job cannot claim a runner that does not exist.
# T11 needs root and T10 needs the OPERATOR's gh credentials, so under sudo we reach
# back to the operator for the GitHub probes — that way ONE run covers the whole
# suite instead of forcing a sudoed and an unsudoed pass.
OPERATOR="${GATE_RUNNER_OPERATOR:-ubuntu}"
ghq() {
  if [ "$(id -u)" = 0 ]; then sudo -n -u "$OPERATOR" gh "$@"; else gh "$@"; fi
}
if ! command -v gh >/dev/null 2>&1 || ! ghq auth status >/dev/null 2>&1; then
  # An absent probe is not a breached invariant — SKIP, never a false red.
  sk "T10 no privileged runner idles" "gh absent or unauthenticated"
else
  n="$(ghq api "repos/${GATE_REPO}/actions/runners" --jq '[.runners[]?|select(.labels[].name=="livespec-orchestrator")]|length' 2>/dev/null)"
  q="$(ghq api "repos/${GATE_REPO}/actions/runs?status=queued&per_page=50" --jq '[.workflow_runs[]?|select(.path==".github/workflows/acceptance-live-golden-master.yml")]|length' 2>/dev/null)"
  if [ "${q:-0}" != "0" ]; then
    sk "T10 no privileged runner idles" "a gate run is queued right now (q=$q)"
  elif [ "${n:-x}" = "0" ]; then
    ok "T10 no gate run queued => ZERO privileged runners registered"
  else
    no "T10 a privileged runner is registered with nothing queued (n=${n:-?})"
  fi
fi

# T11 — the polkit bridge is narrow: ci-sup may start gate-runner@*.service and
# NOTHING else. Probed with an inert /bin/true unit that is removed afterwards.
if [ "$(id -u)" = 0 ] && id ci-sup >/dev/null 2>&1; then
  probe=/etc/systemd/system/gate-runner-polkit-probe.service
  printf '[Unit]\nDescription=inert polkit probe\n[Service]\nType=oneshot\nExecStart=/bin/true\n' > "$probe"
  systemctl daemon-reload
  if sudo -n -u ci-sup systemctl start gate-runner-polkit-probe.service >/dev/null 2>&1; then
    no "T11 ci-sup started a NON gate-runner@ unit (polkit rule is too broad)"
  else
    ok "T11 ci-sup cannot start units outside gate-runner@*.service"
  fi
  rm -f "$probe"; systemctl daemon-reload
else
  sk "T11 polkit bridge is narrow" "needs root + ci-sup"
fi

echo
printf 'gate trigger-surface: %d pass / %d fail / %d skip\n' "$pass" "$fail" "$skip"
[ "$fail" -eq 0 ]
