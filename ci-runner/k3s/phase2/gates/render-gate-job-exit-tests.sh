#!/usr/bin/env bash
# render-gate-job-exit-tests.sh — prove ./render-gate-job.sh and
# ./gate-job-template.yaml carry every requirement R4.S5
# (livespec-dev-tooling-sk8f) names, WITHOUT contacting a cluster or reading any
# real repository:
#
#   A. the image is READ FROM THE GATED REPOSITORY's own workflow, not baked in —
#      two fixture repos declaring DIFFERENT tags render their own tag each, which
#      is the assertion a hardcoded constant could not pass;
#   B. a repository whose workflow declares SEVERAL distinct container images is
#      REFUSED rather than guessed at;
#   C. a repository with no ci.yml is refused;
#   D. a rendered manifest carries all nine requirements;
#   E. a template with the TOLERATION REMOVED is caught by that same check — so
#      D is proven to be load-bearing rather than vacuously true;
#   F. a template carrying an unsubstituted placeholder is refused at render time;
#   G. a --tree-hash that is not lowercase hex is refused, because the value goes
#      into both an object name and a label;
#   H. the cache environment matches ../arc/hook-pod-template.yaml, so the reuse
#      requirement 5 asks for cannot silently drift into a re-invention.
#
# HOW IT STAYS OFF THE CLUSTER AND OFF REAL REPOS. Every repository this suite
# renders against is a fixture tree it creates under its own scratch directory,
# carrying a hand-written .github/workflows/ci.yml. Nothing is applied, and
# render-gate-job.sh contacts nothing by construction.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RENDERER="${SCRIPT_DIR}/render-gate-job.sh"
TEMPLATE="${SCRIPT_DIR}/gate-job-template.yaml"
HOOK_POD_TEMPLATE="${SCRIPT_DIR}/../arc/hook-pod-template.yaml"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "${SCRATCH}"' EXIT

HASH_A="aaaabbbbccccddddeeeeffff0000111122223333"
HASH_B="99998888777766665555444433332222aaaabbbb"

failures=0
pass() { echo "  PASS  $1"; }
fail() { echo "  FAIL  $1"; failures=$((failures + 1)); }

[ -x "${RENDERER}" ] || { echo "FATAL: ${RENDERER} not found or not executable" >&2; exit 1; }
[ -f "${TEMPLATE}" ] || { echo "FATAL: ${TEMPLATE} not found" >&2; exit 1; }
[ -f "${HOOK_POD_TEMPLATE}" ] || { echo "FATAL: ${HOOK_POD_TEMPLATE} not found" >&2; exit 1; }

# --- fixture repositories -----------------------------------------------------
make_repo() {
  # make_repo <dir> <image> [<second image>]
  local dir="$1" img="$2" img2="${3:-}"
  mkdir -p "${dir}/.github/workflows"
  {
    printf 'jobs:\n  one:\n    runs-on: self-hosted\n    container:\n      image: %s\n    env:\n      X: y\n' "${img}"
    [ -n "${img2}" ] && printf '  two:\n    runs-on: self-hosted\n    container:\n      image: %s\n' "${img2}"
  } > "${dir}/.github/workflows/ci.yml"
}
IMG_A="ghcr.io/example/sandbox:python-v1.11.1"
IMG_B="ghcr.io/example/sandbox:python-v2.22.2"
make_repo "${SCRATCH}/repo-a" "${IMG_A}"
make_repo "${SCRATCH}/repo-b" "${IMG_B}"
make_repo "${SCRATCH}/repo-multi" "${IMG_A}" "${IMG_B}"
mkdir -p "${SCRATCH}/repo-none"

# --- the requirement check, used by BOTH case D and case E --------------------
# Returns 0 iff the rendered manifest at $1 carries all nine requirements.
# Prints the name of each requirement it finds missing.
check_requirements() {
  local f="$1" missing=0
  grep -qE '^\s+image: ghcr\.io/' "$f"                          || { echo "    missing: 1 image"; missing=1; }
  grep -qF 'args: ["just check"]' "$f"                          || { echo "    missing: 2 just check command"; missing=1; }
  grep -qE '^\s+cpu: "[0-9]+"' "$f"                             || { echo "    missing: 3 cpu request"; missing=1; }
  grep -qE '^\s+memory: "[0-9]+[GM]i"' "$f"                     || { echo "    missing: 3 memory request"; missing=1; }
  grep -qF 'name: LIVESPEC_TEST_PARALLELISM' "$f"               || { echo "    missing: 4 parallelism"; missing=1; }
  grep -qF 'SCCACHE_REDIS_RW_MODE' "$f"                         || { echo "    missing: 5 cache env"; missing=1; }
  grep -qF 'kueue.x-k8s.io/queue-name: gates-lq' "$f"           || { echo "    missing: 6 queue-name"; missing=1; }
  grep -qF 'key: node-role/ci' "$f"                             || { echo "    missing: 7 toleration"; missing=1; }
  grep -qF 'gmktec-xubuntu' "$f"                                || { echo "    missing: 7 node affinity"; missing=1; }
  grep -qE '^\s+ttlSecondsAfterFinished: [0-9]+' "$f"           || { echo "    missing: 8 ttl"; missing=1; }
  return "${missing}"
}

