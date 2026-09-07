#!/usr/bin/env bash
# remove-server-only-units-exit-tests.sh — prove ./remove-server-only-units.sh
# clears the FAILED state of every unit it removes, WITHOUT touching any host.
#
# The defect this suite exists for: deleting a unit file and reloading systemd
# does NOT take the unit out of `systemctl list-units --state=failed`. systemd
# keeps the failed state in the manager and reports the deleted unit there as
# `not-found failed` until `systemctl reset-failed` runs or the host reboots.
# The stage-4 re-run on gmktec-xubuntu 2026-09-07 exited 0, removed all six
# unit files, `is-enabled` said `not-found` for each — and three timers were
# still listed failed, so a failed-units read on that agent stayed red
# (livespec-dev-tooling-oc5g).
#
#   A. --dry-run over three timers and the three services they trigger prints
#      the removal pairs, ONE daemon-reload, and then one
#      `+ systemctl reset-failed UNIT` per unit removed, in removal order;
#   B. a unit the presence probe does not report is removed AND reset-failed
#      not at all -- the reset-failed pass is over the units actually removed,
#      not over the units named;
#   C. nothing present at all: no command line whatsoever, and the run says so;
#   D. the LIVE path (no --dry-run) exits 0 when `reset-failed` exits non-zero,
#      which is what a unit systemd no longer knows returns. A cleanup must not
#      fail on the clearing of a failed state that was already clear.
#
# HOW IT STAYS OFF THE HOST. Every host-mutating tool the script reaches for is
# replaced by a tripwire on a scratch PATH, and `systemctl` is stubbed so both
# branches of the presence probe are reachable off a host that has none of
# these units. Cases A-C are dry runs, which by construction execute nothing.
# Case D is the one case that runs the LIVE path, so it wears three belts:
# `rm` and `systemctl` are stubs; `id` is stubbed too, because the live path
# refuses to run as non-root and this suite must not need to BE root; and the
# units it names are FIXTURE names no node carries, asserted absent from
# /etc/systemd/system before the case runs — so a stub that somehow failed to
# be picked up would still be pointed at nothing. The case then asserts that
# not one command it executed named a real unit.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/remove-server-only-units.sh"
UNIT_DIR="/etc/systemd/system"

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
# Single-quoted on purpose: the body is the FAKE's source, expanded when the
# fake runs, not when this suite writes it.
printf '#!/usr/bin/env bash\nprintf "%%s %%s\\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"; exit 0\n' \
  > "${FAKEBIN}/rm"
chmod +x "${FAKEBIN}/rm"

# `id` is a fake so case D can drive the script's REAL path without running this
# suite as root. It answers the one question the script asks it — `id -u` — and
# nothing else, so it cannot make any other decision come out differently. Only
# the live path asks it at all, which is why cases A-C leave no `id` line in the
# tripwire.
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "%s %s\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"' \
  'if [ "${1:-}" = -u ]; then printf "0\n"; fi' \
  'exit 0' \
  > "${FAKEBIN}/id"
chmod +x "${FAKEBIN}/id"

# The systemctl stub is the one fake with a RETURN VALUE, because the script
# asks it a question: `list-unit-files NAME` is the presence probe deciding
# whether this node carries the unit at all. STUB_UNITS_PRESENT is the
# SPACE-SEPARATED list of names it answers yes for, rather than a boolean, so a
# case can report some of the named units and assert the others are left out of
# the sequence entirely. STUB_RESET_FAILED_RC is what `reset-failed` exits with,
# so case D can reproduce the unit-systemd-no-longer-knows answer.
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "%s %s\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"' \
  'if [ "${1:-}" = list-unit-files ]; then' \
  '  for stub_unit in ${STUB_UNITS_PRESENT:-}; do' \
  '    if [ "$stub_unit" = "${@: -1}" ]; then printf "%s enabled enabled\n" "$stub_unit"; fi' \
  '  done' \
  'fi' \
  'if [ "${1:-}" = reset-failed ]; then exit "${STUB_RESET_FAILED_RC:-0}"; fi' \
  'exit 0' \
  > "${FAKEBIN}/systemctl"
chmod +x "${FAKEBIN}/systemctl"

run_remove() {  # run_remove ARGS... -> stdout+stderr in REPLY_OUT, code in REPLY_RC
  REPLY_OUT="$(PATH="${FAKEBIN}:${PATH}" "$SCRIPT" "$@" 2>&1)"
  REPLY_RC=$?
}

# command_lines OUTPUT -> the '+ ' command lines only, which ARE the sequence
# this run would execute. A run that removes nothing has none at all.
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

