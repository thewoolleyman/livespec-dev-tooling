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
#      tree with no github.com origin renders EMPTY rather than a guess;
#   M. the gate command is the GATED REPOSITORY's OWN declared check recipes and
#      none of livespec-dev-tooling's — two suites render two different
#      commands, and a repository that declares nothing gets the shared
#      pre-push SEQUENCE its local fall-through runs — the two installs, then
#      the recipe every repository's lefthook `pre-push` names,
#      `check-pre-push`, with no `name=value` override of any kind
#      (freeze-driver rulings R92 and R100, 2026-10-17);
#   N. the rendered pod script PREFLIGHTS each declared recipe: a tree that does
#      not provide one exits non-zero NAMING it, runs no recipe at all, and
#      never falls back — and a tree that provides them runs them in order, so
#      the preflight is proven not to refuse everything;
#   O. a mutant with the preflight deleted is CAUGHT by case N's own check, and
#      an entry that is not a plain `just` invocation is refused at render time;
#   P. the CROSS-REPO SIBLINGS the gated repository registers in its own
#      `.livespec.jsonc` are cloned anonymously from github.com into the
#      directory the Job exports as LIVESPEC_SIBLING_CLONES_ROOT, before any
#      recipe runs — a repository registering none renders the command it has
#      today (compared against the template with the step's line deleted), a
#      url no pod could anonymously fetch is refused naming the sibling, and a
#      clone that FAILS is the verdict.
#
# WHY P EXISTS (livespec-dev-tooling-s35dcb). livespec core's cross-repo readers
# resolve a cited sibling at `$LIVESPEC_SIBLING_CLONES_ROOT/<sibling>` when that
# variable is set and at `/data/projects/<sibling>` otherwise — a fleet-host
# path no pod has — and an absent path is read as an EMPTY heading set rather
# than as an error. Measured 2026-10-18 on gate-livespec-e0a55a1a58f6:
# `doctor-no-cross-spec-reference` failed livespec
# SPECIFICATION/constraints.md:298 for a citation that IS allowlisted, on a tree
# whose master CI was green. The consumer's own CI clones its siblings for that
# same check; the gate is meant to judge the tree the way CI does.
#
# WHY M, N AND O EXIST (livespec-dev-tooling-saxz). The pod command was a
# CONSTANT naming this repository's own recipes, so a consuming repository
# lacking `warm-typecheck` or a `hook_gate` variable failed every Job and its
# gate was red on every green tree — measured 2026-10-16 against
# livespec-orchestrator-beads-fabro, whose post-merge janitor shipped
# `venue = host_local` instead of using the gate.
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

# The suite livespec-dev-tooling itself declares, passed EXPLICITLY here exactly
# as the client passes it, so cases D and J keep asserting this repository's own
# gate command rather than whatever the renderer happens to default to.
OUR_SUITE=(--check-suite install-worktree-pack
           --check-suite install-commit-refuse-hooks
           --check-suite warm-typecheck
           --check-suite "hook_gate=1 check")
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

# One container's own block out of the rendered manifest at $1, by name ($2).
# Bounded by the next sibling `- name:` entry, so a claim about one container is
# never satisfied by its neighbour's lines.
container_block() {
  awk -v want="$2" '
    $0 ~ "^ *- name: " want "$" { inblock = 1; print; next }
    inblock && /^ *- name: / { exit }
    inblock { print }
  ' "$1"
}

