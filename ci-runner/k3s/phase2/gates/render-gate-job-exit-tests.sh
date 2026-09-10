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
#      requirement 5 asks for cannot silently drift into a re-invention;
#   I. the initContainer's fetch brings the RANGE and the BASE — the gate ref
#      with full ancestry (never `--depth`) and the `.base` companion mapped to
#      `refs/remotes/origin/master` — and asserts the merge-base the aggregate is
#      about to take;
#   J. the repository bootstrap (worktree pack, commit-refuse hooks) PRECEDES
#      `just check` in the gate container, and the aggregate is still the last
#      thing that runs;
#   K. mutants of I and J are CAUGHT by those same checks, so neither is
#      vacuously true — the same discipline case E applies to case D;
#   L. the GATED REPOSITORY's github.com identity is derived from the gated
#      clone's own origin and rendered into LIVESPEC_GATE_REPOSITORY — and a
#      tree with no github.com origin renders EMPTY rather than a guess.
#
# WHY I AND J EXIST (livespec-dev-tooling-rwmo.1). The sandbox used to be a
# `--depth 1` fetch of one ref into a bare `git init`, so eight members of
# `just check` — the shipped-path release guard, both coverage-diff members,
# the workflow-edit guard, red-green-replay's range arm, the commit-refuse-hook
# and worktree-pack arms, and the live-handoff-file member — failed
# STRUCTURALLY on absent history, an unresolvable `origin/master`, or an
# un-bootstrapped checkout. A gate that cannot run a member is gating a subset,
# and the failure looked like a red tree.
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
  grep -qE '^\s*just hook_gate=1 check$' "$f"                   || { echo "    missing: 2 just hook_gate=1 check command"; missing=1; }
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

# The fetch check, used by BOTH case I and case K. Returns 0 iff the rendered
# manifest at $1 fetches the tree $2 with ancestry AND a resolvable diff base.
# COMMENT LINES ARE STRIPPED FIRST: the template explains at length why it is
# not a `--depth 1` fetch, and prose about a flag must not read as the flag.
check_fetch_brings_range_and_master() {
  local f="$1" hash="$2" missing=0
  # NOT `... | grep -q`: under `pipefail` a `-q` downstream exits on its FIRST
  # match, the upstream grep takes SIGPIPE, and the pipeline reports 141 — so a
  # real match reads as no match, but only when the upstream is still writing.
  # That race passed here and failed inside the loaded commit aggregate.
  if [ -n "$(grep -v '^[[:space:]]*#' "$f" | grep -F -- '--depth' || true)" ]; then
    echo "    shallow: the initContainer still fetches with --depth"; missing=1
  fi
  grep -qF "+refs/gates/${hash}:refs/gates/${hash}" "$f" \
    || { echo "    missing: the gate refspec that brings ancestry"; missing=1; }
  grep -qF "+refs/gates/${hash}.base:refs/remotes/origin/master" "$f" \
    || { echo "    missing: the .base companion mapped to refs/remotes/origin/master"; missing=1; }
  grep -qF 'git merge-base HEAD origin/master' "$f" \
    || { echo "    missing: the merge-base assertion"; missing=1; }
  return "${missing}"
}

