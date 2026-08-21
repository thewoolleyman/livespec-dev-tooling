#!/usr/bin/env bash
# set-ci-runner-labels-exit-tests.sh — behavioral exit tests for the
# fork-exclusion precondition that `set-ci-runner-labels.sh` binds to the
# `CI_RUNNER_LABELS` write.
#
# WHY A FAKE `gh` AND NOT A LIVE REPOSITORY. The property under test is what the
# script REFUSES to do. Proving a refusal against live repositories would mean
# weakening a real repository's fork-approval tier to see the refusal fire --
# creating, for the duration of the test, exactly the exposure the script
# exists to prevent, on a repository whose merge gate runs on the shared runner
# host. So the GitHub surface is faked: a `gh` shim first on `PATH` that answers
# from environment variables and appends every invocation to a log, and the
# tests assert on that log. No network, no credential, no repository touched.
#
# WHAT EACH TEST PROVES, in one line each -- the refusals are the point, and the
# two permissive cases exist so a script that refused EVERYTHING would still
# fail this suite:
#
#   1  hosted-only target        -> writes, and never reads the tier at all
#   2  self-hosted + strict tier -> writes
#   3  self-hosted + weak tier   -> REFUSES, and writes nothing
#   4  self-hosted + tier unreadable -> REFUSES (fail-closed on not-knowing)
#   5  --set-tier on a weak tier -> raises the tier, verifies, then writes
#   6  --set-tier whose write "succeeds" but reads back weak -> REFUSES
#   7  --dry-run on a weak tier  -> REFUSES, writes nothing
#   8  --dry-run on a strict tier-> writes nothing
#   9  read-back mismatch        -> non-zero exit (the variable write is not
#                                   trusted either)
#  10  malformed label           -> rejected before any GitHub call
#
# Test 6 is the one worth reading twice. A tier write that reports success and
# still reads back weak leaves the repository in precisely the state the script
# refuses to create, so the script re-reads rather than trusting its own PUT.
# That is the same discipline the plan's own audit had to learn the hard way
# when a push reported success and landed nothing.
#
# Exit 0 iff every test passes. No arguments. Requires bash and nothing else.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/set-ci-runner-labels.sh"
[ -x "$SCRIPT" ] || { echo "FATAL: ${SCRIPT} not found or not executable" >&2; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
FAKE_BIN="${WORK}/bin"
mkdir -p "$FAKE_BIN"
GH_LOG="${WORK}/gh.log"

# ---------------------------------------------------------------------------
# The fake `gh`. Behavior is driven entirely by environment variables so each
# test composes a scenario without editing this file:
#
#   FAKE_TIER            value the tier read returns ("" plus FAKE_TIER_FAILS=1
#                        to simulate an unreadable tier)
#   FAKE_TIER_FAILS      when 1, the tier read exits 1 having written an error
#                        object to STDOUT -- gh's real 404/403 behavior, and the
#                        exact shape that defeats an emptiness test
#   FAKE_TIER_AFTER_PUT  value the tier read returns AFTER a PUT (defaults to
#                        FAKE_TIER, which is what test 6 exploits)
#   FAKE_READBACK        value the variable read-back returns (defaults to the
#                        value the fake was asked to write)
cat > "${FAKE_BIN}/gh" <<'FAKE_GH'
#!/usr/bin/env bash
set -uo pipefail
printf '%s\n' "$*" >> "$GH_LOG"

is_tier_path() { case "$1" in *fork-pr-contributor-approval*) return 0 ;; *) return 1 ;; esac; }

