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
#                      [--parallelism N] [--ttl-seconds N] [--job-name NAME]
#
# --repo defaults to the basename of --repo-root. --source-url defaults to the
# in-cluster read-only mirror R4.S4 builds. The resource defaults are the terms
# ../kueue/cluster-queue-gates.yaml quotas: 5 cpu / 6Gi, three concurrent gates
# under its 15 cpu / 24Gi.
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
cpu="5"; memory="6Gi"; parallelism="4"; ttl_seconds="3600"; job_name=""
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
    --job-name)          job_name="$2"; shift 2 ;;
    *) echo "FATAL: unknown argument $1" >&2; exit 2 ;;
  esac
done
for v in repo_root tree_hash; do
  [ -n "${!v}" ] || { echo "FATAL: --${v//_/-} is required" >&2; exit 2; }
done
[ -d "${repo_root}" ] || { echo "FATAL: --repo-root ${repo_root} is not a directory" >&2; exit 2; }
[ -f "${TEMPLATE}" ] || { echo "FATAL: template not found: ${TEMPLATE}" >&2; exit 1; }

# A Kubernetes object name and a label value must both accept it, and the tree
# hash goes into both, so refuse anything that is not a plain hex digest.
case "${tree_hash}" in
  *[!0-9a-f]* | "") echo "FATAL: --tree-hash must be lowercase hex: ${tree_hash}" >&2; exit 2 ;;
esac

[ -n "${repo}" ] || repo="$(basename "${repo_root}")"
[ -n "${source_url}" ] || source_url="git://git-gates.gates.svc.cluster.local/${repo}.git"
[ -n "${job_name}" ] || job_name="gate-${repo}-${tree_hash:0:12}"

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
substitute JOB_NAME          "${job_name}"
substitute REPO              "${repo}"
substitute GATED_REPOSITORY  "${gated_repository}"
substitute TREE_HASH         "${tree_hash}"
substitute IMAGE             "${image}"
substitute SOURCE_URL        "${source_url}"
substitute CPU               "${cpu}"
substitute MEMORY            "${memory}"
substitute PARALLELISM       "${parallelism}"
substitute TTL_SECONDS       "${ttl_seconds}"

# A token added to the template without a matching substitution above is caught
# HERE, at render time, rather than by the API server or — worse — by a gate that
# runs against a nonsense value.
if leftover="$(printf '%s\n' "${rendered}" | grep -oE '@@[A-Z_]+@@' | sort -u)"; [ -n "${leftover}" ]; then
  echo "FATAL: unsubstituted placeholder(s) remain in the rendered manifest:" >&2
  printf '  %s\n' ${leftover} >&2
  exit 1
fi

printf '%s\n' "${rendered}"
