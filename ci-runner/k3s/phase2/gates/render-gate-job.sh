#!/usr/bin/env bash
# render-gate-job.sh — render ./gate-job-template.yaml into a submittable gate
# Job for ONE repository and ONE tree (R4.S5, livespec-dev-tooling-sk8f; plan
# livespec k3s-on-gmktec-for-vps-usage, epic livespec-sab5gn; design in that
# plan's research/003 section D and corrections 2, 5 and 6).
#
# THE POINT OF THIS SCRIPT IS REQUIREMENT 1: the container image is READ FROM THE
# GATED REPOSITORY'S OWN .github/workflows/ci.yml, never baked in. The tag lives
# in each repository's `container:` block and moves with the fleet image pin —
# measured 2026-09-07 livespec ran python-v1.56.2 while livespec-dev-tooling ran
# python-v1.58.2, and by 2026-09-08 BOTH had moved to python-v1.64.2. A constant
# would silently gate against a different toolchain than CI uses, which is the
# same class of defect as gating a subset of the checks.
#
# If a repository's workflow carries SEVERAL container images, this script
# REFUSES rather than picking one: which toolchain the gate should use is then a
# real question about that repository, and guessing it wrong is exactly the
# failure this requirement exists to prevent.
#
# Writes the manifest to stdout. Applies NOTHING; contacts no cluster.
#
# Usage:
#   render-gate-job.sh --repo-root PATH --tree-hash SHA [--repo NAME]
#                      [--gated-repository OWNER/REPO]
#                      [--source-url URL] [--cpu N] [--memory SIZE]
#                      [--parallelism N] [--ttl-seconds N] [--gate-ref REF]
#                      [--livespec-core-ref REF]
#                      [--check-suite 'RECIPE' ...]
#
# --repo defaults to the basename of --repo-root. --source-url defaults to the
# in-cluster read-only mirror R4.S4 builds. The resource defaults are the terms
# ../kueue/cluster-queue-gates.yaml quotas: 5 cpu / 6Gi, three concurrent gates
# under its 15 cpu / 24Gi.
#
# THERE IS NO --job-name, AND THAT IS THE POINT (livespec-dev-tooling-44fglo).
# The manifest asks the API server for a `metadata.generateName`, so the Job's
# name is ASSIGNED at submit rather than rendered here. A rendered name was
# derived from the gated tree, and the template's `ttlSecondsAfterFinished`
# keeps a finished Job for an hour — so for that hour every further gate of the
# same tree was refused at submit with `AlreadyExists` and the client reported
# NO_VERDICT, the state reserved for a lost cluster. The gated tree is still
# named by the `livespec.gate/tree-hash` label, which is what made the name
# useful; the client reads the assigned name back off its own submit.
#
# --gate-ref is the mirror ref THIS RUN pushed the tree under test to, which the
# pod fetches and checks out. It defaults to `refs/gates/<tree hash>` for a hand
# render, and the gate client passes a PER-RUN ref instead. That is not
# decoration: the client deletes the refs it created in a `finally`, so two
# gates of one tree sharing a ref name meant whichever finished first deleted
# the other run's input — measured 2026-10-19, when one such collision cost BOTH
# post-merge janitors of master tree 228727afbe95 their verdicts.
#
# --check-suite is the GATED REPOSITORY'S OWN check recipes — one flag per `just`
# invocation, run in the order given — and it is requirement 1's sibling
# (livespec-dev-tooling-saxz). The pod command used to be a CONSTANT naming
# livespec-dev-tooling's own `install-worktree-pack`, `warm-typecheck` and
# `hook_gate=1 check`, so a consuming repository that carries neither
# `warm-typecheck` nor a `hook_gate` variable failed every Job and its gate was
# red on every green tree — measured 2026-10-16 against
# livespec-orchestrator-beads-fabro, whose post-merge janitor had to ship
# `venue = host_local` because of it. The caller passes what the repository
# DECLARES (`gate_check_suite` in its `[tool.livespec_dev_tooling]` block); the
# default when no flag is given is the SHARED PRE-PUSH SEQUENCE a consumer's
# local fall-through runs (see that default below), never a recipe only this
# repository declares.
#
# An entry MAY carry leading `name=value` variable assignments, which `just`
# accepts before the recipe name. The RECIPE the Job preflights is the first
# token that is not an assignment, so `hook_gate=1 check` preflights `check`.
#
# --livespec-core-ref is the livespec CORE release the gate resolves inside the
# pod, for a consumer whose aggregate runs `check-doctor-static` (R4.S7c part
# ii, freeze-driver ruling R92). It DEFAULTS to the gated repository's own
# `.livespec.jsonc` `compat.pinned` — the same field that repository's CI job
# resolves core at, so the gate and CI judge the tree against one core build —
# and to `master` for a consumer that pins nothing. Core is public, so no
# credential is passed into the pod for it.
#
# --gated-repository is the github.com <owner>/<repo> the gate is judging, and
# it is NOT the same thing as --repo (R4.S7 slice B, livespec-dev-tooling-rwmo.2).
# --repo names the mirror and labels the Job; this names the FORGE REPOSITORY
# `check-branch-protection-alignment` and `check-master-ci-green` must read. They
# cannot derive it themselves inside the pod: the gate clone's only remote is the
# git daemon URL above, which is not github.com and carries no owner segment at
# all. It IS derivable HERE, on the dispatching host, where --repo-root is a real
# github clone — so this script derives it and the pod is simply told.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="${GATE_JOB_TEMPLATE:-${SCRIPT_DIR}/gate-job-template.yaml}"