# Exactly the six units install-node.sh's agent skip hands this script for the
# three timers gmktec-xubuntu was found carrying, in the order it hands them:
# each timer immediately before the service it triggers.
GMKTEC_UNITS=(
  reapply-node-extended-resource.timer
  reapply-node-extended-resource.service
  scan-wedged-runners.timer
  scan-wedged-runners.service
  scan-runner-pod-lifecycle.timer
  scan-runner-pod-lifecycle.service
)

# ---------------------------------------------------------------------------
# A. Every unit removed is then cleared from systemd's failed list.
# ---------------------------------------------------------------------------
IFS= read -r -d '' EXPECTED_FULL <<'EOF'
+ systemctl disable --now reapply-node-extended-resource.timer
+ rm -f /etc/systemd/system/reapply-node-extended-resource.timer
+ systemctl disable --now reapply-node-extended-resource.service
+ rm -f /etc/systemd/system/reapply-node-extended-resource.service
+ systemctl disable --now scan-wedged-runners.timer
+ rm -f /etc/systemd/system/scan-wedged-runners.timer
+ systemctl disable --now scan-wedged-runners.service
+ rm -f /etc/systemd/system/scan-wedged-runners.service
+ systemctl disable --now scan-runner-pod-lifecycle.timer
+ rm -f /etc/systemd/system/scan-runner-pod-lifecycle.timer
+ systemctl disable --now scan-runner-pod-lifecycle.service
+ rm -f /etc/systemd/system/scan-runner-pod-lifecycle.service
+ systemctl daemon-reload
+ systemctl reset-failed reapply-node-extended-resource.timer
+ systemctl reset-failed reapply-node-extended-resource.service
+ systemctl reset-failed scan-wedged-runners.timer
+ systemctl reset-failed scan-wedged-runners.service
+ systemctl reset-failed scan-runner-pod-lifecycle.timer
+ systemctl reset-failed scan-runner-pod-lifecycle.service
EOF

printf '== A. three timers and their services: removed, one reload, then a reset-failed each ==\n'
# Exported, not a command prefix: the stub is a child process and reads it from
# the environment, and `VAR=x func` would leave it set for the whole suite.
export STUB_UNITS_PRESENT="${GMKTEC_UNITS[*]}"
run_remove --dry-run "${GMKTEC_UNITS[@]}"
unset STUB_UNITS_PRESENT
if [ "$REPLY_RC" -eq 0 ]; then
  ok "the dry run exits 0 with six units to remove"
else
  no "the dry run exits 0 with six units to remove (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi
same "the reload is followed by one reset-failed per unit, in removal order" \
  "$EXPECTED_FULL" "$(command_lines "$REPLY_OUT")"

# Stated as its own assertion rather than left implicit in the block above: the
# ORDER of the two phases is the whole point. reset-failed before the reload
# would clear a state systemd is about to recompute from a file it still knows.
RELOAD_AT="$(command_lines "$REPLY_OUT" | grep -n '^+ systemctl daemon-reload$' | cut -d: -f1)"
FIRST_RESET_AT="$(command_lines "$REPLY_OUT" | grep -n '^+ systemctl reset-failed ' | head -1 | cut -d: -f1)"
if [ -n "$RELOAD_AT" ] && [ -n "$FIRST_RESET_AT" ] && [ "$FIRST_RESET_AT" -gt "$RELOAD_AT" ]; then
  ok "every reset-failed comes AFTER the single daemon-reload"
else
  no "every reset-failed comes AFTER the single daemon-reload (reload ${RELOAD_AT:-none}, first reset ${FIRST_RESET_AT:-none})"
fi

# ---------------------------------------------------------------------------
# B. The reset-failed pass is over the units REMOVED, not the units NAMED.
#
# The three services are named on the command line and are NOT reported by the
# probe, exactly as gmktec was found: three timers present, their services
# already gone.
# ---------------------------------------------------------------------------
IFS= read -r -d '' EXPECTED_TIMERS_ONLY <<'EOF'
+ systemctl disable --now reapply-node-extended-resource.timer
+ rm -f /etc/systemd/system/reapply-node-extended-resource.timer
+ systemctl disable --now scan-wedged-runners.timer
+ rm -f /etc/systemd/system/scan-wedged-runners.timer
+ systemctl disable --now scan-runner-pod-lifecycle.timer
+ rm -f /etc/systemd/system/scan-runner-pod-lifecycle.timer
+ systemctl daemon-reload
+ systemctl reset-failed reapply-node-extended-resource.timer
+ systemctl reset-failed scan-wedged-runners.timer
+ systemctl reset-failed scan-runner-pod-lifecycle.timer
EOF

printf '\n== B. only the units actually removed are reset-failed ==\n'
export STUB_UNITS_PRESENT="reapply-node-extended-resource.timer scan-wedged-runners.timer scan-runner-pod-lifecycle.timer"
run_remove --dry-run "${GMKTEC_UNITS[@]}"
unset STUB_UNITS_PRESENT
same "a named unit the probe does not report is neither removed nor reset-failed" \
  "$EXPECTED_TIMERS_ONLY" "$(command_lines "$REPLY_OUT")"