case "$1" in
  api)
    shift
    method="GET"
    path=""
    for arg in "$@"; do
      case "$arg" in
        PUT|POST|PATCH|DELETE) method="$arg" ;;
        repos/*) [ -z "$path" ] && path="$arg" ;;
      esac
    done
    if is_tier_path "$path"; then
      if [ "$method" = "PUT" ]; then
        touch "${GH_LOG}.tier-put"
        echo '{"approval_policy":"written"}'
        exit 0
      fi
      if [ -e "${GH_LOG}.tier-put" ] && [ -n "${FAKE_TIER_AFTER_PUT:-}" ]; then
        printf '%s\n' "$FAKE_TIER_AFTER_PUT"
        exit 0
      fi
      if [ "${FAKE_TIER_FAILS:-0}" = "1" ]; then
        # Real gh writes the error object to STDOUT and exits non-zero.
        echo '{"message":"Not Found","status":"404"}'
        exit 1
      fi
      printf '%s\n' "${FAKE_TIER:-}"
      exit 0
    fi
    # The CI_RUNNER_LABELS read-back.
    if [ -n "${FAKE_READBACK:-}" ]; then
      printf '%s\n' "$FAKE_READBACK"
    else
      cat "${GH_LOG}.written" 2>/dev/null || { echo '{"message":"Not Found"}'; exit 1; }
    fi
    exit 0
    ;;
  variable)
    shift
    body=""
    prev=""
    for arg in "$@"; do
      [ "$prev" = "--body" ] && body="$arg"
      prev="$arg"
    done
    printf '%s\n' "$body" > "${GH_LOG}.written"
    exit 0
    ;;
esac
echo "fake gh: unhandled invocation: $*" >&2
exit 3
FAKE_GH
chmod +x "${FAKE_BIN}/gh"

PASS=0
FAIL=0

reset_scenario() {
  : > "$GH_LOG"
  rm -f "${GH_LOG}.written" "${GH_LOG}.tier-put"
  unset FAKE_TIER FAKE_TIER_FAILS FAKE_TIER_AFTER_PUT FAKE_READBACK
}

# run_case <expected-exit> <description> -- <script args...>
run_case() {
  local expected="$1" desc="$2"
  shift 3
  local out status
  out="$(PATH="${FAKE_BIN}:${PATH}" GH_LOG="$GH_LOG" "$SCRIPT" "$@" 2>&1)"
  status=$?
  LAST_OUT="$out"
  if [ "$expected" = "nonzero" ]; then
    if [ "$status" -ne 0 ]; then return 0; fi
    printf 'FAIL: %s -- expected non-zero exit, got 0\n%s\n' "$desc" "$out" >&2
    return 1
  fi
  if [ "$status" -eq "$expected" ]; then return 0; fi
  printf 'FAIL: %s -- expected exit %s, got %s\n%s\n' "$desc" "$expected" "$status" "$out" >&2
  return 1
}

record() {
  local ok="$1" name="$2"
  if [ "$ok" -eq 0 ]; then
    PASS=$(( PASS + 1 ))
    printf 'ok   %s\n' "$name"
  else
    FAIL=$(( FAIL + 1 ))
    printf 'FAIL %s\n' "$name"
  fi
}

wrote_variable() { [ -e "${GH_LOG}.written" ]; }
read_the_tier()  { grep -q 'fork-pr-contributor-approval' "$GH_LOG"; }

# ---------------------------------------------------------------------------
# 1. Hosted-only target writes, and never reads the tier.
reset_scenario
ok=1
if run_case 0 "hosted-only write" -- thewoolleyman/example ubuntu-latest; then
  if wrote_variable && ! read_the_tier; then ok=0; else
    echo "  (wrote=$(wrote_variable && echo yes || echo no) tier-read=$(read_the_tier && echo yes || echo no))" >&2
  fi
fi
record "$ok" "1  hosted-only target writes without reading the tier"

# 2. Self-hosted target at the strict tier writes.
reset_scenario
export FAKE_TIER="all_external_contributors"
ok=1
if run_case 0 "strict tier write" -- thewoolleyman/example example-k3s; then
  if wrote_variable && read_the_tier; then ok=0; fi
fi
record "$ok" "2  self-hosted target at the strict tier writes"

# 3. Self-hosted target at a weak tier REFUSES and writes nothing.
reset_scenario
export FAKE_TIER="first_time_contributors"
ok=1
if run_case nonzero "weak tier refusal" -- thewoolleyman/example example-k3s; then
  if ! wrote_variable && printf '%s' "$LAST_OUT" | grep -q "REFUSING"; then ok=0; fi
fi
record "$ok" "3  self-hosted target at a weak tier refuses, writing nothing"

# 4. An UNREADABLE tier refuses -- fail-closed on not-knowing. The fake writes
#    gh's real error-object-on-STDOUT shape, so a script branching on emptiness
#    rather than exit status would sail past this one.
reset_scenario
export FAKE_TIER_FAILS=1
ok=1
if run_case nonzero "unreadable tier refusal" -- thewoolleyman/example example-k3s; then
  if ! wrote_variable && printf '%s' "$LAST_OUT" | grep -q "REFUSING"; then ok=0; fi
fi
record "$ok" "4  an unreadable tier refuses the write (fail-closed)"

# 5. --set-tier raises the tier, verifies it, then writes.
reset_scenario
export FAKE_TIER="first_time_contributors"
export FAKE_TIER_AFTER_PUT="all_external_contributors"
ok=1
if run_case 0 "--set-tier raise" -- thewoolleyman/example example-k3s --set-tier; then
  if wrote_variable && [ -e "${GH_LOG}.tier-put" ]; then ok=0; fi
fi
record "$ok" "5  --set-tier raises the tier and then writes"

# 6. --set-tier whose PUT reports success but still reads back weak REFUSES.
reset_scenario
export FAKE_TIER="first_time_contributors"
export FAKE_TIER_AFTER_PUT="first_time_contributors"
ok=1
if run_case nonzero "--set-tier unverified" -- thewoolleyman/example example-k3s --set-tier; then
  if ! wrote_variable && [ -e "${GH_LOG}.tier-put" ]; then ok=0; fi
fi
record "$ok" "6  --set-tier refuses when the tier still reads back weak"

# 7. --dry-run on a weak tier still refuses, and writes nothing.
reset_scenario
export FAKE_TIER="none"
ok=1
if run_case nonzero "--dry-run weak tier" -- thewoolleyman/example example-k3s --dry-run; then
  if ! wrote_variable; then ok=0; fi
fi
record "$ok" "7  --dry-run on a weak tier refuses"

# 8. --dry-run on a strict tier writes nothing.
reset_scenario
export FAKE_TIER="all_external_contributors"
ok=1
if run_case 0 "--dry-run strict tier" -- thewoolleyman/example example-k3s --dry-run; then
  if ! wrote_variable; then ok=0; fi
fi
record "$ok" "8  --dry-run on a strict tier writes nothing"

# 9. A read-back that disagrees with what was written exits non-zero.
reset_scenario
export FAKE_TIER="all_external_contributors"
export FAKE_READBACK='["something-else"]'
ok=1
if run_case nonzero "read-back mismatch" -- thewoolleyman/example example-k3s; then
  ok=0
fi
record "$ok" "9  a read-back mismatch exits non-zero"

# 10. A malformed label is rejected before any GitHub call is made.
reset_scenario
export FAKE_TIER="all_external_contributors"
ok=1
if run_case nonzero "malformed label" -- thewoolleyman/example 'bad"label'; then
  if [ ! -s "$GH_LOG" ] && ! wrote_variable; then ok=0; fi
fi
record "$ok" "10 a malformed label is rejected before any GitHub call"

# ---------------------------------------------------------------------------
printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