repo_root=""; tree_hash=""; repo=""; source_url=""; gated_repository=""
cpu="5"; memory="6Gi"; parallelism="4"; ttl_seconds="3600"; gate_ref=""
livespec_core_ref=""
check_suite=()
private_siblings=()
private_sibling_secret=""
authority_skip_env=""
authority_skip_members=()

# WHERE livespec CORE comes from, for the consumer whose aggregate runs
# `check-doctor-static` (R4.S7c part ii, freeze-driver ruling R92 2026-10-17).
# A constant rather than a flag because there is exactly one livespec core and
# it is PUBLIC: the anonymous https form is what lets the pod resolve core
# without being handed a credential, and a flag would be a way to repoint a gate
# at another tree. WHICH REF is per consumer and is derived below.
LIVESPEC_CORE_URL="https://github.com/thewoolleyman/livespec.git"
# What a consumer that pins no livespec release gets — the same fallback its own
# CI step takes when `.livespec.jsonc` carries no `pinned` field.
LIVESPEC_CORE_REF_FALLBACK="master"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root)         repo_root="$2"; shift 2 ;;
    --tree-hash)         tree_hash="$2"; shift 2 ;;
    --repo)              repo="$2"; shift 2 ;;
    --gated-repository)  gated_repository="$2"; shift 2 ;;
    --source-url)        source_url="$2"; shift 2 ;;
    --cpu)               cpu="$2"; shift 2 ;;
    --memory)            memory="$2"; shift 2 ;;
    --parallelism)       parallelism="$2"; shift 2 ;;
    --ttl-seconds)       ttl_seconds="$2"; shift 2 ;;
    --gate-ref)          gate_ref="$2"; shift 2 ;;
    --livespec-core-ref) livespec_core_ref="$2"; shift 2 ;;
    --check-suite)       check_suite+=("$2"); shift 2 ;;
    --private-sibling)   private_siblings+=("$2"); shift 2 ;;
    --private-sibling-secret) private_sibling_secret="$2"; shift 2 ;;
    --authority-skip-env)     authority_skip_env="$2"; shift 2 ;;
    --authority-skip-member)  authority_skip_members+=("$2"); shift 2 ;;
    *) echo "FATAL: unknown argument $1" >&2; exit 2 ;;
  esac
done
for v in repo_root tree_hash; do
  [ -n "${!v}" ] || { echo "FATAL: --${v//_/-} is required" >&2; exit 2; }
done
[ -d "${repo_root}" ] || { echo "FATAL: --repo-root ${repo_root} is not a directory" >&2; exit 2; }
[ -f "${TEMPLATE}" ] || { echo "FATAL: template not found: ${TEMPLATE}" >&2; exit 1; }

# A Kubernetes label value must accept it, and the tree hash is what makes every
# Job of one tree selectable now that the Job's own name is assigned by the API
# server, so refuse anything that is not a plain hex digest.
case "${tree_hash}" in
  *[!0-9a-f]* | "") echo "FATAL: --tree-hash must be lowercase hex: ${tree_hash}" >&2; exit 2 ;;
esac

[ -n "${repo}" ] || repo="$(basename "${repo_root}")"
[ -n "${source_url}" ] || source_url="git://git-gates.gates.svc.cluster.local/${repo}.git"
[ -n "${gate_ref}" ] || gate_ref="refs/gates/${tree_hash}"

# The ref goes into the pod's shell script and into two refspecs, so its
# character set is bounded HERE rather than trusted: a git ref name is
# alphanumerics with `._/-` and everything else is a way to write shell into a
# manifest. The `refs/gates/` prefix is required too — that namespace is what
# ./prune-gate-refs.sh sweeps, so a ref outside it is one nothing ever collects.
case "${gate_ref}" in
  refs/gates/?*) : ;;
  *) echo "FATAL: --gate-ref must name a ref under refs/gates/: ${gate_ref}" >&2; exit 2 ;;
esac
case "${gate_ref}" in
  *[!A-Za-z0-9._/-]*)
    echo "FATAL: --gate-ref '${gate_ref}' is not a plain git ref name" >&2
    exit 2 ;;