# ---------------------------------------------------------------------------
# C. Nothing present: nothing printed, and the run says so.
#
# Only assertable on a host that does NOT carry these units, and this suite is
# meant to be runnable on the pool's SERVER too — where they are installed, and
# where the probe is right to see them. So it is stated as a skip there rather
# than as a failure.
# ---------------------------------------------------------------------------
printf '\n== C. nothing present: no command line at all ==\n'
unit_on_this_host=0
for unit in "${GMKTEC_UNITS[@]}"; do
  [ -e "${UNIT_DIR}/${unit}" ] && unit_on_this_host=1
done
if [ "$unit_on_this_host" -eq 1 ]; then
  printf '  SKIP  nothing present: this host has some installed, so the probe reads them\n'
else
  run_remove --dry-run "${GMKTEC_UNITS[@]}"
  if [ "$REPLY_RC" -eq 0 ] && [ -z "$(command_lines "$REPLY_OUT")" ]; then
    ok "no unit present: not one removal or reset-failed line is printed"
  else
    no "no unit present: not one removal or reset-failed line is printed"
    command_lines "$REPLY_OUT"
  fi
  case "$REPLY_OUT" in
    *"nothing to remove"*) ok "the empty removal says so rather than staying silent" ;;
    *) no "the empty removal says so rather than staying silent" ;;
  esac
fi

# Everything above is a dry run, so the only command any of them may have
# reached is the read-only presence probe.
if grep -qvE '^systemctl list-unit-files ' "$TRIPWIRE"; then
  no "the dry runs executed no host-mutating command"
  cat "$TRIPWIRE"
else
  ok "the dry runs executed no host-mutating command"
fi

# ---------------------------------------------------------------------------
# D. The LIVE path survives a reset-failed that fails.
#
# `systemctl reset-failed` on a unit the manager no longer knows exits
# non-zero, and a unit that was removed but never failed is exactly that case.
# Under `set -e` an untolerated non-zero there would abort the cleanup after
# the files were already deleted — a partial removal reported as a failure.
#
# Fixture unit names, not the real ones: this is the one case that runs the
# live path, and a name no node carries means even an escaped `rm` tripwire
# would be pointed at a file that does not exist.
# ---------------------------------------------------------------------------
printf '\n== D. live path: a failing reset-failed does not fail the run ==\n'
FIXTURE_UNITS=(oc5g-fixture.timer oc5g-fixture.service)

for unit in "${FIXTURE_UNITS[@]}"; do
  if [ -e "${UNIT_DIR}/${unit}" ]; then
    echo "FATAL: ${UNIT_DIR}/${unit} exists -- this suite's fixture name is supposed to name nothing" >&2
    exit 1
  fi
done

IFS= read -r -d '' EXPECTED_LIVE <<'EOF'
+ systemctl disable --now oc5g-fixture.timer
+ rm -f /etc/systemd/system/oc5g-fixture.timer
+ systemctl disable --now oc5g-fixture.service
+ rm -f /etc/systemd/system/oc5g-fixture.service
+ systemctl daemon-reload
+ systemctl reset-failed oc5g-fixture.timer
+ systemctl reset-failed oc5g-fixture.service
EOF

export STUB_UNITS_PRESENT="${FIXTURE_UNITS[*]}"
export STUB_RESET_FAILED_RC=1
run_remove "${FIXTURE_UNITS[@]}"
unset STUB_UNITS_PRESENT STUB_RESET_FAILED_RC
if [ "$REPLY_RC" -eq 0 ]; then
  ok "the live run exits 0 though every reset-failed exited non-zero"
else
  no "the live run exits 0 though every reset-failed exited non-zero (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi
same "the live run performed the whole sequence, reset-failed included" \
  "$EXPECTED_LIVE" "$(command_lines "$REPLY_OUT")"
for unit in "${FIXTURE_UNITS[@]}"; do
  case "$REPLY_OUT" in
    *"reset-failed found no ${unit} to clear"*)
      ok "the tolerated failure is reported for ${unit}, not swallowed" ;;
    *)
      no "the tolerated failure is reported for ${unit}, not swallowed" ;;
  esac
done

# The live run is allowed to reach the mutating stubs — that is what makes it
# live — but only ever through them: nothing it ran may name a real unit.
if grep -qE 'reapply-node-extended-resource|scan-wedged-runners|scan-runner-pod-lifecycle|archive-arc-logs' \
     <(grep -vE '^systemctl list-unit-files ' "$TRIPWIRE"); then
  no "the live run named only fixture units in the commands it executed"
  cat "$TRIPWIRE"
else
  ok "the live run named only fixture units in the commands it executed"
fi

# ---------------------------------------------------------------------------
printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
