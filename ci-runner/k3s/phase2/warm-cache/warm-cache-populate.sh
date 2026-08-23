#!/usr/bin/env bash
# warm-cache-populate.sh — the ONE trusted writer of the fleet's warm uv cache
# lower, tier 1 of the cache tiers in the livespec repo's
# plan/fleet-ci-runner-pool/research/design.md ("Cache tiers, and the volume
# that holds them"), re-scoped to the k3s/ARC lane under livespec-s43svm.2.
#
# Runs INSIDE the `warm-cache-populate` CronJob (warm-cache-cronjob.yaml), in
# the same fabro sandbox image the fleet's CI jobs execute in, with the host
# volume /var/cache/ci-runner/warm mounted read-WRITE at $WARM_ROOT. Nothing
# else in the cluster mounts that path writable: every workflow pod mounts it
# READ-ONLY (../arc/hook-pod-template.yaml) and copies the current generation
# into its own ephemeral work volume before its first step runs. A job can
# read the warm lower; it can never write it. That is the same trust tiering
# the deleted podman lane enforced with a read-only overlay lower, realized
# here with a read-only hostPath + per-pod copy because an unprivileged pod
# cannot mount an overlay and uv refuses a read-only cache outright
# ("Failed to initialize cache ... Permission denied", measured 2026-08-23).
#
# GENERATIONS, not in-place writes. Readers `cp -a` the lower while this
# script may be writing it. Writing in place would let a reader copy a
# half-written entry, so each run builds a NEW generation directory,
# hardlink-seeded from the current one (same filesystem, so the seed is
# metadata-only and takes well under a second even for a multi-GB cache),
# syncs every routed repository's lockfile into it, and then publishes it with
# ONE atomic symlink rename. A reader that resolved the symlink before the
# flip keeps copying the previous generation, which this script keeps for one
# more cycle before pruning. The hardlink seed is safe because uv never
# mutates a cache file in place — it writes to a temporary path and renames —
# so a new generation's writes never reach the inodes the previous generation
# still points at.
#
# WHAT IS SYNCED: for every repository URL in $REPOS_FILE (one per line — the
# installer derives the list from ../arc/values-*.yaml, the live set of
# repositories routed to this pool), clone or fast-forward its default branch
# under $WARM_ROOT/src/<repo> and run `uv sync --frozen --all-groups
# --no-install-project --no-install-workspace` against THIS generation as
# UV_CACHE_DIR, into a throwaway environment that is deleted afterwards. The
# project itself is never built or installed: only its locked third-party
# dependency tree is fetched, unpacked, and left in the cache. A repository
# without a uv.lock is skipped, not failed.
#
# FAIL-SOFT PER REPOSITORY, FAIL-LOUD OVERALL: one repository's sync failing
# (a broken lock on its default branch, a PyPI outage mid-fetch) is logged
# and skipped so the others still refresh; the generation is still published
# because a partially-refreshed cache is strictly better than the previous
# one. The script exits non-zero at the end if ANY repository failed, so the
# CronJob's last run shows red and the failure is observable.
set -uo pipefail

WARM_ROOT="${WARM_ROOT:-/warm}"
REPOS_FILE="${REPOS_FILE:-/config/repos.txt}"
KEEP_GENERATIONS="${KEEP_GENERATIONS:-2}"
GENERATIONS_DIR="${WARM_ROOT}/uv-generations"
SRC_DIR="${WARM_ROOT}/src"
CURRENT_LINK="${WARM_ROOT}/uv"
SCRATCH="${SCRATCH:-$(mktemp -d)}"

log() { printf '[warm-cache-populate %s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

command -v uv >/dev/null || { log "FATAL: uv not on PATH"; exit 2; }
command -v git >/dev/null || { log "FATAL: git not on PATH"; exit 2; }
[ -f "${REPOS_FILE}" ] || { log "FATAL: repos file ${REPOS_FILE} not found"; exit 2; }
[ -d "${WARM_ROOT}" ] || { log "FATAL: WARM_ROOT ${WARM_ROOT} is not a directory"; exit 2; }

mkdir -p "${GENERATIONS_DIR}" "${SRC_DIR}"

generation="$(date -u +%Y%m%dT%H%M%SZ)"
new_gen="${GENERATIONS_DIR}/${generation}"
current_gen=""
if [ -L "${CURRENT_LINK}" ]; then
  current_gen="$(readlink -f "${CURRENT_LINK}" || true)"
fi

if [ -n "${current_gen}" ] && [ -d "${current_gen}" ]; then
  log "seeding generation ${generation} from $(basename "${current_gen}") (hardlinks)"
  cp -al "${current_gen}" "${new_gen}"
else
  log "no current generation; starting ${generation} empty"
  mkdir -p "${new_gen}"
fi

failed=()
synced=0
while IFS= read -r url || [ -n "${url}" ]; do
  case "${url}" in ''|'#'*) continue ;; esac
  name="$(basename "${url}" .git)"
  src="${SRC_DIR}/${name}"
  log "-- ${name}: ${url}"
  if [ -d "${src}/.git" ]; then
    if ! git -C "${src}" fetch --quiet --depth 1 origin HEAD \
       || ! git -C "${src}" reset --quiet --hard FETCH_HEAD; then
      log "   fetch failed; skipping"
      failed+=("${name}")
      continue
    fi
  else
    rm -rf "${src}"
    if ! git clone --quiet --depth 1 "${url}" "${src}"; then
      log "   clone failed; skipping"
      failed+=("${name}")
      continue
    fi
  fi
  if [ ! -f "${src}/uv.lock" ]; then
    log "   no uv.lock; skipping"
    continue
  fi
  venv="${SCRATCH}/venv-${name}"
  rm -rf "${venv}"
  if UV_CACHE_DIR="${new_gen}" UV_PROJECT_ENVIRONMENT="${venv}" \
     uv sync --frozen --all-groups --no-install-project --no-install-workspace \
       --project "${src}" --quiet; then
    synced=$((synced + 1))
    log "   synced"
  else
    log "   uv sync failed; skipping"
    failed+=("${name}")
  fi
  rm -rf "${venv}"
done < "${REPOS_FILE}"

# Publish: one atomic rename of a relative symlink, so the link stays valid
# wherever the warm root is mounted (readers see /var/cache/ci-runner/warm as
# a different path than this container does).
ln -sfn "uv-generations/${generation}" "${CURRENT_LINK}.tmp"
mv -T "${CURRENT_LINK}.tmp" "${CURRENT_LINK}"
log "published generation ${generation} (${synced} repositories synced, size $(du -sh "${new_gen}" | cut -f1))"

# Prune: keep the newest KEEP_GENERATIONS, oldest first. The one just
# published is always among those kept.
mapfile -t gens < <(find "${GENERATIONS_DIR}" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
if [ "${#gens[@]}" -gt "${KEEP_GENERATIONS}" ]; then
  for old in "${gens[@]:0:$(( ${#gens[@]} - KEEP_GENERATIONS ))}"; do
    log "pruning generation ${old}"
    rm -rf "${GENERATIONS_DIR:?}/${old}"
  done
fi

rm -rf "${SCRATCH}"
if [ "${#failed[@]}" -gt 0 ]; then
  log "FAILED repositories: ${failed[*]}"
  exit 1
fi
log "ok"