esac

# --- the gated repository's github.com identity (R4.S7 slice B) ---------------
# Derived from the gated clone's OWN origin, matched against the same two
# canonical forms `_branch_protection_api.py` accepts, so the renderer and the
# check cannot disagree about what a github.com remote looks like.
#
# UNDERIVABLE IS NOT FATAL. A repo with no origin, or one hosted elsewhere,
# renders an EMPTY value, which the checks read as "no repository was named" —
# exactly as if the variable were unset. That is the same disposition this
# template already takes for the GH_TOKEN Secret: the pod still starts and the
# two credential-reading targets fail naming what is missing, which tells an
# operator more than a render that refused. Refusing here would also make the
# renderer unusable for the fixture trees its own exit-test suite builds.
if [ -z "${gated_repository}" ] && command -v git > /dev/null 2>&1; then
  origin_url="$(git -C "${repo_root}" remote get-url origin 2> /dev/null || true)"
  # Shell patterns rather than a sed expression: the URL forms differ only in
  # the separator after the host (`/` for https, `:` for scp-style), and the
  # `.git`/trailing-slash suffixes strip cleanly with parameter expansion. An
  # ERE would need non-greedy matching, which POSIX ERE does not have.
  case "${origin_url}" in
    https://github.com/* | http://github.com/* | git@github.com:*)
      owner_repo="${origin_url#*github.com}"
      owner_repo="${owner_repo#[:/]}"
      owner_repo="${owner_repo%/}"
      owner_repo="${owner_repo%.git}"
      # Exactly two non-empty segments. A third would make the value a path to
      # something that is not a repository, which the checks refuse anyway.
      case "${owner_repo}" in
        */*/*) : ;;
        ?*/?*) gated_repository="${owner_repo}" ;;
      esac
      ;;
  esac
fi

# --- the private siblings, and the Secret whose NAME is all that is passed ---
# A private sibling needs a per-run Secret mount; a public one stays an
# anonymous clone. WHICH targets are private is decided on the PUSHING HOST,
# where the GitHub App credential exists — this renderer is told, never asked,
# and it carries only the Secret's NAME into the manifest. The token itself
# never enters this process: a manifest is stored by the API server and handed
# back by any `kubectl get job -o yaml`, so a credential interpolated here
# would be a credential published (the delegated pre-push gate's
# cross-repository siblings rule in SPECIFICATION/contracts.md).
if [ "${#private_siblings[@]}" -gt 0 ] && [ -z "${private_sibling_secret}" ]; then
  echo "FATAL: --private-sibling requires --private-sibling-secret" >&2
  exit 2
fi
# The name is reproduced verbatim into YAML, so it is held to the DNS-1123 shape
# Kubernetes accepts for a resource name — the same refusal-before-render
# posture the sibling urls below get, rather than letting the API server reject
# a manifest a gate has already waited on.
if [ -n "${private_sibling_secret}" ]; then
  case "${private_sibling_secret}" in
    *[!a-z0-9-]* | -* | *-)
      echo "FATAL: --private-sibling-secret '${private_sibling_secret}' is not a lowercase" \
           "alphanumeric-and-dash Kubernetes resource name" >&2
      exit 2 ;;
  esac
fi

# --- the livespec core ref THIS consumer pins (R4.S7c part ii) ---------------
# Derived from the gated clone's own `.livespec.jsonc` `compat.pinned`, which is
# the SAME field the consumer's own CI job resolves core at — so the gate and CI
# judge the tree against one core build rather than two. Read with the same
# first-match grep that CI step uses rather than a JSON parser, because the file
# is JSONC (comments) and the renderer must stay dependency-free.
#
# An ABSENT file or field is an ANSWER, not a refusal: the consumer pins
# nothing and gets the same `master` fallback its CI step takes.
#
# THE `|| true` IS WHAT MAKES THE FIELD'S ABSENCE AN ANSWER, and without it the
# sentence above was false: `grep` exits 1 when it matches nothing, `pipefail`
# carries that out of the pipeline, and `set -e` aborts an assignment whose
# command substitution failed — so a `.livespec.jsonc` carrying no `pinned`
# killed the renderer HERE, exit 1 with NOTHING on stderr, which the gate client
# reports as `NO_VERDICT: render-gate-job did not complete`. Unreachable until a
# repository had a reason to carry that file without pinning a release, which is
# exactly what registering cross-repo siblings gives it. Same disposition as the
# `|| true` on the `git remote get-url origin` read above.
if [ -z "${livespec_core_ref}" ] && [ -f "${repo_root}/.livespec.jsonc" ]; then
  livespec_core_ref="$(grep -oE '"pinned"[[:space:]]*:[[:space:]]*"[^"]*"' "${repo_root}/.livespec.jsonc" \
    | head -1 | sed -E 's/.*:[[:space:]]*"([^"]*)".*/\1/' || true)"
