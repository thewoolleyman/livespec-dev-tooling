#!/usr/bin/env bash
# verify-installed-tree-exit-tests.sh — prove ./verify-installed-tree.sh detects the
# drift it exists to detect, and does NOT report drift that is not there
# (livespec-dev-tooling-fdse).
#
#   A. a tree staged straight from the installer verifies CLEAN and exits 0;
#   B. ONE BYTE changed in one installed file is reported STALE and exits 1 — the
#      case that actually occurred, where a host ran a converge from before the
#      gates queue existed and still exited Result=success;
#   C. a file DELETED from the installed tree is reported MISSING and exits 1;
#      "never installed" is exactly as stale as "installed and old", and the manifest
#      that started this was missing rather than outdated;
#   D. a FOREIGN file — one this installer does not ship — is counted and excluded
#      rather than reported, and does not fail the run. Other installers share this
#      root, and a check that cried wolf about their files would not survive being
#      run routinely;
#   E. `install-converge-unit.sh --stage-to` works WITHOUT root and stops before its
#      systemd steps, which is what lets the expected set be DERIVED from the real
#      installer instead of kept as a second list that can itself fall behind.
#
# Every tree here is built in this suite's own scratch directory and verified with
# --lib-dir, so no host is read and nothing is installed. Exit 0 iff all pass.
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
VERIFY="${SCRIPT_DIR}/verify-installed-tree.sh"
INSTALLER="${SCRIPT_DIR}/install-converge-unit.sh"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "${SCRATCH}"' EXIT

failures=0
pass() { echo "  PASS  $1"; }
fail() { echo "  FAIL  $1"; failures=$((failures + 1)); }

[ -x "${VERIFY}" ] || { echo "FATAL: ${VERIFY} not found or not executable" >&2; exit 1; }
[ -x "${INSTALLER}" ] || { echo "FATAL: ${INSTALLER} not found or not executable" >&2; exit 1; }

echo "== E. the installer stages rootless and stops before systemd =="
STAGED="${SCRATCH}/staged"
if out="$("${INSTALLER}" --stage-to "${STAGED}" 2>&1)"; then
  count="$(find "${STAGED}" -type f | wc -l)"
  if [ "${count}" -gt 0 ]; then
    pass "staged ${count} files as an unprivileged user"
  else
    fail "staging produced no files"
  fi
  if grep -qF "stopping before the systemd steps" <<< "${out}"; then
    pass "stopped before the systemd steps"
  else
    fail "did not report stopping before the systemd steps"
  fi
  if [ -e "${STAGED}/converge-ci-stack.service" ]; then
    fail "staged the unit file; staging must stop before the systemd steps"
  else
    pass "no systemd unit written by staging"
  fi
else
  fail "staging failed as an unprivileged user: ${out}"
fi

# The "installed tree" every case below verifies against: a copy of the staged tree.
TREE="${SCRATCH}/installed"
cp -a "${STAGED}" "${TREE}"

echo "== A. an unmodified tree verifies clean =="
if "${VERIFY}" --lib-dir "${TREE}" --quiet > "${SCRATCH}/a.log" 2>&1; then
  if grep -qF "0 stale, 0 missing" "${SCRATCH}/a.log"; then
    pass "clean tree reports 0 stale, 0 missing and exits 0"
  else
    fail "exited 0 but did not report a clean tally: $(tail -2 "${SCRATCH}/a.log")"
  fi
else
  fail "clean tree did not exit 0: $(tail -3 "${SCRATCH}/a.log")"
fi

echo "== B. one changed byte is STALE =="
victim="${TREE}/converge-ci-stack.sh"
printf '\n# drift introduced by the exit tests\n' >> "${victim}"
if "${VERIFY}" --lib-dir "${TREE}" --quiet > "${SCRATCH}/b.log" 2>&1; then
  fail "a modified file did NOT fail the check — the whole point of this script"
else
  if grep -qE '^STALE +converge-ci-stack\.sh' "${SCRATCH}/b.log"; then
    pass "the modified file is named as STALE and the run exits non-zero"
  else
    fail "exited non-zero but did not name the file STALE: $(head -3 "${SCRATCH}/b.log")"
  fi
fi
cp -a "${STAGED}/converge-ci-stack.sh" "${victim}"

echo "== C. a deleted file is MISSING =="
rm -f "${TREE}/gates/gates-rbac.yaml"
if "${VERIFY}" --lib-dir "${TREE}" --quiet > "${SCRATCH}/c.log" 2>&1; then
  fail "a deleted file did NOT fail the check"
else
  if grep -qE '^MISSING +gates/gates-rbac\.yaml' "${SCRATCH}/c.log"; then
    pass "the absent file is named as MISSING and the run exits non-zero"
  else
    fail "exited non-zero but did not name the file MISSING: $(head -3 "${SCRATCH}/c.log")"
  fi
fi
mkdir -p "${TREE}/gates"
cp -a "${STAGED}/gates/gates-rbac.yaml" "${TREE}/gates/gates-rbac.yaml"

echo "== D. a foreign file is excluded, not reported =="
mkdir -p "${TREE}/bin"
printf '#!/bin/sh\n# installed by some other installer\n' > "${TREE}/bin/some-host-tool"
if "${VERIFY}" --lib-dir "${TREE}" --quiet > "${SCRATCH}/d.log" 2>&1; then
  if grep -qF "shipped by other installers" "${SCRATCH}/d.log"; then
    pass "the foreign file is counted as out of scope and does not fail the run"
  else
    fail "exited 0 but did not account for the foreign file: $(tail -2 "${SCRATCH}/d.log")"
  fi
else
  fail "a foreign file FAILED the run; this check must not judge files it does not ship"
fi

echo
if [ "${failures}" -eq 0 ]; then
  echo "ALL TESTS PASSED"
  exit 0
fi
echo "${failures} TEST(S) FAILED"
exit 1
