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
# THE CARGO HALF (2026-09-04, plan ci-runner-cache-tiers, livespec-dev-tooling-
# oiltq3): the warm cargo cache is HOST-SERVED by the crates proxy
# (../crates-proxy/), not a lower copied into pods — per-job start writes are
# the pool's disk knee. This script's job for cargo is to PRE-WARM that proxy:
# for every routed repository with a Cargo.lock it runs `cargo fetch --locked`
# through the proxy into a throwaway CARGO_HOME, so every locked crate is
# cached before any job asks, and the cold cost (~300 upstream fetches per
# lockfile) lands on this timer, never on a job. Nothing from that fetch is
# kept here. It WARNS on any git+ source in a lockfile: the proxy serves the
# registry only, so those crates fetch from their forge in the job as they do
# on hosted runners (no routed lockfile has one today).
#
# THE COMPILATION CACHE'S ONE WRITER (B1, livespec-dev-tooling-ddiszt): for
# every routed repository with a Cargo.lock, when the sccache binary is mounted
# and the writer credential is present, this script builds the DEFAULT BRANCH
# with sccache as the writer against the host redis (../sccache/), so every
# job's dependency compiles (and unchanged-workspace compiles) are hits. It
# builds at the SAME path a job checks out to (/__w/<repo>/<repo>) with the
# SAME CARGO_HOME (/root/.cargo, the image's), because sccache hashes absolute
# paths and cargo's -C metadata hashes a workspace member's path: a build
# elsewhere would fill the cache with entries no job can hit. The four cargo
# invocations mirror the console matrix's compile shapes (build --all-targets,
# test --no-run, check --all-targets for clippy's dependency graph, build
# --release) with --all-features as the matrix uses. It runs under nice/ionice
# at the repository's own build.jobs cap and skips entirely when its MARKER KEY
# in redis (`livespec:sccache:populated:<repo>` = `<sha>@<toolchain>`) already
# names the current default-branch SHA and toolchain: the marker lives in the
# cache it describes, so a redis restart (RAM-only, no persistence) or an
# eviction of the marker triggers a rebuild on the next tick, and an
# unchanged branch costs nothing. Nothing from the build is kept here.
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
CRATES_PROXY_URL="${CRATES_PROXY_URL:-http://crates-proxy.ci-crates-proxy.svc.cluster.local:3080}"
SCCACHE_BIN="${SCCACHE_BIN:-/opt/ci-runner/bin/sccache}"
SCCACHE_REDIS_ENDPOINT="${SCCACHE_REDIS_ENDPOINT:-redis://sccache-redis.ci-sccache.svc.cluster.local:6379}"
SCCACHE_REDIS_WRITER_USERNAME="${SCCACHE_REDIS_WRITER_USERNAME:-}"
SCCACHE_REDIS_WRITER_PASSWORD="${SCCACHE_REDIS_WRITER_PASSWORD:-}"
JOB_WORK_ROOT="${JOB_WORK_ROOT:-/__w}"
GENERATIONS_DIR="${WARM_ROOT}/uv-generations"
SRC_DIR="${WARM_ROOT}/src"
CURRENT_LINK="${WARM_ROOT}/uv"
SCRATCH="${SCRATCH:-$(mktemp -d)}"