fi
[ -n "${livespec_core_ref}" ] || livespec_core_ref="${LIVESPEC_CORE_REF_FALLBACK}"
# The value goes into the pod's shell script, so the character set is bounded
# HERE rather than trusted — a git ref name is alphanumerics with `._/-` and
# everything else is a way to write shell into a manifest.
case "${livespec_core_ref}" in
  *[!A-Za-z0-9._/-]*)
    echo "FATAL: livespec core ref '${livespec_core_ref}' is not a plain git ref name" >&2
    exit 2 ;;
esac

# --- the cross-repo siblings this consumer's checks READ (livespec-dev-tooling-s35dcb)
# WHY THE POD HAS TO PROVISION THESE. livespec core's cross-repo readers —
# `doctor-no-cross-spec-reference` validating an `external_references` citation
# against the cited sibling's real headings, and the wiring-completeness arm
# reading each registered sibling's justfile — resolve a sibling at
# `$LIVESPEC_SIBLING_CLONES_ROOT/<sibling>` when that variable is set and at the
# manifest's `cross_repo_targets.<sibling>.local_clone` otherwise, which is
# `/data/projects/<sibling>`: a fleet-host path, present in no pod. AN ABSENT
# PATH DOES NOT ERROR THERE — it reads as an EMPTY heading set, every allowlist
# entry for that sibling is dropped, and a correctly allowlisted citation is
# reported "not allowlisted". Measured 2026-10-18 on gate-livespec-e0a55a1a58f6,
# which failed livespec SPECIFICATION/constraints.md:298 on a tree whose master
# CI was green and which passes the same check locally.
#
# THE CONSUMER'S OWN CI ALREADY DOES EXACTLY THIS, which is the standard a gate
# is held to: livespec's `.github/workflows/ci.yml` step "Clone sibling repos
# for cross-repo wiring check" shallow-clones its siblings from github.com into
# `$RUNNER_TEMP/sibling-clones` and exports the variable for
# `check-doctor-static`. These are anonymous fetches of PUBLIC repositories,
# the same kind as the livespec core fetch above, so no credential enters the
# pod for them either.
#
# WHICH SIBLINGS: every key of the gated repository's own `.livespec.jsonc`
# `cross_repo_targets`, which IS the map a reader looks a cited sibling up in —
# so a sibling a check can read about is a sibling the pod has. The repository's
# OWN key is deliberately NOT excluded: core's host detection keys on the
# project root's BASENAME, and a gate pod's root is `/workspace`, so a
# repository's own key resolves through the override like any other and would
# otherwise be the one missing path.
#
# A repository that registers no targets renders NO step and keeps the command
# it has today — the renderer substitutes an empty block, which removes the
# placeholder's whole line.
GATE_SIBLING_CLONES_ROOT="/tmp/gate-sibling-clones"

# Where the per-run token Secret is mounted when a PRIVATE sibling is named.
# One constant because two places have to agree inside one rendered manifest —
# the volumeMount and the clone command that reads `<mount>/token` — and they
# are written hundreds of lines apart.
GATE_PRIVATE_SIBLING_MOUNT="/run/secrets/gate-private-siblings"