# The fetch check, used by BOTH case I and case K. Returns 0 iff the rendered
# manifest at $1 fetches the tree $2 with ancestry AND a resolvable diff base.
# COMMENT LINES ARE STRIPPED FIRST: the template explains at length why it is
# not a `--depth 1` fetch, and prose about a flag must not read as the flag.
#
# THE `--depth` BAN IS SCOPED TO THE fetch-tree CONTAINER, which is the one this
# requirement is about: the TREE UNDER TEST needs ancestry because eight
# aggregate members judge `origin/master..HEAD`. A sibling init container
# fetching a DEPENDENCY — livespec core, whose history nothing reads — is
# legitimately shallow, and the scoping stays load-bearing because case K's
# mutant reinstates `--depth 1` in THIS container and must still be caught.
check_fetch_brings_range_and_master() {
  local f="$1" hash="$2" missing=0
  # NOT `... | grep -q`: under `pipefail` a `-q` downstream exits on its FIRST
  # match, the upstream grep takes SIGPIPE, and the pipeline reports 141 — so a
  # real match reads as no match, but only when the upstream is still writing.
  # That race passed here and failed inside the loaded commit aggregate.
  if [ -n "$(container_block "$f" fetch-tree | grep -v '^[[:space:]]*#' | grep -F -- '--depth' || true)" ]; then
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
if "${RENDERER}" --repo-root "${SCRATCH}/repo-a" --tree-hash "${HASH_A}" "${OUR_SUITE[@]}" > "${out_a}" 2>"${SCRATCH}/a.err" &&
   "${RENDERER}" --repo-root "${SCRATCH}/repo-b" --tree-hash "${HASH_B}" "${OUR_SUITE[@]}" > "${out_b}" 2>"${SCRATCH}/b.err"; then
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
       --tree-hash "${HASH_A}" "${OUR_SUITE[@]}" > "${mut_out}" 2>/dev/null; then
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
     --tree-hash "${HASH_A}" "${OUR_SUITE[@]}" > "${shallow_out}" 2>/dev/null; then
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

# The bootstrap now comes from the DECLARED SUITE rather than from the template,
# so the mutant is a declaration with the two installs dropped — which is also
# exactly the shape a consuming repository that declares only its own aggregate
# produces, and the ordering check must still name what it did not find.
nobootstrap_out="${SCRATCH}/nobootstrap.yaml"
if "${RENDERER}" --repo-root "${SCRATCH}/repo-a" --tree-hash "${HASH_A}" \
     --check-suite "hook_gate=1 check" > "${nobootstrap_out}" 2>/dev/null; then
  if check_bootstrap_precedes_check "${nobootstrap_out}" > "${SCRATCH}/nobootstrap.report" 2>&1; then
    fail "an un-bootstrapped gate container PASSED the ordering check — case J is vacuous"
  elif grep -qF 'missing: just install-worktree-pack' "${SCRATCH}/nobootstrap.report"; then
    pass "the deleted bootstrap step is caught and named"
  else
    fail "caught, but not as a missing bootstrap step: $(cat "${SCRATCH}/nobootstrap.report")"
  fi
else
  fail "renderer errored on the no-bootstrap declaration instead of rendering it"
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

echo "== M. the command is the GATED repository's own declared recipes =="
# The same discipline as case A, applied to the command: two DIFFERENT suites
# rendered by one renderer, plus the no-declaration default. A constant could
# not produce three different answers.
gate_recipes() {
  # Every `just …` the gate container runs, in order. Anchored to a line that
  # STARTS with `just `, so neither the preflight's `if just --show …` probe nor
  # the template's prose about these recipes can be mistaken for one.
  awk '/^ *- name: gate$/ { gate = 1 } gate && /^ *just /' "$1" | sed -e 's/^[[:space:]]*//'
}
declared_out="${SCRATCH}/declared.yaml"
other_out="${SCRATCH}/other.yaml"
default_out="${SCRATCH}/default.yaml"
if "${RENDERER}" --repo-root "${SCRATCH}/repo-a" --tree-hash "${HASH_A}" \
     --check-suite verify --check-suite publish > "${declared_out}" 2>/dev/null &&
   "${RENDERER}" --repo-root "${SCRATCH}/repo-a" --tree-hash "${HASH_A}" \
     --check-suite ci > "${other_out}" 2>/dev/null &&
   "${RENDERER}" --repo-root "${SCRATCH}/repo-a" --tree-hash "${HASH_A}" \
     > "${default_out}" 2>/dev/null; then
  if [ "$(gate_recipes "${declared_out}")" = "just verify
just publish" ]; then
    pass "a declaring repository's Job runs its own two recipes, in order"
  else
    fail "the declared suite did not reach the command: $(gate_recipes "${declared_out}")"
  fi
  if [ "$(gate_recipes "${other_out}")" = "just ci" ]; then
    pass "a second declaration renders a different command from the same renderer"
  else
    fail "the second declaration did not reach the command: $(gate_recipes "${other_out}")"
  fi
  # The no-declaration default is the SHARED PRE-PUSH SEQUENCE, not one recipe
  # (ruling R92). A bare `just check` is not the fall-through a gate stands in
  # for: without the installs two members judge the pod's un-bootstrapped
  # sandbox. And the last entry is the RECIPE every repository's lefthook
  # `pre-push` names, carrying no `name=value` override (ruling R100): R92's
  # `hook_gate=1 check` names a variable only livespec-dev-tooling declares, and
  # `just` refuses an override of an undeclared variable, so every other
  # consumer's Job died before its aggregate ran.
  if [ "$(gate_recipes "${default_out}")" = "just install-worktree-pack
just install-commit-refuse-hooks
just check-pre-push" ]; then
    pass "a repository that declares nothing gets its local fall-through sequence"
  else
    fail "the no-declaration default is not the shared pre-push sequence: $(gate_recipes "${default_out}")"
  fi
  if [ -z "$(gate_recipes "${default_out}" | grep -F '=' || true)" ]; then
    pass "the no-declaration default passes no just-variable override at all"
  else
    fail "the default carries a just-variable override: $(gate_recipes "${default_out}")"
  fi
  if [ -z "$(gate_recipes "${declared_out}" | grep -E 'warm-typecheck|hook_gate|install-' || true)" ]; then
    pass "none of livespec-dev-tooling's own recipes reach another repository's Job"
  else
    fail "this repository's recipes leaked into another repository's Job"
  fi
else
  fail "renderer errored while rendering a declared check suite"
fi

echo "== N. the pod preflights each declared recipe before running anything =="
# The rendered script is RUN here, against a stub `just` that answers
# `--show <recipe>` from a provided list — which is exactly the question the
# preflight asks. Nothing else about `just` is simulated, because nothing else
# is under test.
STUB_DIR="${SCRATCH}/stub-bin"
mkdir -p "${STUB_DIR}"
cat > "${STUB_DIR}/just" <<'STUB'
#!/usr/bin/env bash
printf 'just %s\n' "$*" >> "${STUB_LOG}"
if [ "${1:-}" = "--show" ]; then
  case " ${PROVIDED} " in
    *" ${2} "*) exit 0 ;;
    *)          exit 1 ;;
  esac
fi
exit 0
STUB
chmod +x "${STUB_DIR}/just"

# A `git` for case P's sibling clones, answering `clone` without reaching the
# network and CREATING NOTHING: a real clone makes its destination and every
# parent of it, and a stub that did the same would leave the pod's clones root
# on the host running this suite.
cat > "${STUB_DIR}/git" <<'STUB'
#!/usr/bin/env bash
printf 'git %s\n' "$*" >> "${STUB_LOG}"
if [ "${1:-}" = "clone" ]; then
  [ -n "${CLONE_FAILS}" ] && exit 1
  exit 0
fi
[ "${3:-}" = "rev-parse" ] && echo "0000000000000000000000000000000000000000"
exit 0
STUB
chmod +x "${STUB_DIR}/git"

gate_script() {
  # The gate container's shell script, dedented out of a rendered manifest.
  awk '
    /^ *- name: gate$/ { gate = 1 }
    gate && !body && /^ *- \|$/ { match($0, /^ */); indent = RLENGTH + 2; body = 1; next }
    body {
      if ($0 != "" && substr($0, 1, indent) !~ /^ +$/) { exit }
      print substr($0, indent + 1)
    }
  ' "$1"
}

run_gate_script() {
  # run_gate_script <manifest> <space-separated recipes the tree provides>
  #                 [<non-empty to make every sibling clone fail>]
  # Leaves the invocation log at ${SCRATCH}/stub.log and returns the script's
  # own exit status, which IS the Job's verdict.
  : > "${SCRATCH}/stub.log"
  gate_script "$1" > "${SCRATCH}/gate-script.sh"
  PATH="${STUB_DIR}:${PATH}" STUB_LOG="${SCRATCH}/stub.log" PROVIDED="$2" \
    CLONE_FAILS="${3:-}" \
    bash "${SCRATCH}/gate-script.sh" > "${SCRATCH}/gate.out" 2> "${SCRATCH}/gate.err"
}

if run_gate_script "${declared_out}" "verify publish"; then
  if [ "$(cat "${SCRATCH}/stub.log")" = "just --show verify
just --show publish
just verify
just publish" ]; then
    pass "a tree providing both recipes preflights both, then runs both in order"
  else
    fail "the provided tree ran the wrong commands: $(cat "${SCRATCH}/stub.log")"
  fi
else
  fail "the preflight refused a tree that DOES provide its declared recipes"
fi

if run_gate_script "${declared_out}" "publish"; then
  fail "a tree missing a declared recipe reported a GREEN gate"
else
  missing_named=0
  grep -qF "does not provide the gate check recipe 'verify'" "${SCRATCH}/gate.err" || missing_named=1
  if [ "${missing_named}" -ne 0 ]; then
    fail "red, but the message does not name the missing recipe: $(cat "${SCRATCH}/gate.err")"
  elif [ -n "$(grep -vF -- '--show' "${SCRATCH}/stub.log" || true)" ]; then
    fail "a recipe RAN despite the missing one: $(cat "${SCRATCH}/stub.log")"
  else
    pass "a missing declared recipe is red, names the recipe, and runs nothing"
  fi
fi

echo "== O. the preflight is load-bearing, and a non-recipe entry is refused =="
# Case E's discipline: a check that cannot fail is not a check. With the
# preflight loop deleted the SAME missing-recipe tree must stop being refused.
nopreflight="${SCRATCH}/nopreflight-template.yaml"
sed '/for recipe in @@GATE_RECIPE_NAMES@@; do/,/^ *done$/d' "${TEMPLATE}" > "${nopreflight}"
nopreflight_out="${SCRATCH}/nopreflight.yaml"
if [ -n "$(grep -F 'GATE_RECIPE_NAMES' "${nopreflight}" || true)" ]; then
  fail "could not build the no-preflight mutant template"
elif GATE_JOB_TEMPLATE="${nopreflight}" "${RENDERER}" --repo-root "${SCRATCH}/repo-a" \
     --tree-hash "${HASH_A}" --check-suite verify --check-suite publish \
     > "${nopreflight_out}" 2>/dev/null; then
  if run_gate_script "${nopreflight_out}" "publish"; then
    pass "without the preflight the same missing recipe is NOT refused — case N is load-bearing"
  else
    fail "the no-preflight mutant refused anyway — case N proves nothing"
  fi
else
  fail "renderer errored on the no-preflight mutant template instead of rendering it"
fi

if "${RENDERER}" --repo-root "${SCRATCH}/repo-a" --tree-hash "${HASH_A}" \
     --check-suite 'check; curl evil' >/dev/null 2>"${SCRATCH}/injection.err"; then
  fail "a --check-suite entry that is not a plain just invocation was rendered"
elif grep -qF 'is not a plain just invocation' "${SCRATCH}/injection.err"; then
  pass "a --check-suite entry carrying shell is refused at render time"
else
  fail "refused without naming the cause: $(cat "${SCRATCH}/injection.err")"
fi

echo "== P. the Job provisions the cross-repo siblings its checks read =="
# livespec core's cross-repo readers resolve a cited sibling at
# `$LIVESPEC_SIBLING_CLONES_ROOT/<sibling>` when that variable is set and at the
# manifest's `/data/projects/<sibling>` otherwise — a path present in no pod,
# whose absence they read as an EMPTY heading set rather than as an error. So an
# unprovisioned sibling is a GREEN gate on citations nothing validated, which is
# why all four arms below exist: the clones happen, a repository registering
# none renders the command it had, a url the pod cannot anonymously fetch is
# refused, and a clone that FAILS is the verdict.
make_siblings() {
  # make_siblings <dir> <slug>=<github_url> ...
  local dir="$1" first=1 pair
  shift
  {
    printf '{\n  "cross_repo_targets": {\n'
    for pair in "$@"; do
      [ "${first}" -eq 1 ] || printf ',\n'
      first=0
      printf '    "%s": {\n      "github_url": "%s",\n      "local_clone": "/data/projects/%s"\n    }' \
        "${pair%%=*}" "${pair#*=}" "${pair%%=*}"
    done
    printf '\n  }\n}\n'
  } > "${dir}/.livespec.jsonc"
}
# Dedented out of the gate script, so a line number here is a line number in
# the script the pod runs. A caller matching a recipe invocation must allow
# LEADING WHITESPACE: the recipes run inside a captured brace group, so they are
# indented in the rendered script (livespec-dev-tooling-plbimj). A `^just `
# pattern matches nothing there and yields an EMPTY line number, which `[ -ge ]`
# reports as `integer expression expected` and the arm then reads as a PASS —
# which is how this very edit first presented.
sibling_root() { gate_script "$1" | sed -n "s/^export LIVESPEC_SIBLING_CLONES_ROOT='\(.*\)'$/\1/p"; }
script_line() { gate_script "$1" | grep -n -- "$2" | head -1 | cut -d: -f1; }
last_script_line() { gate_script "$1" | grep -n -- "$2" | tail -1 | cut -d: -f1; }

repo_siblings="${SCRATCH}/repo-siblings"
make_repo "${repo_siblings}" "${IMG_A}"
make_siblings "${repo_siblings}" \
  "widget-core=https://github.com/acme/widget-core" \
  "widget-docs=https://github.com/acme/widget-docs"
siblings_out="${SCRATCH}/siblings.yaml"
if "${RENDERER}" --repo-root "${repo_siblings}" --tree-hash "${HASH_A}" \
     --check-suite verify > "${siblings_out}" 2>/dev/null; then
  clones_root="$(sibling_root "${siblings_out}")"
  first_recipe="$(script_line "${siblings_out}" '^ *just ')"
  cloned=0
  for slug in widget-core widget-docs; do
    grep -qF "git clone --quiet --depth 1 'https://github.com/acme/${slug}' '${clones_root}/${slug}'" \
      "${siblings_out}" || cloned=1
  done
  if [ -z "${clones_root}" ]; then
    fail "the gate container exports no sibling-clones root, so the readers resolve /data/projects"
  elif [ "${cloned}" -ne 0 ]; then
    fail "a registered sibling is not cloned where the readers look: $(gate_script "${siblings_out}" | grep -c 'git clone ')"
  elif [ "$(gate_script "${siblings_out}" | grep -c 'git clone ')" != "2" ]; then
    fail "the Job does not clone exactly one sibling per registered target"
  elif [ -z "${first_recipe}" ]; then
    fail "the gate script carries no check-suite recipe line, so the ordering arm below is vacuous"
  elif [ "$(last_script_line "${siblings_out}" 'git clone ')" -ge "${first_recipe}" ]; then
    fail "a check-suite recipe runs before the siblings are provisioned"
  elif grep -F 'git clone ' "${siblings_out}" | grep -qF '@'; then
    fail "a credential rides a sibling clone: $(grep -F 'git clone ' "${siblings_out}")"
  else
    pass "each registered sibling is cloned anonymously into the exported root, before any recipe"
  fi
else
  fail "renderer errored on a repository registering cross-repo siblings"
fi

# The fixture above is the FIRST one in this suite to carry a `.livespec.jsonc`
# without a `compat.pinned`, and it proved the renderer died there — exit 1,
# nothing on stderr, which the client reports as `NO_VERDICT`. The module
# promises an absent field is an ANSWER, so the fallback is asserted here where
# the shape that reaches it lives.
if grep -qF '"pinned"' "${repo_siblings}/.livespec.jsonc"; then
  fail "the siblings fixture pins a core release, so the absent-field fallback is untested"
elif [ -z "$(gate_script "${siblings_out}" | grep -F 'livespec core ref master' || true)" ]; then
  fail "a .livespec.jsonc with no compat.pinned did not fall back to master: $(gate_script "${siblings_out}" | grep -F 'livespec core ref')"
else
  pass "a .livespec.jsonc carrying no compat.pinned renders the master fallback, not a refusal"
fi

# The control, and the whole of the no-declaration claim: `repo-a` registers
# nothing, and its gate script is compared — executable line for executable
# line — against the SAME template with the step's placeholder line deleted,
# which IS the template that shipped before the step existed.
nostep="${SCRATCH}/nostep-template.yaml"
grep -vF '@@GATE_SIBLING_CLONES@@' "${TEMPLATE}" > "${nostep}"
nostep_out="${SCRATCH}/nostep.yaml"
executable_gate_script() { gate_script "$1" | grep -vE '^[[:space:]]*(#|$)'; }
if [ "$(grep -cF '@@GATE_SIBLING_CLONES@@' "${TEMPLATE}")" != "1" ]; then
  fail "the template does not carry exactly one sibling-clone placeholder"
elif GATE_JOB_TEMPLATE="${nostep}" "${RENDERER}" --repo-root "${SCRATCH}/repo-a" \
     --tree-hash "${HASH_A}" > "${nostep_out}" 2>/dev/null; then
  if [ -n "$(sibling_root "${default_out}")" ] ||
     [ -n "$(gate_script "${default_out}" | grep -F 'git clone ' || true)" ]; then
    fail "a repository registering no siblings still renders a clone step"
  elif [ "$(executable_gate_script "${default_out}")" != "$(executable_gate_script "${nostep_out}")" ]; then
    fail "a repository registering no siblings got a different command than it has today"
  else
    pass "a repository registering no siblings renders no step and keeps today's command"
  fi
else
  fail "renderer errored on the no-step mutant template instead of rendering it"
fi

repo_badurl="${SCRATCH}/repo-badurl"
make_repo "${repo_badurl}" "${IMG_A}"
make_siblings "${repo_badurl}" "widget-core=git@github.com:acme/widget-core.git"
if "${RENDERER}" --repo-root "${repo_badurl}" --tree-hash "${HASH_A}" \
     > /dev/null 2>"${SCRATCH}/badurl.err"; then
  fail "a sibling the pod cannot anonymously clone was rendered anyway"
elif grep -qF 'cross_repo_targets.widget-core' "${SCRATCH}/badurl.err"; then
  pass "a sibling url that is not an anonymous github.com https url is refused, naming it"
else
  fail "refused without naming the sibling: $(cat "${SCRATCH}/badurl.err")"
fi

if run_gate_script "${siblings_out}" "verify" "fail-the-clones"; then
  fail "a gate whose sibling clone FAILED reported a GREEN verdict"
elif ! grep -qF "cannot clone cross-repo sibling 'widget-core'" "${SCRATCH}/gate.err"; then
  fail "red, but the message does not name the sibling: $(cat "${SCRATCH}/gate.err")"
elif [ -n "$(grep -E '^just ' "${SCRATCH}/stub.log" | grep -vF -- '--show' || true)" ]; then
  fail "a check-suite recipe RAN despite an unprovisioned sibling: $(cat "${SCRATCH}/stub.log")"
else
  pass "a sibling that will not clone is red, names the sibling, and runs no recipe"
fi

if run_gate_script "${siblings_out}" "verify"; then
  if [ "$(grep -cF 'git clone ' "${SCRATCH}/stub.log")" = "2" ]; then
    pass "the same Job with clones that succeed runs its recipe — the refusal is the clone"
  else
    fail "the clean run did not clone both siblings: $(cat "${SCRATCH}/stub.log")"
  fi
else
  fail "the gate refused a tree whose siblings cloned cleanly: $(cat "${SCRATCH}/gate.err")"
fi

echo "== Q. a PRIVATE sibling clones with a mounted token the manifest never carries =="
# The delegated pre-push gate's cross-repository siblings rule in
# SPECIFICATION/contracts.md: a private sibling is cloned with a GitHub App
# installation token the pushing
# host mints, and that token "MUST NOT appear in the rendered manifest's text".
# The renderer is told WHICH siblings are private and the NAME of the per-run
# Secret holding the token, and that is ALL it is told — so these arms assert
# both halves: the mount and authenticated clone are rendered, and no credential
# material is anywhere in the output.
#
# The Secret name used here is deliberately token-SHAPED. If the renderer ever
# started accepting a token instead of a name, the "no credential in the
# manifest" arm below would have to catch it, and a bland fixture name would not
# distinguish the two cases (work-item livespec-dev-tooling-7kvh2d).
private_out="${SCRATCH}/private-sibling.yaml"
private_secret="gate-sibling-token-9f2c1b4a7d6e"
private_mount="/run/secrets/gate-private-siblings"
if "${RENDERER}" --repo-root "${repo_siblings}" --tree-hash "${HASH_A}" \
     --check-suite verify --private-sibling widget-core \
     --private-sibling-secret "${private_secret}" > "${private_out}" 2>"${SCRATCH}/private.err"; then
  private_clone="$(gate_script "${private_out}" | grep -F "'https://github.com/acme/widget-core'" | head -1)"
  public_clone="$(gate_script "${private_out}" | grep -F "'https://github.com/acme/widget-docs'" | head -1)"
  if ! printf '%s' "${private_clone}" | grep -qF "http.extraHeader"; then
    fail "the private sibling's clone carries no authorization: ${private_clone}"
  elif ! printf '%s' "${private_clone}" | grep -qF "cat ${private_mount}/token"; then
    fail "the private clone does not read its token from the mount: ${private_clone}"
  # THE SCHEME IS LOAD-BEARING, and asserting only the header's PRESENCE above
  # is how R581 shipped: github.com's git smart-HTTP endpoint rejects an
  # installation token sent as `Bearer`, which in a pod with no askPass reads
  # as `could not read Username`. The accepted form is Basic with the username
  # `x-access-token`. What that header actually EVALUATES to is proven by
  # running it — `tests/consumer/test_delegated_gate_declared_recipe_scenarios.py`
  # sends it to a `git` stub and compares it to an independently computed
  # base64 — so these two arms pin the scheme and the username alone.
  elif printf '%s' "${private_clone}" | grep -qF "Bearer"; then
    fail "the private clone sends a Bearer header, which github.com rejects: ${private_clone}"
  elif ! printf '%s' "${private_clone}" | grep -qF "Authorization: Basic \$(printf 'x-access-token:%s'"; then
    fail "the private clone does not send Basic x-access-token: ${private_clone}"
  elif printf '%s' "${public_clone}" | grep -qF "http.extraHeader"; then
    fail "a PUBLIC sibling was given a credential: ${public_clone}"
  elif ! grep -qF "mountPath: ${private_mount}" "${private_out}"; then
    fail "the token Secret is not mounted into the gate container"
  elif ! grep -qF "secretName: ${private_secret}" "${private_out}"; then
    fail "the manifest declares no volume for the per-run token Secret"
  elif [ "$(grep -cF "${private_secret}" "${private_out}")" != "3" ]; then
    fail "the Secret name is not named exactly three times (mount, volume, volume name)"
  else
    pass "a private sibling mounts the per-run Secret and clones through it; a public one does not"
  fi
  # The point of the whole design: what the API server STORES holds no
  # credential. `ghs_`/`ghp_`/`github_pat_` are GitHub's own token prefixes, and
  # a `Bearer`/`Basic` followed by a LITERAL would be an interpolated header
  # rather than the deferred `$(...)` read the renderer emits. BOTH schemes are
  # named: the renderer now sends Basic, and a pattern that still knew only the
  # retired scheme would be blind to exactly the header being rendered.
  if grep -qE 'gh[sprou]_|github_pat_|Authorization: (Bearer|Basic) [A-Za-z0-9]' "${private_out}"; then
    fail "credential-shaped text is in the rendered manifest: $(grep -nE 'gh[sprou]_|github_pat_|Authorization: (Bearer|Basic) [A-Za-z0-9]' "${private_out}")"
  else
    pass "the rendered manifest carries no token — only the Secret's name and a deferred read"
  fi
else
  fail "renderer errored on a repository with a private sibling: $(cat "${SCRATCH}/private.err")"
fi

# Two refusals, because each would otherwise render a Job that cannot start: a
# mount with no Secret name, and a name the API server will not accept.
if "${RENDERER}" --repo-root "${repo_siblings}" --tree-hash "${HASH_A}" \
     --private-sibling widget-core > /dev/null 2>"${SCRATCH}/nosecret.err"; then
  fail "a private sibling was rendered with no Secret to read its token from"
elif grep -qF 'requires --private-sibling-secret' "${SCRATCH}/nosecret.err"; then
  pass "--private-sibling without --private-sibling-secret is refused at render time"
else
  fail "refused without naming the cause: $(cat "${SCRATCH}/nosecret.err")"
fi

if "${RENDERER}" --repo-root "${repo_siblings}" --tree-hash "${HASH_A}" \
     --private-sibling widget-core --private-sibling-secret 'Gate Token!' \
     > /dev/null 2>"${SCRATCH}/badsecret.err"; then
  fail "a Secret name Kubernetes cannot accept was reproduced into a manifest"
elif grep -qF 'Kubernetes resource name' "${SCRATCH}/badsecret.err"; then
  pass "a Secret name that is not a lowercase resource name is refused, naming it"
else
  fail "refused without naming the cause: $(cat "${SCRATCH}/badsecret.err")"
fi

# The clone is still THE VERDICT for a private sibling: an authenticated clone
# that fails must be red and name the sibling, exactly as the anonymous one is.
# Without this arm the authorization could be added and the refusal lost.
if run_gate_script "${private_out}" "verify" "fail-the-clones"; then
  fail "a gate whose PRIVATE sibling clone FAILED reported a GREEN verdict"
elif ! grep -qF "cannot clone cross-repo sibling 'widget-core'" "${SCRATCH}/gate.err"; then
  fail "red, but the message does not name the private sibling: $(cat "${SCRATCH}/gate.err")"
elif grep -qE 'gh[sprou]_|github_pat_' "${SCRATCH}/gate.err"; then
  fail "the refusal message leaked credential-shaped text: $(cat "${SCRATCH}/gate.err")"
else
  pass "a private sibling that will not clone is red, names it, and leaks no credential"
fi

echo
if [ "${failures}" -eq 0 ]; then
  echo "ALL TESTS PASSED"
  exit 0
fi
echo "${failures} TEST(S) FAILED"
exit 1
