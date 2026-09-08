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
#                      [--source-url URL] [--cpu N] [--memory SIZE]
#                      [--parallelism N] [--ttl-seconds N] [--job-name NAME]
#
# --repo defaults to the basename of --repo-root. --source-url defaults to the
# in-cluster read-only mirror R4.S4 builds. The resource defaults are the terms
# ../kueue/cluster-queue-gates.yaml quotas: 5 cpu / 6Gi, three concurrent gates
# under its 15 cpu / 24Gi.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="${GATE_JOB_TEMPLATE:-${SCRIPT_DIR}/gate-job-template.yaml}"

repo_root=""; tree_hash=""; repo=""; source_url=""
cpu="5"; memory="6Gi"; parallelism="4"; ttl_seconds="3600"; job_name=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root)    repo_root="$2"; shift 2 ;;
    --tree-hash)    tree_hash="$2"; shift 2 ;;
    --repo)         repo="$2"; shift 2 ;;
    --source-url)   source_url="$2"; shift 2 ;;
    --cpu)          cpu="$2"; shift 2 ;;
    --memory)       memory="$2"; shift 2 ;;
    --parallelism)  parallelism="$2"; shift 2 ;;
    --ttl-seconds)  ttl_seconds="$2"; shift 2 ;;
    --job-name)     job_name="$2"; shift 2 ;;
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
substitute JOB_NAME    "${job_name}"
substitute REPO        "${repo}"
substitute TREE_HASH   "${tree_hash}"
substitute IMAGE       "${image}"
substitute SOURCE_URL  "${source_url}"
substitute CPU         "${cpu}"
substitute MEMORY      "${memory}"
substitute PARALLELISM "${parallelism}"
substitute TTL_SECONDS "${ttl_seconds}"

# A token added to the template without a matching substitution above is caught
# HERE, at render time, rather than by the API server or — worse — by a gate that
# runs against a nonsense value.
if leftover="$(printf '%s\n' "${rendered}" | grep -oE '@@[A-Z_]+@@' | sort -u)"; [ -n "${leftover}" ]; then
  echo "FATAL: unsubstituted placeholder(s) remain in the rendered manifest:" >&2
  printf '  %s\n' ${leftover} >&2
  exit 1
fi

printf '%s\n' "${rendered}"