# Read with awk rather than a JSON parser for the same reason the `compat.pinned`
# grep above is: the file is JSONC and this renderer must stay dependency-free.
# It walks brace DEPTH inside the `cross_repo_targets` object and emits one
# `<slug><TAB><github_url>` row per key.
#
# THE COMMENT STRIP RUNS ON A STRING-FREE COPY, and that is load-bearing rather
# than fastidious: a `github_url` value carries `//` in its scheme, so stripping
# `//`-comments off the raw line truncates the very value being read (it did,
# on the first draft). Taking the strings out first also keeps a brace inside
# any value or trailing comment from moving the depth counter.
read_cross_repo_targets() {
  awk '
    {
      line = $0
      clean = line
      gsub(/"[^"]*"/, "", clean)
      sub(/\/\/.*$/, "", clean)
    }
    clean !~ /[^ \t]/ { next }
    inside == 0 {
      if (line ~ /"cross_repo_targets"[ \t]*:/ && clean ~ /:[ \t]*\{/) { inside = 1; depth = 1 }
      next
    }
    {
      if (depth == 1 && clean ~ /:[ \t]*\{/ && match(line, /"[^"]+"[ \t]*:/)) {
        name = substr(line, RSTART + 1, RLENGTH - 1)
        sub(/"[ \t]*:$/, "", name)
        url = ""
      }
      if (depth == 2 && match(line, /"github_url"[ \t]*:[ \t]*"[^"]*"/)) {
        url = substr(line, RSTART, RLENGTH)
        sub(/^"github_url"[ \t]*:[ \t]*"/, "", url)
        sub(/"$/, "", url)
      }
      depth += gsub(/\{/, "{", clean) - gsub(/\}/, "}", clean)
      if (depth == 1 && name != "") { print name "\t" url; name = ""; url = "" }
      if (depth < 1) exit
    }
  ' "$1"
}

sibling_rows=()
if [ -f "${repo_root}/.livespec.jsonc" ]; then
  mapfile -t sibling_rows < <(read_cross_repo_targets "${repo_root}/.livespec.jsonc")
fi

gate_sibling_clone_lines=""
private_sibling_volume_mount=""
private_sibling_volume=""
if [ "${#sibling_rows[@]}" -gt 0 ]; then
  # NO `mkdir -p` FOR THE ROOT: `git clone` creates its destination and every
  # parent of it, so the first clone makes the root and a pre-created one would
  # be a directory a run that clones NOTHING still leaves behind.
  gate_sibling_clone_lines="export LIVESPEC_SIBLING_CLONES_ROOT='${GATE_SIBLING_CLONES_ROOT}'
echo \":: gate: cross-repo siblings -> LIVESPEC_SIBLING_CLONES_ROOT=${GATE_SIBLING_CLONES_ROOT}\""
fi
for row in ${sibling_rows[@]+"${sibling_rows[@]}"}; do
  sibling_name="${row%%$'\t'*}"
  sibling_url="${row#*$'\t'}"
  # Both values go into the pod's shell script, so their character sets are
  # bounded HERE rather than trusted. A slug is a repository name and a path
  # segment; everything else is a way to write shell into a manifest.
  case "${sibling_name}" in
    "" | *[!A-Za-z0-9._-]* | .* )
      echo "FATAL: .livespec.jsonc cross_repo_targets names '${sibling_name}', which is not a plain repository slug" >&2
      exit 1 ;;
  esac
  # ANONYMOUS https ON github.com, asserted rather than assumed. A url carrying
  # userinfo would put a credential into a manifest, and one pointing elsewhere
  # cannot be fetched by a pod holding no credential at all — either way the
  # answer is a refusal naming the sibling, not a gate that silently skips it
  # and reports green on a sibling nothing read.
  case "${sibling_url}" in
    https://github.com/?*/?*) : ;;
    *)
      echo "FATAL: .livespec.jsonc cross_repo_targets.${sibling_name} declares github_url '${sibling_url}', which is not an anonymous https://github.com/<owner>/<repo> url the gate pod can clone" >&2
      exit 1 ;;
  esac
  case "${sibling_url}" in
    *[!A-Za-z0-9:/._-]* | *@*)
      echo "FATAL: .livespec.jsonc cross_repo_targets.${sibling_name} declares github_url '${sibling_url}', which carries characters a gate manifest must not reproduce" >&2
      exit 1 ;;
  esac
  # PRIVATE OR PUBLIC — the only thing that differs is where the clone's
  # authorization comes from, and a public sibling keeps the bare `git clone` it
  # has today: the url is identical, the refusal below is identical, and the
  # difference is one env prefix. THE TOKEN IS NOT IN THE URL, deliberately: the
  # refusal message a few lines down reproduces the url into both stderr and the
  # termination message, so a credential embedded in it would be published by
  # the very path that reports the failure (implementation note 3 on
  # livespec-dev-tooling-7kvh2d). It is read out of the mounted Secret, inside
  # the pod, at clone time — `http.extraHeader` rather than a credential helper
  # because a helper needs a file git can execute and this needs no file at all.
  private=0
  for named_private in ${private_siblings[@]+"${private_siblings[@]}"}; do
    if [ "${named_private}" = "${sibling_name}" ]; then
      private=1
      break
    fi
  done
  clone_command="git clone --quiet --depth 1 '${sibling_url}' '${GATE_SIBLING_CLONES_ROOT}/${sibling_name}'"
  if [ "${private}" -eq 1 ]; then
    # The mount is declared once however many private siblings there are: ONE
    # token covers all of them, because the host mints it scoped to exactly the
    # set this gate run names.
    private_sibling_volume_mount="- name: ${private_sibling_secret}
  mountPath: ${GATE_PRIVATE_SIBLING_MOUNT}
  readOnly: true"
    private_sibling_volume="- name: ${private_sibling_secret}
  secret:
    secretName: ${private_sibling_secret}"
    # BASIC, NOT BEARER, and the scheme is the whole defect of R581: GitHub's
    # git smart-HTTP endpoint REJECTS an installation token presented as
    # `Authorization: Bearer`, and in a pod with no askPass that 401 surfaces as
    # `fatal: could not read Username for 'https://github.com'` — a message
    # naming neither the scheme nor the token. Measured 2026-10-22 with one
    # freshly minted token, the same two private repositories, and git with
    # every credential source disabled: `Bearer <token>` exited 128 on
    # `fatal: Authentication failed`, `Basic base64(x-access-token:<token>)`
    # exited 0. The username is the literal `x-access-token` and the token is
    # the password, which is the form GitHub documents for an installation
    # token over https.
    #
    # EVERY PART OF IT IS STILL DEFERRED INTO THE POD. The `$(...)` is written
    # into the manifest unevaluated, so the API server stores the encoding STEP
    # and never the encoded credential, exactly as it stored the `cat` before.
    # The inner command substitution strips the trailing newline a Secret file
    # may carry, and `base64` WRAPS at 76 columns — which a 60-odd byte payload
    # exceeds — so its output is joined back into one line: a header value
    # carrying a newline is not a header.
    clone_command="GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0='http.extraHeader' GIT_CONFIG_VALUE_0=\"Authorization: Basic \$(printf 'x-access-token:%s' \"\$(cat ${GATE_PRIVATE_SIBLING_MOUNT}/token)\" | base64 | tr -d '\\n')\" ${clone_command}"
  fi
  # SHALLOW, like the core fetch and like the consumer's own CI step: nothing
  # reads a sibling's history — a reader wants its current headings and its
  # current justfile — and a full clone of six siblings on a pod whose cache is
  # cold every run is bytes spent on nothing.
  #
  # THE FAILURE IS THE VERDICT. A sibling that will not clone is the one case
  # this step must never shrug off, because the shrug is indistinguishable from
  # success: the readers would carry on against an absent path and report green.
  # The termination-log write is best-effort for the same reason the preflight's
  # is — the message is EVIDENCE and the exit status is the verdict.
  gate_sibling_clone_lines="${gate_sibling_clone_lines}
if ! ${clone_command}; then
  unclonable=\"FATAL: cannot clone cross-repo sibling '${sibling_name}' from ${sibling_url}. Its checks would read the absent clone as an EMPTY tree and silently drop every allowlisted citation to it, so no recipe was run; this gate is RED.\"
  echo \"\${unclonable}\" >&2
  { printf '%s\\n' \"\${unclonable}\" > /dev/termination-log; } 2> /dev/null || true
  exit 1
fi
echo \":: gate: sibling ${sibling_name} at \$(git -C '${GATE_SIBLING_CLONES_ROOT}/${sibling_name}' rev-parse HEAD)\""
done

# --- requirement 1: the image comes from the gated repo's own workflow --------
workflow="${repo_root}/.github/workflows/ci.yml"
[ -f "${workflow}" ] || { echo "FATAL: ${workflow} not found — cannot resolve the gated repository's image" >&2; exit 1; }
# Every `image:` that is the first field of a `container:` block. Anchored to the
# container block so a `services:` image or a commented tag cannot be picked up.
mapfile -t images < <(grep -A1 -E '^[[:space:]]*container:[[:space:]]*$' "${workflow}" \
  | grep -oE 'image:[[:space:]]*[^[:space:]]+' \
  | sed -E 's/^image:[[:space:]]*//' | sort -u)
if [ "${#images[@]}" -eq 0 ]; then
  echo "FATAL: no container image found in ${workflow}" >&2
  exit 1
fi
if [ "${#images[@]}" -gt 1 ]; then
  echo "FATAL: ${workflow} declares ${#images[@]} distinct container images:" >&2
  printf '  %s\n' "${images[@]}" >&2
  echo "Refusing to guess which toolchain the gate should use." >&2
  exit 1
fi
image="${images[0]}"

# --- the gated repository's own check recipes --------------------------------
# No flag means the caller named no suite, which for the gate client means the
# repository declared nothing: it gets the SHARED PRE-PUSH SEQUENCE its own
# local fall-through runs — the worktree-pack install lefthook's `pre-push`
# block runs, the commit-refuse-hook install, and the ONE recipe that hook then
# calls, `check-pre-push` (freeze-driver rulings R92 and R100, 2026-10-17). A
# single `check` was this default before R92, and it is NOT that fall-through:
# the pod's `/workspace` is a `git init` + fetch rather than a bootstrapped
# clone, so without the installs two members judge the SANDBOX.
#
# THE LAST ENTRY CARRIES NO `name=value` OVERRIDE, which is R100. R92 spelled it
# `hook_gate=1 check`, but `hook_gate` is a `just` variable only
# livespec-dev-tooling's own justfile declares, and `just` refuses a
# command-line override of an undeclared variable — so every other consumer's
# Job died with `error: Variable 'hook_gate' overridden on the command line but
# not present in justfile` before its aggregate ran (measured 2026-10-17 on
# gate-livespec-orchestrator-beads-fabro-ee118f8fd5dc, on a tree green in CI).
# What IS uniform fleet-wide is the RECIPE NAME `check-pre-push`, which the
# preflight below can test for; a variable it cannot.
#
# The client decides the default too (`GATE_CHECK_SUITE_FALL_THROUGH`) and
# always passes it explicitly, so this is the fallback for a hand-run render on
# a delegating host. The two spellings are held together by
# `tests.consumer.test_delegated_gate_declared_recipe_scenarios`, which renders
# with no flag and compares. Never this repository's `warm-typecheck` or its own
# `hook_gate=1 check`, which no other repository carries — that constant is the
# defect livespec-dev-tooling-saxz removed.
if [ "${#check_suite[@]}" -eq 0 ]; then
  check_suite=("install-worktree-pack" "install-commit-refuse-hooks" "check-pre-push")
fi

# Each entry goes into the pod's shell script verbatim and its recipe name goes
# into an unquoted `for` list, so the character set is bounded HERE rather than
# trusted. `just` recipe names are kebab/underscore identifiers and an entry may
# carry `name=value` assignments and the spaces between them; nothing else can
# be a legitimate invocation, and everything else is a way to write shell into a
# manifest.
recipe_names=()
for entry in "${check_suite[@]}"; do
  case "${entry}" in
    "" | *[!A-Za-z0-9_.=\ -]*)
      echo "FATAL: --check-suite entry '${entry}' is not a plain just invocation" >&2
      exit 2 ;;
  esac
  recipe=""
  for token in ${entry}; do
    case "${token}" in
      *=*) continue ;;
      *)   recipe="${token}"; break ;;
    esac
  done
  if [ -z "${recipe}" ]; then
    echo "FATAL: --check-suite entry '${entry}' names no recipe, only assignments" >&2
    exit 2
  fi
  recipe_names+=("${recipe}")