echo "== A. the image comes from the GATED repository's own workflow =="
out_a="${SCRATCH}/a.yaml"; out_b="${SCRATCH}/b.yaml"
if "${RENDERER}" --repo-root "${SCRATCH}/repo-a" --tree-hash "${HASH_A}" > "${out_a}" 2>"${SCRATCH}/a.err" &&
   "${RENDERER}" --repo-root "${SCRATCH}/repo-b" --tree-hash "${HASH_B}" > "${out_b}" 2>"${SCRATCH}/b.err"; then
  if grep -qF "${IMG_A}" "${out_a}" && ! grep -qF "${IMG_B}" "${out_a}"; then
    pass "repo-a renders its OWN tag and not repo-b's"
  else
    fail "repo-a rendered the wrong image"
  fi
  if grep -qF "${IMG_B}" "${out_b}" && ! grep -qF "${IMG_A}" "${out_b}"; then
    pass "repo-b renders its OWN tag and not repo-a's"
  else
    fail "repo-b rendered the wrong image"
  fi
else
  fail "renderer failed on a well-formed fixture: $(cat "${SCRATCH}/a.err" "${SCRATCH}/b.err")"
fi

echo "== B. several distinct container images are refused, not guessed =="
if "${RENDERER}" --repo-root "${SCRATCH}/repo-multi" --tree-hash "${HASH_A}" >/dev/null 2>"${SCRATCH}/multi.err"; then
  fail "a repo with two distinct images rendered instead of refusing"
else
  if grep -qF 'Refusing to guess' "${SCRATCH}/multi.err"; then
    pass "two distinct images refused, and the refusal says why"
  else
    fail "refused but without naming the cause: $(cat "${SCRATCH}/multi.err")"
  fi
fi

echo "== C. a repository with no ci.yml is refused =="
if "${RENDERER}" --repo-root "${SCRATCH}/repo-none" --tree-hash "${HASH_A}" >/dev/null 2>&1; then
  fail "a repo with no workflow rendered"
else
  pass "missing workflow refused"
fi

echo "== D. a rendered manifest carries all nine requirements =="
if check_requirements "${out_a}"; then
  pass "all nine requirements present"
else
  fail "rendered manifest is missing a requirement (listed above)"
fi

echo "== E. removing the toleration is CAUGHT by that same check =="
# Proves case D is load-bearing: with the toleration stripped from the template,
# the very check that passed above must fail, and must name requirement 7.
mutant="${SCRATCH}/mutant-template.yaml"
sed '/- key: node-role\/ci/,+3d' "${TEMPLATE}" > "${mutant}"
if [ "$(grep -c 'key: node-role/ci' "${mutant}")" -ne 0 ]; then
  fail "could not build the no-toleration mutant template"
else
  mut_out="${SCRATCH}/mutant.yaml"
  if GATE_JOB_TEMPLATE="${mutant}" "${RENDERER}" --repo-root "${SCRATCH}/repo-a" \
       --tree-hash "${HASH_A}" > "${mut_out}" 2>/dev/null; then
    if check_requirements "${mut_out}" > "${SCRATCH}/mut.report" 2>&1; then
      fail "the no-toleration manifest PASSED the requirement check — case D is vacuous"
    else
      if grep -qF 'missing: 7 toleration' "${SCRATCH}/mut.report"; then
        pass "the missing toleration is caught and named"
      else
        fail "caught, but not as requirement 7: $(cat "${SCRATCH}/mut.report")"
      fi
    fi
  else
    fail "renderer errored on the mutant template instead of rendering it"
  fi
fi

echo "== F. an unsubstituted placeholder is refused at render time =="
ph="${SCRATCH}/placeholder-template.yaml"
sed 's|^  namespace: gates$|  namespace: @@NEVER_SUBSTITUTED@@|' "${TEMPLATE}" > "${ph}"
if GATE_JOB_TEMPLATE="${ph}" "${RENDERER}" --repo-root "${SCRATCH}/repo-a" \
     --tree-hash "${HASH_A}" >/dev/null 2>"${SCRATCH}/ph.err"; then
  fail "a template with an unsubstituted placeholder rendered"
else
  if grep -qF 'unsubstituted placeholder' "${SCRATCH}/ph.err"; then
    pass "unsubstituted placeholder refused at render time"
  else
    fail "refused without naming the placeholder: $(cat "${SCRATCH}/ph.err")"
  fi
fi

echo "== G. a non-hex tree hash is refused =="
if "${RENDERER}" --repo-root "${SCRATCH}/repo-a" --tree-hash "not-a-hash!" >/dev/null 2>&1; then
  fail "a non-hex tree hash was accepted"
else
  pass "non-hex tree hash refused"
fi

echo "== H. the cache env matches ../arc/hook-pod-template.yaml =="
# Requirement 5 says REUSED, not re-invented. Assert each cache variable this
# template sets carries the same value the hook pod template gives it.
drift=0
for var in UV_CACHE_DIR SCCACHE_REDIS_ENDPOINT SCCACHE_REDIS_RW_MODE CI_CACHE_CANARY_N; do
  ours="$(grep -A1 -F "name: ${var}" "${TEMPLATE}" | grep -oE 'value: .*' | head -1)"
  theirs="$(grep -A1 -F "name: ${var}" "${HOOK_POD_TEMPLATE}" | grep -oE 'value: .*' | head -1)"
  if [ -z "${ours}" ]; then
    fail "${var} is absent from the gate template"; drift=1
  elif [ "${ours}" != "${theirs}" ]; then
    fail "${var} drifted: gate has [${ours}], hook pod has [${theirs}]"; drift=1
  fi
done
[ "${drift}" -eq 0 ] && pass "all four cache variables match the hook pod template"

echo
if [ "${failures}" -eq 0 ]; then
  echo "ALL TESTS PASSED"
  exit 0
fi
echo "${failures} TEST(S) FAILED"
exit 1