log() { printf '[warm-cache-populate %s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# redis_cmd [--auth USER PASS] CMD ARG... — one RESP round trip to the host
# redis (python3 is in the image; redis-cli is not). Prints a bulk/simple
# reply, "(nil)" for null, exits 1 on an error reply or a connection failure.
redis_cmd() {
  local user="" pass=""
  if [ "${1:-}" = "--auth" ]; then user="$2"; pass="$3"; shift 3; fi
  REDIS_USER="${user}" REDIS_PASS="${pass}" python3 - "${SCCACHE_REDIS_ENDPOINT}" "$@" <<'PY'
import os, socket, sys
from urllib.parse import urlparse
u = urlparse(sys.argv[1]); host, port = u.hostname, u.port or 6379
def enc(*parts):
    out = b"*%d\r\n" % len(parts)
    for p in parts:
        b = p.encode(); out += b"$%d\r\n%s\r\n" % (len(b), b)
    return out
def read_reply(f):
    line = f.readline()
    if not line: raise SystemExit("EOF")
    t, body = chr(line[0]), line[1:-2].decode()
    if t == "+": return body
    if t == "-": raise SystemExit("redis error: " + body)
    if t == ":": return body
    if t == "$":
        n = int(body)
        if n < 0: return "(nil)"
        data = f.read(n + 2)[:-2]; return data.decode()
    if t == "*":
        return " ".join(str(read_reply(f)) for _ in range(int(body)))
    raise SystemExit("unexpected reply: " + line.decode())
try:
    s = socket.create_connection((host, port), timeout=5)
except OSError as e:
    raise SystemExit("connect failed: %s" % e)
f = s.makefile("rb")
if os.environ.get("REDIS_USER"):
    s.sendall(enc("AUTH", os.environ["REDIS_USER"], os.environ["REDIS_PASS"])); read_reply(f)
s.sendall(enc(*sys.argv[2:]))
print(read_reply(f))
PY
}

command -v uv >/dev/null || { log "FATAL: uv not on PATH"; exit 2; }
command -v git >/dev/null || { log "FATAL: git not on PATH"; exit 2; }
[ -f "${REPOS_FILE}" ] || { log "FATAL: repos file ${REPOS_FILE} not found"; exit 2; }
[ -d "${WARM_ROOT}" ] || { log "FATAL: WARM_ROOT ${WARM_ROOT} is not a directory"; exit 2; }

mkdir -p "${GENERATIONS_DIR}" "${SRC_DIR}"

# One cargo config for everything cargo does in this container: the crates
# proxy as crates.io, incremental off, a network retry budget — the SAME
# stanzas the hook template writes into job containers. Everything cargo-
# related that differs from a job goes in THIS FILE and never in the
# environment: sccache hashes every CARGO_* environment variable into a
# cache key (all but CARGO_MAKEFLAGS, CARGO_BUILD_JOBS, CARGO_REGISTRIES_*
# and CARGO_ENCODED_RUSTFLAGS; src/compiler/rust.rs), and cargo config is not
# hashed — the first writer build set CARGO_INCREMENTAL/CARGO_NET_RETRY/
# CARGO_TERM_COLOR in its env and every job missed (2026-09-04). The image's
# own /root/.cargo is CARGO_HOME here, as in a job.
mkdir -p /.cargo
printf '[source.crates-io]\nreplace-with = "ci-runner-pool"\n\n[source.ci-runner-pool]\nregistry = "sparse+%s/index/"\n\n[build]\nincremental = false\n\n[net]\nretry = 5\n' \
  "${CRATES_PROXY_URL}" > /.cargo/config.toml

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
cargo_warmed=0
sccache_built=0
sccache_skipped=0
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
  if [ -f "${src}/uv.lock" ]; then
    venv="${SCRATCH}/venv-${name}"
    rm -rf "${venv}"
    if UV_CACHE_DIR="${new_gen}" UV_PROJECT_ENVIRONMENT="${venv}" \
       uv sync --frozen --all-groups --no-install-project --no-install-workspace \
         --project "${src}" --quiet; then
      synced=$((synced + 1))
      log "   uv: synced"
    else
      log "   uv sync failed; skipping"
      failed+=("${name}")
    fi
    rm -rf "${venv}"
  else
    log "   no uv.lock; nothing to sync for uv"
  fi
  if [ -f "${src}/Cargo.lock" ]; then
    if ! command -v cargo >/dev/null; then
      log "   Cargo.lock present but cargo is not on PATH (this image lacks the Rust layer); skipping the cargo pre-warm"
      failed+=("${name}:cargo")
    else
      if grep -q 'source = "git+' "${src}/Cargo.lock"; then
        log "   WARN: Cargo.lock carries git+ sources; the crates proxy serves the registry only, those fetch from their forge in every job"
      fi
      # cd, not --manifest-path: rustup resolves rust-toolchain.toml from cwd.
      # /.cargo/config.toml (above) routes this through the proxy; the
      # extraction into /root/.cargo/registry is reused by the build below.
      if (cd "${src}" && cargo fetch --locked --quiet); then
        cargo_warmed=$((cargo_warmed + 1))
        log "   cargo: every locked crate warmed through ${CRATES_PROXY_URL}"
      else
        log "   cargo fetch through the proxy failed; skipping"
        failed+=("${name}:cargo")
      fi
      # ---- the compilation cache's writer build (see the header) ----
      if [ ! -x "${SCCACHE_BIN}" ]; then
        log "   sccache: ${SCCACHE_BIN} not mounted; no compilation-cache build"
        sccache_skipped=$((sccache_skipped + 1))
      elif [ -z "${SCCACHE_REDIS_WRITER_PASSWORD}" ] || [ -z "${SCCACHE_REDIS_WRITER_USERNAME}" ]; then
        log "   sccache: no writer credential in this pod (converge-sccache-redis.sh projects it); no compilation-cache build"
        failed+=("${name}:sccache-no-credential")
      else
        sha="$(git -C "${src}" rev-parse HEAD)"
        toolchain="$(cd "${src}" && rustc --version 2>/dev/null | awk '{print $2}')"
        marker_key="livespec:sccache:populated:${name}"
        want="${sha}@${toolchain}"
        have="$(redis_cmd GET "${marker_key}" 2>/dev/null || echo "(unreachable)")"
        if [ "${have}" = "${want}" ]; then
          log "   sccache: cache already holds ${sha:0:8}@${toolchain}; no build"
          sccache_skipped=$((sccache_skipped + 1))
        elif [ "${have}" = "(unreachable)" ]; then
          log "   sccache: redis unreachable at ${SCCACHE_REDIS_ENDPOINT}; no build"
          failed+=("${name}:sccache-unreachable")
        else
          build_dir="${JOB_WORK_ROOT}/${name}/${name}"
          rm -rf "${JOB_WORK_ROOT:?}/${name}"
          mkdir -p "${JOB_WORK_ROOT}/${name}"
          cp -a "${src}" "${build_dir}"
          log "   sccache: building ${sha:0:8}@${toolchain} as the writer (cache had: ${have})"
          build_ok=true
          for invocation in \
              "build --workspace --all-targets --all-features" \
              "test --workspace --all-features --no-run" \
              "check --workspace --all-targets --all-features" \
              "build --release --workspace"; do
            t0=$(date +%s)
            # No CARGO_* in this env, ever (see the config note above): the
            # wrapper via RUSTC_WRAPPER and the writer credential via SCCACHE_*
            # are not hashed; a CARGO_* here would key the cache to this
            # process and away from every job.
            # shellcheck disable=SC2086  # the invocation is a word list on purpose
            if (cd "${build_dir}" && RUSTC_WRAPPER="${SCCACHE_BIN}" \
                  SCCACHE_REDIS_ENDPOINT="${SCCACHE_REDIS_ENDPOINT}" \
                  SCCACHE_REDIS_USERNAME="${SCCACHE_REDIS_WRITER_USERNAME}" \
                  SCCACHE_REDIS_PASSWORD="${SCCACHE_REDIS_WRITER_PASSWORD}" \
                  SCCACHE_REDIS_RW_MODE=READ_WRITE \
                  nice -n 19 ionice -c 3 cargo ${invocation} --quiet); then
              log "   sccache: cargo ${invocation%% *} ok in $(( $(date +%s) - t0 )) s"
            else
              log "   sccache: cargo ${invocation} FAILED after $(( $(date +%s) - t0 )) s"
              build_ok=false
              break
            fi
          done
          SCCACHE_REDIS_ENDPOINT="${SCCACHE_REDIS_ENDPOINT}" \
            SCCACHE_REDIS_USERNAME="${SCCACHE_REDIS_WRITER_USERNAME}" \
            SCCACHE_REDIS_PASSWORD="${SCCACHE_REDIS_WRITER_PASSWORD}" \
            "${SCCACHE_BIN}" --show-stats 2>/dev/null | grep -E "Compile requests|Cache hits|Cache misses|Cache errors|Non-cacheable" | sed 's/^/   sccache stats: /' || true
          "${SCCACHE_BIN}" --stop-server >/dev/null 2>&1 || true
          if [ "${build_ok}" = true ]; then
            if redis_cmd --auth "${SCCACHE_REDIS_WRITER_USERNAME}" "${SCCACHE_REDIS_WRITER_PASSWORD}" SET "${marker_key}" "${want}" >/dev/null; then
              sccache_built=$((sccache_built + 1))
              log "   sccache: cache now holds ${sha:0:8}@${toolchain} (marker set)"
            else
              log "   sccache: build ok but the marker SET failed; it will rebuild next tick"
              failed+=("${name}:sccache-marker")
            fi
          else
            failed+=("${name}:sccache-build")
          fi
          rm -rf "${JOB_WORK_ROOT:?}/${name}"
        fi
      fi
    fi
  fi
done < "${REPOS_FILE}"

# Publish: one atomic rename of a relative symlink, so the link stays valid
# wherever the warm root is mounted (readers see /var/cache/ci-runner/warm as
# a different path than this container does).
ln -sfn "uv-generations/${generation}" "${CURRENT_LINK}.tmp"
mv -T "${CURRENT_LINK}.tmp" "${CURRENT_LINK}"
log "published generation ${generation} (${synced} repositories synced for uv, ${cargo_warmed} pre-warmed for cargo, sccache builds: ${sccache_built} built / ${sccache_skipped} skipped, size $(du -sh "${new_gen}" | cut -f1))"

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