done

# The preflight's `for` list: single-quoted so a name is one word there even
# though the character set above already forbids anything that could split.
quoted_recipe_names=""
for recipe in "${recipe_names[@]}"; do
  quoted_recipe_names="${quoted_recipe_names:+${quoted_recipe_names} }'${recipe}'"
done
# The invocations themselves, one per line, substituted as a BLOCK so the
# rendered manifest reads as the script it is rather than as one packed line.
gate_recipe_lines=""
for entry in "${check_suite[@]}"; do
  gate_recipe_lines="${gate_recipe_lines:+${gate_recipe_lines}
}just ${entry}"
done

# --- the members this Job must NOT run (livespec-dev-tooling-mex6ga) ---------
# The one exception in the "What the delegated gate runs" bullet of
# livespec-dev-tooling's SPECIFICATION/contracts.md: a member that declares it
# reads an AUTHORIZATION held outside the tree does not run in the gate Job,
# because the Job is handed no ledger credential and no admin-scoped token BY
# DESIGN. The pre-push gate runs it on the pushing host instead, against the same
# committed tree, and ANDs its result into the delegated verdict.
#
# WHICH MEMBERS, AND UNDER WHICH VARIABLE, IS DECIDED ON THE PUSHING HOST and
# this renderer is TOLD — the same posture the private siblings above take. The
# host already resolves the declaring members for its own half, so resolving them
# a second time in the pod would be a second answer that can disagree with the
# first, and a pod that skipped a member the host never ran is an unread
# authorization treated as granted.
#
# THE VARIABLE'S NAME IS THE CONSUMER'S OWN. livespec's `check` recipe reads its
# skip list from `SKIP_TARGETS` and livespec-overseer's from
# `LIVESPEC_CHECK_SKIP`, so a name baked in here would be right in one repository
# and silently inert in the other — and inert means the member runs, fails on the
# absent credential, and a correct tree reads as RED. Measured 2026-10-24 on gate
# Jobs gate-livespec-p87qc and gate-livespec-overseer-tpfd2, both of which
# refused a tree their own master CI called green.
#
# BOTH FLAGS OR NEITHER. A variable with no members would export an empty list,
# CLOBBERING any skip the consumer's own gate suite set; members with no variable
# name nowhere to put them. Either half alone is a caller defect, so it is refused
# before render rather than rendered into a Job that reads as told and was not.
authority_skip_block=""
if [ -n "${authority_skip_env}" ] || [ "${#authority_skip_members[@]}" -gt 0 ]; then
  if [ -z "${authority_skip_env}" ] || [ "${#authority_skip_members[@]}" -eq 0 ]; then
    echo "FATAL: --authority-skip-env and --authority-skip-member must be given together;" \
         "a variable with no members would clobber the consumer's own skip and members" \
         "with no variable name nowhere to go" >&2
    exit 2
  fi
  # Reproduced verbatim into the pod's shell script, so the character set is
  # bounded HERE rather than trusted: a shell variable name is an identifier and
  # anything else is a way to write shell into a manifest.
  case "${authority_skip_env}" in
    *[!A-Za-z0-9_]* | [0-9]*)
      echo "FATAL: --authority-skip-env '${authority_skip_env}' is not a plain shell" \
           "variable name" >&2
      exit 2 ;;
  esac
  for authority_member in ${authority_skip_members[@]+"${authority_skip_members[@]}"}; do
    case "${authority_member}" in
      "" | *[!A-Za-z0-9_.-]*)
        echo "FATAL: --authority-skip-member '${authority_member}' is not a plain just" \
             "recipe name" >&2
        exit 2 ;;
    esac
  done
  # `${array[*]}` joins on the first character of IFS, which is a space — the
  # separator every one of these recipes splits its skip list on.
  authority_skip_list="${authority_skip_members[*]}"
  # THE ECHO IS NOT DECORATION. The client STREAMS this pod's log as the verdict
  # an operator reads, so without it "was that member skipped, or did it pass?"
  # cannot be answered from a gate's own output — the same reason the livespec
  # core resolution above says itself out loud.
  authority_skip_block="export ${authority_skip_env}=\"${authority_skip_list}\"