# The ordering check, used by BOTH case J and case K. Returns 0 iff the rendered
# manifest at $1 runs both bootstrap steps BEFORE `just check`. Every pattern is
# anchored to a whole line so the template's prose about these same recipes —
# which explains why the pack install is its own `just` invocation — cannot
# satisfy it.
check_bootstrap_precedes_check() {
  local f="$1" pack hooks aggregate
  pack="$(grep -nE '^\s*just install-worktree-pack$' "$f" | head -1 | cut -d: -f1)"
  hooks="$(grep -nE '^\s*just install-commit-refuse-hooks$' "$f" | head -1 | cut -d: -f1)"
  aggregate="$(grep -nE '^\s*just hook_gate=1 check$' "$f" | head -1 | cut -d: -f1)"
  [ -n "${pack}" ]      || { echo "    missing: just install-worktree-pack"; return 1; }
  [ -n "${hooks}" ]     || { echo "    missing: just install-commit-refuse-hooks"; return 1; }
  [ -n "${aggregate}" ] || { echo "    missing: the just check aggregate"; return 1; }
  if [ "${pack}" -ge "${aggregate}" ] || [ "${hooks}" -ge "${aggregate}" ]; then
    echo "    out of order: the bootstrap does not precede just check"
    return 1
  fi
  return 0
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

echo "== I. the fetch brings the RANGE and a resolvable diff base =="
if check_fetch_brings_range_and_master "${out_a}" "${HASH_A}"; then
  pass "full-ancestry gate ref, .base -> refs/remotes/origin/master, merge-base asserted"
else
  fail "the rendered fetch cannot produce a diff base (listed above)"
fi

echo "== J. the repository bootstrap precedes the aggregate =="
if check_bootstrap_precedes_check "${out_a}"; then
  pass "worktree pack and commit-refuse hooks install before just check"
else
  fail "the rendered gate container does not bootstrap before just check (listed above)"
fi

echo "== K. mutants of I and J are CAUGHT by those same checks =="
# Case E's discipline, applied to the two new checks: a check that cannot fail
# is not a check. The first mutant restores the shallow single-ref fetch this
# slice removed; the second deletes the bootstrap lines.
shallow="${SCRATCH}/shallow-template.yaml"
sed -e 's|if ! git fetch --quiet origin \\|git fetch --quiet --depth 1 origin "refs/gates/@@TREE_HASH@@"; if false; then|' \
    "${TEMPLATE}" > "${shallow}"
shallow_out="${SCRATCH}/shallow.yaml"
# Case E's guard, for the same reason: a sed that stops matching would present
# as the MUTANT PASSING, which reads as "case I is vacuous" and sends the
# reader to the wrong file entirely.
if [ -z "$(grep -F -- '--depth 1' "${shallow}" || true)" ]; then
  fail "could not build the shallow mutant template"
elif GATE_JOB_TEMPLATE="${shallow}" "${RENDERER}" --repo-root "${SCRATCH}/repo-a" \
     --tree-hash "${HASH_A}" > "${shallow_out}" 2>/dev/null; then
  if check_fetch_brings_range_and_master "${shallow_out}" "${HASH_A}" > "${SCRATCH}/shallow.report" 2>&1; then
    fail "a --depth 1 single-ref fetch PASSED the fetch check — case I is vacuous"
  elif grep -qF 'still fetches with --depth' "${SCRATCH}/shallow.report"; then
    pass "the reinstated shallow fetch is caught and named"
  else
    fail "caught, but not as a shallow fetch: $(cat "${SCRATCH}/shallow.report")"
  fi
else
  fail "renderer errored on the shallow mutant template instead of rendering it"
fi

nobootstrap="${SCRATCH}/nobootstrap-template.yaml"
sed -E '/^[[:space:]]*just install-(worktree-pack|commit-refuse-hooks)$/d' "${TEMPLATE}" > "${nobootstrap}"
nobootstrap_out="${SCRATCH}/nobootstrap.yaml"
if [ -n "$(grep -E '^[[:space:]]*just install-worktree-pack$' "${nobootstrap}" || true)" ]; then
  fail "could not build the no-bootstrap mutant template"
elif GATE_JOB_TEMPLATE="${nobootstrap}" "${RENDERER}" --repo-root "${SCRATCH}/repo-a" \
     --tree-hash "${HASH_A}" > "${nobootstrap_out}" 2>/dev/null; then
  if check_bootstrap_precedes_check "${nobootstrap_out}" > "${SCRATCH}/nobootstrap.report" 2>&1; then
    fail "an un-bootstrapped gate container PASSED the ordering check — case J is vacuous"
  elif grep -qF 'missing: just install-worktree-pack' "${SCRATCH}/nobootstrap.report"; then
    pass "the deleted bootstrap step is caught and named"
  else
    fail "caught, but not as a missing bootstrap step: $(cat "${SCRATCH}/nobootstrap.report")"
  fi
else
  fail "renderer errored on the no-bootstrap mutant template instead of rendering it"
fi

echo "== L. the gated repository's github.com identity reaches the pod =="
# R4.S7 slice B (livespec-dev-tooling-rwmo.2). The pod's own clone cannot name
# the repository it is gating — its only remote is the git-daemon URL, which is
# not github.com — so the renderer derives the identity HERE, from the gated
# clone's origin, and the manifest carries it as LIVESPEC_GATE_REPOSITORY.
#
# The fixture gets a REAL `git init` + origin rather than a stubbed git: the
# derivation under test is exactly "what does this clone say it is". Git's
# global config is scrubbed so a host-level `url.<base>.insteadOf` cannot
# rewrite the remote this case exists to read.
repo_origin="${SCRATCH}/repo-origin"
make_repo "${repo_origin}" "ghcr.io/thewoolleyman/livespec-python:v1.64.2"
git_scrubbed() { GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null git "$@"; }
git_scrubbed init --quiet "${repo_origin}" 2>/dev/null
git_scrubbed -C "${repo_origin}" remote add origin \
  "https://github.com/thewoolleyman/livespec-dev-tooling.git" 2>/dev/null
origin_out="${SCRATCH}/origin.yaml"
if "${RENDERER}" --repo-root "${repo_origin}" --tree-hash "${HASH_A}" > "${origin_out}" 2>/dev/null; then
  if grep -qF 'value: "thewoolleyman/livespec-dev-tooling"' "${origin_out}"; then
    pass "the github.com owner/repo is derived from origin and rendered"
  else
    fail "the rendered manifest does not name the gated repository: $(grep -A1 -F 'LIVESPEC_GATE_REPOSITORY' "${origin_out}")"
  fi
else
  fail "renderer errored on the fixture repo carrying a github.com origin"
fi

# The negative half, and the control that keeps the positive one honest: the
# SAME renderer against a tree with NO github.com origin — every other fixture
# in this suite — must render an EMPTY value rather than refusing, and rather
# than leaking `--repo` (a bare mirror name) into a slot that must hold
# owner/repo. Two fixtures, one renderer, two different values: the identity
# can only have come from the clone. Empty is what the checks read as "no
# repository was named".
if "${RENDERER}" --repo-root "${SCRATCH}/repo-a" --tree-hash "${HASH_A}" \
     > "${SCRATCH}/no-origin.yaml" 2>/dev/null; then
  if grep -A1 -F 'name: LIVESPEC_GATE_REPOSITORY' "${SCRATCH}/no-origin.yaml" | grep -qF 'value: ""'; then
    pass "a repo with no github.com origin renders an empty identity, not a guess"
  else
    fail "expected an empty identity: $(grep -A1 -F 'name: LIVESPEC_GATE_REPOSITORY' "${SCRATCH}/no-origin.yaml")"
  fi
else
  fail "renderer errored on the fixture repo with no origin"
fi

echo
if [ "${failures}" -eq 0 ]; then
  echo "ALL TESTS PASSED"
  exit 0
fi
echo "${failures} TEST(S) FAILED"
exit 1