echo \":: gate: NOT running ${authority_skip_list} here - each reads an authorization held outside the tree and this Job is handed none; the pushing host runs it against this same tree (skipped through this repository's own ${authority_skip_env})\""
fi

# --- substitution ------------------------------------------------------------
# `&`, `|` and `\` are the characters sed would reinterpret in a replacement with
# `|` as the delimiter. URLs and image references carry `/` and `:` freely, which
# is why the delimiter is `|` rather than `/`.
sed_escape() { printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'; }

rendered="$(cat "${TEMPLATE}")"
substitute() {
  local token="$1" value
  value="$(sed_escape "$2")"
  rendered="$(printf '%s\n' "${rendered}" | sed -e "s|@@${token}@@|${value}|g")"
}

# A MULTI-LINE value cannot ride the `sed` substitution above — the replacement
# would collapse onto one line and the block scalar would stop being a script.
# This one replaces the placeholder's whole LINE, re-using that line's own
# indentation for every line of the block, so the YAML stays well-formed
# whatever depth the token sits at. The placeholder must therefore be alone on
# its line, which it is.
substitute_block() {
  local token="$1"
  rendered="$(
    LIVESPEC_RENDER_TOKEN="@@${token}@@" LIVESPEC_RENDER_BLOCK="$2" awk '
      BEGIN {
        token = ENVIRON["LIVESPEC_RENDER_TOKEN"]
        count = split(ENVIRON["LIVESPEC_RENDER_BLOCK"], block, "\n")
      }
      index($0, token) > 0 {
        match($0, /^[ \t]*/)
        indent = substr($0, 1, RLENGTH)
        for (line = 1; line <= count; line++) { print indent block[line] }
        next
      }
      { print }
    ' <<< "${rendered}"
  )"
}

substitute REPO              "${repo}"
substitute GATE_REF          "${gate_ref}"
substitute GATED_REPOSITORY  "${gated_repository}"
substitute TREE_HASH         "${tree_hash}"
substitute IMAGE             "${image}"
substitute SOURCE_URL        "${source_url}"
substitute CPU               "${cpu}"
substitute MEMORY            "${memory}"
substitute PARALLELISM       "${parallelism}"
substitute TTL_SECONDS       "${ttl_seconds}"
substitute LIVESPEC_CORE_URL "${LIVESPEC_CORE_URL}"
substitute LIVESPEC_CORE_REF "${livespec_core_ref}"
substitute GATE_RECIPE_NAMES "${quoted_recipe_names}"
substitute_block GATE_RECIPES "${gate_recipe_lines}"
# An EMPTY block removes the placeholder's whole line, which is exactly what a
# repository registering no cross-repo siblings must render.
substitute_block GATE_SIBLING_CLONES "${gate_sibling_clone_lines}"
# EMPTY for a repository whose authority members this run could not establish,
# which removes the placeholder's whole line: such a Job runs the members it runs
# today, where an unreadable authorization FAILS rather than passing.
substitute_block GATE_AUTHORITY_SKIP "${authority_skip_block}"
substitute_block GATE_PRIVATE_SIBLING_VOLUME_MOUNT "${private_sibling_volume_mount}"
substitute_block GATE_PRIVATE_SIBLING_VOLUME "${private_sibling_volume}"

# A token added to the template without a matching substitution above is caught
# HERE, at render time, rather than by the API server or — worse — by a gate that
# runs against a nonsense value.
if leftover="$(printf '%s\n' "${rendered}" | grep -oE '@@[A-Z_]+@@' | sort -u)"; [ -n "${leftover}" ]; then
  echo "FATAL: unsubstituted placeholder(s) remain in the rendered manifest:" >&2
  printf '  %s\n' ${leftover} >&2
  exit 1
fi

printf '%s\n' "${rendered}"
