#!/usr/bin/env bash
# warm-cache-populate.sh — the ONE trusted writer of the fleet's warm uv cache
# lower, tier 1 of the cache tiers in the livespec repo's
# plan/fleet-ci-runner-pool/research/design.md ("Cache tiers, and the volume
# that holds them"), re-scoped to the k3s/ARC lane under livespec-s43svm.2.
#
# Runs INSIDE the `warm-cache-populate` CronJob (warm-cache-cronjob.yaml), in
# the same fabro sandbox image the fleet's CI jobs execute in, with the host
# directory /var/lib/rancher/k3s/storage/.warm (a hidden sibling of the runner
# work volumes on the ci-workvols tier) mounted read-WRITE at $WARM_ROOT.
# Nothing else in the cluster mounts that path at all: the local-path
# provisioner's setup script (../local-path-provisioner/) REFLINK-COPIES the
# current generation into each work volume's _warm/uv when the volume is
# created (XFS with reflink on the ci-workvols tier since 2026-09-06), and a
# job only ever sees that seed: every inode its own, the data blocks shared
# copy-on-write, so a job's writes land in its volume and never here. That
# is the enforcement the "Runner-pool build cache tiers" clause requires
# (livespec-dev-tooling-hmv2bo; README.md "The hazard, closed"). The
# hardlink seed of 2026-09-04 to 2026-09-06 had no such enforcement -- the
# workflow pod's volume is idmapped, its root is uid 0 there, and the
# root-owned shared inodes were writable from it; owning them as a uid no
# pod maps broke every job (uv's cache init opens CACHEDIR.TAG for writing,
# and the kernel refuses any write-open, unlink or rename-over on an inode
# whose owner the pod does not map) -- the record is livespec plan
# ci-runner-pod-lifecycle-reliability research/006.
# The podman lane enforced the same trust tiering with a read-only overlay
# lower; here an unprivileged pod cannot mount an overlay and uv refuses a
# read-only cache outright ("Failed to initialize cache ... Permission
# denied", measured 2026-08-23).
#
# GENERATIONS, not in-place writes. Readers reflink-copy from the lower
# while this script may be writing it. Writing in place would let a reader
# copy a half-written entry, so each run that rebuilds creates a NEW
# generation directory, fills it, and publishes it with ONE atomic symlink
# rename. A reader resolves the symlink once before it starts copying, so
# one that resolved it before the flip keeps seeding from the previous
# generation, which this script keeps for one more cycle before pruning —
# and a seeded volume's copies outlive even a pruned generation (their
# blocks stay referenced).
#
# EVERY GENERATION IS BUILT FROM EMPTY (livespec-41w4, Carrier F2 of the
# livespec plan ci-runner-pod-lifecycle-reliability). Until 2026-09-06 a new
# generation was hardlink-seeded from its predecessor and nothing pruned it:
# every version ever locked accumulated, and the generation grew from 379 MB
# / 8,070 files (2026-08-23) to 1,388 MB / 159,409 files (2026-09-04), the
# per-start seed cost growing with it (research/005). Now a generation is the
# union of the routed repositories' CURRENT lockfiles BY CONSTRUCTION: it
# starts as an empty directory and holds only what `uv sync --frozen` of
# those locks put there. The from-empty build is affordable because uv fetches
# through the host-served PyPI files proxy (./pypi-proxy/): 379 MB and 8,070
# files for nine locks in ~14 s, with ~105 MB of PyPI transfer avoided per
# rebuild (README.md "From-empty build cost").
#
# THE FILE HOST IS REWRITTEN IN THE CLONE'S LOCK. `uv sync --frozen` downloads
# every locked distribution from the ABSOLUTE files.pythonhosted.org URL in
# uv.lock; UV_DEFAULT_INDEX / UV_INDEX_URL serve only unlocked build
# dependencies, so an index proxy caches nothing for a frozen sync (measured
# 2026-09-04: a frozen sync with UV_DEFAULT_INDEX pointed at a bogus port
# succeeded). What works is the prefix swap this script makes in ITS OWN
# CLONE of each lock, `https://files.pythonhosted.org/packages/` ->
# `$PYPI_FILES_PROXY/packages/`, with `source = { registry = ... }` untouched:
# the wheels come through the proxy, the lock's hashes are still enforced (a
# tampered proxied wheel fails the sync), the cache lands under
# `wheels-v5/pypi/...` exactly as a job's ORIGINAL lock expects, and that
# original lock syncs `--offline` from the generation. No UV_DEFAULT_INDEX is
# set, so build dependencies stay in the `pypi` bucket too. The clone is
# reset to the fetched tip on the next run, so the rewrite never leaks.
#
# NOTHING IS PUBLISHED UNVERIFIED. After the syncs, ./verify-uv-cache.py (with
# ./uv_cache_layout.py, the cache-layout half it imports) maps
# every entry of the new generation back to a (name, version) and checks it
# against the union of the routed locks (build dependencies derived from
# [build-system].requires are the one legitimate class outside every lock).
# Any unreferenced or unknown entry fails the publish: the entries are named
# in this log, the directory is kept beside the generations as
# <stamp>.unverified for one cycle, the symlink is untouched, the job exits 1.
# `uv cache prune` / `uv cache clean` are NOT used anywhere here and MUST NOT
# be run against uv-generations/ from the host: neither knows about
# lockfiles, and both DESTROY a generation reached through a copy or a link
# (README.md "Verifier").
#
# NOTHING IS PUBLISHED OVER BUDGET. The generation's bytes (du -sb) and
# regular-file count must each be at or under WARM_BUDGET_BYTES /
# WARM_BUDGET_FILES (the `warm-cache-budget` ConfigMap; fixed numbers derived
# from the measured union in README.md "Budget", not a ratchet on the last
# build). Over either: the directory is renamed <stamp>.refused, the previous
# generation stays live, last-run.json records refused=1 with both numbers,
# the job exits 3 — the alarm the sweep's livespec.ci_warm.refused gauge
# carries.
#
# A RUN THAT CHANGES NOTHING BUILDS NOTHING. Every routed uv.lock is hashed
# against the published generation's manifest; when every lock is unchanged,
# the published generation still verifies against them, and it is younger
# than WARM_FORCE_REBUILD_SECONDS, the run records rebuilt=0 and keeps it (the
# generation directory's mtime is touched so ci-cache-gauges.sh's
# generation_age_s reads "last verified current", which is what the stale
# trigger asks). The forced rebuild past that age keeps the from-empty path
# exercised at least once per 24 h.
#
# METRICS go through a file, not the network. The CronJob has no hostNetwork
# (it runs PyPI build backends; do not add it), and the host collector's
# OTLP receiver listens on loopback only, so this script writes
# $WARM_ROOT/last-run.json (one document per run, refused runs included,
# written before any non-zero exit) and the host lifecycle sweep
# (../runner-pod-lifecycle/scan-runner-pod-lifecycle.sh) emits
# livespec.ci_warm.* from it once per new run_id. The proxy hit ratio is
# derived without log parsing: the proxy store is mounted read-only at
# $PROXY_STORE, its object count is read before and after the build, and the
# denominator is the number of uv pointer files in the new generation that
# name the proxy (1 - new_objects / proxied_downloads).
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
# GUARDRAILS on that build (v054 populator-guardrails clause; livespec-dev-
# tooling-osmzo4): it runs at the repository's own build.jobs cap under
# `nice -n 19 ionice -c 3`, inside the CronJob's CPU limit, and it does NOT
# START while the pool's admitted-job count — Kueue ClusterQueue
# status.admittedWorkloads summed, read through the API with this pod's
# read-only ServiceAccount — is above $POPULATE_ADMITTED_JOB_THRESHOLD. A
# tick that finds the pool busy logs the skip and moves on; the marker key
# makes the next idle tick build, so a skipped tick costs nothing. A count
# that cannot be READ is treated as busy (no build) AND recorded as a failed
# step, so a broken read shows up in the manifest and on the populate-failing
# trigger rather than silently starving the cache.
#
# WHAT IS SYNCED: for every repository URL in $REPOS_FILE (one per line — the
# installer derives the list from ../arc/values-*.yaml, the live set of
# repositories routed to this pool), clone or fast-forward its default branch
# under $WARM_ROOT/src/<repo> and, when a rebuild is due, run `uv sync
# --frozen --all-groups --no-install-project --no-install-workspace` against
# the NEW generation as UV_CACHE_DIR, into a throwaway environment that is
# deleted afterwards. The project itself is never built or installed: only its
# locked third-party dependency tree is fetched, unpacked, and left in the
# cache. A repository without a uv.lock is skipped, not failed.
#
# FAIL-SOFT PER REPOSITORY, FAIL-LOUD OVERALL: one repository's sync failing
# (a broken lock on its default branch, a PyPI outage mid-fetch) is logged
# and skipped so the others still refresh; the generation is still published
# (if it verifies and fits the budget) because a partially-refreshed cache is
# strictly better than the previous one, and the failed repository's lock is
# left out of the manifest so the next run rebuilds (its packages are absent
# from the new generation — from-empty means a failed repository's jobs run
# cold for one tick, not that the fleet keeps stale entries). When EVERY
# routed lock fails to sync the new generation is discarded and the
# published one stays. The script exits non-zero at the end if ANY
# repository failed, so the CronJob's last run shows red and the failure is
# observable.
#
# EXIT CODES: 0 every step ok (rebuilt or verified-unchanged); 1 a repository
# step failed, or the verifier rejected the new generation; 2 a preflight
# failed (nothing built); 3 the new generation was over budget and refused.
# last-run.json is written on every path but 2.
set -uo pipefail

WARM_ROOT="${WARM_ROOT:-/warm}"
REPOS_FILE="${REPOS_FILE:-/config/repos.txt}"
KEEP_GENERATIONS="${KEEP_GENERATIONS:-2}"
VERIFIER="${VERIFIER:-/scripts/verify-uv-cache.py}"
# The host-served PyPI files proxy (./pypi-proxy/), probed at /health; an
# unreachable proxy means a direct build and proxy_unavailable=1, never a
# failed run.
PYPI_FILES_PROXY="${PYPI_FILES_PROXY:-http://pypi-proxy.ci-warm-cache.svc.cluster.local:8081}"
# The proxy's object store, mounted read-only, for the hit-ratio count; when
# it is not mounted or not readable the ratio is recorded as null.
PROXY_STORE="${PROXY_STORE:-/proxy-store}"
# The budget (both required; the CronJob injects them from the
# warm-cache-budget ConfigMap).
WARM_BUDGET_BYTES="${WARM_BUDGET_BYTES:-}"
WARM_BUDGET_FILES="${WARM_BUDGET_FILES:-}"
# A published generation older than this is rebuilt even when no lock changed.
WARM_FORCE_REBUILD_SECONDS="${WARM_FORCE_REBUILD_SECONDS:-86400}"
# NEGATIVE-TEST HOOK: a uv project directory (pyproject.toml + uv.lock) synced
# into the new generation AFTER the routed repositories and BEFORE the
# verifier, so an operator can prove the verifier refuses an unreferenced
# entry (README.md "Acceptance"). Never set on the CronJob itself.
WARM_INJECT_TEST="${WARM_INJECT_TEST:-}"
CRATES_PROXY_URL="${CRATES_PROXY_URL:-http://crates-proxy.ci-crates-proxy.svc.cluster.local:3080}"
SCCACHE_BIN="${SCCACHE_BIN:-/opt/ci-runner/bin/sccache}"
SCCACHE_REDIS_ENDPOINT="${SCCACHE_REDIS_ENDPOINT:-redis://sccache-redis.ci-sccache.svc.cluster.local:6379}"
SCCACHE_REDIS_WRITER_USERNAME="${SCCACHE_REDIS_WRITER_USERNAME:-}"
SCCACHE_REDIS_WRITER_PASSWORD="${SCCACHE_REDIS_WRITER_PASSWORD:-}"
JOB_WORK_ROOT="${JOB_WORK_ROOT:-/__w}"
POPULATE_ADMITTED_JOB_THRESHOLD="${POPULATE_ADMITTED_JOB_THRESHOLD:-16}"
K8S_SA_DIR="${K8S_SA_DIR:-/var/run/secrets/kubernetes.io/serviceaccount}"
GENERATIONS_DIR="${WARM_ROOT}/uv-generations"
SRC_DIR="${WARM_ROOT}/src"
CURRENT_LINK="${WARM_ROOT}/uv"
LAST_RUN="${WARM_ROOT}/last-run.json"
SCRATCH="${SCRATCH:-$(mktemp -d)}"
PYPI_FILES_PREFIX="https://files.pythonhosted.org/packages/"

log() { printf '[warm-cache-populate %s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# admitted_jobs — the pool's admitted-job count: Kueue ClusterQueue
# status.admittedWorkloads summed across every queue, read through the API
# server with this pod's ServiceAccount (get/list clusterqueues only).
# Prints an integer; exits 1 when the read fails (treated as busy by the
# caller).
admitted_jobs() {
  local token
  [ -r "${K8S_SA_DIR}/token" ] || return 1
  token="$(cat "${K8S_SA_DIR}/token")"
  curl --silent --fail --max-time 10 \
    --cacert "${K8S_SA_DIR}/ca.crt" -H "Authorization: Bearer ${token}" \
    "https://kubernetes.default.svc/apis/kueue.x-k8s.io/v1beta2/clusterqueues" \
  | python3 -c 'import json,sys; print(sum(int((i.get("status") or {}).get("admittedWorkloads") or 0) for i in json.load(sys.stdin)["items"]))'
}

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

# gen_bytes DIR / gen_files DIR — the two budget axes, measured the same way
# ci-cache-gauges.sh measures the live generation (apparent bytes; regular
# files, so uv's pointer symlinks do not count).
gen_bytes() { du -sb "$1" | cut -f1; }
gen_files() { find "$1" -type f | wc -l; }

# proxy_store_objects — the number of cached objects in the proxy store (one
# regular file per object; the store is FLAT so a capability-less reader can
# list it, see pypi-proxy/pypi-proxy.yaml). Prints nothing when unreadable.
proxy_store_objects() {
  [ -d "${PROXY_STORE}" ] && [ -r "${PROXY_STORE}" ] || return 1
  find "${PROXY_STORE}" -maxdepth 1 -type f 2>/dev/null | wc -l
}

# manifest_field FILE KEY — one top-level scalar from a JSON manifest, or
# nothing when the file or the key is absent.
manifest_field() {
  [ -r "$1" ] || return 1
  python3 -c 'import json,sys
d = json.load(open(sys.argv[1])); v = d.get(sys.argv[2])
sys.exit(1) if v is None else print(v)' "$1" "$2" 2>/dev/null
}

# ---------------------------------------------------------------------------
# PREFLIGHT — fail-closed, before anything is touched.
command -v uv >/dev/null || { log "FATAL: uv not on PATH"; exit 2; }
command -v git >/dev/null || { log "FATAL: git not on PATH"; exit 2; }
command -v python3 >/dev/null || { log "FATAL: python3 not on PATH"; exit 2; }
python3 -c 'import tomllib' 2>/dev/null || { log "FATAL: python3 is older than 3.11 (no tomllib); the verifier cannot run"; exit 2; }
[ -r "${VERIFIER}" ] || { log "FATAL: verifier ${VERIFIER} not readable (converge-warm-cache.sh ships it in the script ConfigMap)"; exit 2; }
[ -r "$(dirname "${VERIFIER}")/uv_cache_layout.py" ] || { log "FATAL: uv_cache_layout.py not beside ${VERIFIER} (the verifier imports it; converge-warm-cache.sh ships both)"; exit 2; }
[ -f "${REPOS_FILE}" ] || { log "FATAL: repos file ${REPOS_FILE} not found"; exit 2; }
[ -d "${WARM_ROOT}" ] || { log "FATAL: WARM_ROOT ${WARM_ROOT} is not a directory"; exit 2; }
for v in WARM_BUDGET_BYTES WARM_BUDGET_FILES WARM_FORCE_REBUILD_SECONDS KEEP_GENERATIONS; do
  [[ "${!v}" =~ ^[0-9]+$ ]] || { log "FATAL: ${v} must be a non-negative integer, got '${!v}' (the warm-cache-budget ConfigMap injects the budget)"; exit 2; }
done
[ "${WARM_BUDGET_BYTES}" -gt 0 ] && [ "${WARM_BUDGET_FILES}" -gt 0 ] || { log "FATAL: WARM_BUDGET_BYTES and WARM_BUDGET_FILES must be positive"; exit 2; }
if [ -n "${WARM_INJECT_TEST}" ] && { [ ! -f "${WARM_INJECT_TEST}/pyproject.toml" ] || [ ! -f "${WARM_INJECT_TEST}/uv.lock" ]; }; then
  log "FATAL: WARM_INJECT_TEST=${WARM_INJECT_TEST} is set but holds no pyproject.toml + uv.lock; a negative test that injects nothing would pass falsely"
  exit 2
fi
proxy_unavailable=0
if curl --silent --fail --max-time 5 "${PYPI_FILES_PROXY}/health" >/dev/null 2>&1; then
  log "pypi files proxy ${PYPI_FILES_PROXY} healthy; locks will be rewritten to fetch through it"
else
  proxy_unavailable=1
  log "WARN: pypi files proxy ${PYPI_FILES_PROXY} not answering /health; building DIRECT from files.pythonhosted.org (proxy_unavailable=1)"
fi

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

run_started="$(date +%s)"
generation="$(date -u +%Y%m%dT%H%M%SZ)"
new_gen="${GENERATIONS_DIR}/${generation}"
current_gen=""
if [ -L "${CURRENT_LINK}" ]; then
  current_gen="$(readlink -f "${CURRENT_LINK}" || true)"
  [ -d "${current_gen}" ] || current_gen=""
fi
current_manifest="${current_gen:+${current_gen}/.warm-manifest.json}"

# ---------------------------------------------------------------------------
# 1. CLONE / FETCH every routed repository and hash its uv.lock. The syncs
#    come later, only if a rebuild is due; the cargo work comes after that.
failed=()
fetched=()
uv_repos=()
declare -A lock_sha
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
  fetched+=("${name}")
  if [ -f "${src}/uv.lock" ]; then
    uv_repos+=("${name}")
    lock_sha["${name}"]="$(sha256sum "${src}/uv.lock" | cut -d' ' -f1)"
    log "   uv.lock sha256 ${lock_sha[${name}]:0:12}"
  else
    log "   no uv.lock; nothing to sync for uv"
  fi
done < "${REPOS_FILE}"

# ---------------------------------------------------------------------------
# 2. DECIDE: unchanged locks + a verifying, young published generation means
#    no rebuild. Every lock hash must match the published manifest's, and the
#    manifest must name every routed lock (a repository whose sync failed last
#    run is absent from it, which forces the rebuild that heals it).
rebuild_reason=""
if [ -n "${WARM_INJECT_TEST}" ]; then
  # A negative test that took the no-rebuild path would inject nothing and
  # "pass"; the hook always builds.
  rebuild_reason="WARM_INJECT_TEST is set (the negative test always rebuilds)"
elif [ -z "${current_gen}" ]; then
  rebuild_reason="no published generation"
elif [ ! -r "${current_manifest}" ]; then
  rebuild_reason="published generation $(basename "${current_gen}") has no manifest (built before livespec-41w4)"
else
  published_epoch="$(manifest_field "${current_manifest}" published_at_epoch || echo 0)"
  if [ $(( run_started - published_epoch )) -ge "${WARM_FORCE_REBUILD_SECONDS}" ]; then
    rebuild_reason="published generation is $(( run_started - published_epoch )) s old (forced rebuild past ${WARM_FORCE_REBUILD_SECONDS} s)"
  else
    lock_args=()
    for name in "${uv_repos[@]}"; do lock_args+=("${name}=${lock_sha[${name}]}"); done
    if ! changed="$(python3 - "${current_manifest}" "${lock_args[@]}" <<'PY'
import json, sys
published = json.load(open(sys.argv[1])).get("locks") or {}
current = dict(a.split("=", 1) for a in sys.argv[2:])
changed = sorted(n for n in set(published) | set(current) if published.get(n) != current.get(n))
print(" ".join(changed))
sys.exit(1 if changed else 0)
PY
)"; then
      rebuild_reason="lock changed: ${changed}"
    fi
  fi
fi

if [ -z "${rebuild_reason}" ]; then
  # Every lock unchanged: the published generation must still verify against
  # them (an operator may have touched it; a uv bump may have changed the
  # layout), else it is rebuilt now rather than served broken for a day.
  lock_files=()
  for name in "${uv_repos[@]}"; do lock_files+=("${SRC_DIR}/${name}/uv.lock"); done
  if python3 "${VERIFIER}" --cache "${current_gen}" "${lock_files[@]}" > "${SCRATCH}/verify-current.txt" 2>&1; then
    log "every routed uv.lock unchanged and generation $(basename "${current_gen}") verifies; no rebuild (rebuilt=0)"
  else
    rebuild_reason="published generation $(basename "${current_gen}") no longer verifies against the current locks"
    log "WARN: ${rebuild_reason}:"
    sed 's/^/   /' "${SCRATCH}/verify-current.txt"
  fi
fi

# ---------------------------------------------------------------------------
# 3. BUILD (or keep). Everything the sweep emits comes from these variables.
rebuilt=0; refused=0; verified=1; uv_exit=0
synced=0
published_gen="${current_gen}"
prev_bytes=""; prev_files=""
new_bytes=""; new_files=""
trimmed_bytes=0; trimmed_files=0
proxy_before=""; proxy_after=""; proxied_downloads=0; proxy_hit_ratio="null"
unreferenced=0; unknown=0
if [ -z "${rebuild_reason}" ]; then
  new_bytes="$(manifest_field "${current_manifest}" generation_bytes || gen_bytes "${current_gen}")"
  new_files="$(manifest_field "${current_manifest}" generation_files || gen_files "${current_gen}")"
  prev_bytes="${new_bytes}"; prev_files="${new_files}"
  # "Last verified current" for ci-cache-gauges.sh's generation_age_s (the
  # header explains); the contents are untouched.
  touch "${current_gen}" || true
else
  rebuilt=1
  log "REBUILD: ${rebuild_reason}"
  if [ -n "${current_gen}" ]; then
    prev_bytes="$(manifest_field "${current_manifest}" generation_bytes || gen_bytes "${current_gen}")"
    prev_files="$(manifest_field "${current_manifest}" generation_files || gen_files "${current_gen}")"
    log "previous generation $(basename "${current_gen}"): ${prev_bytes} bytes, ${prev_files} files"
  fi
  proxy_before="$(proxy_store_objects || true)"
  log "starting generation ${generation} EMPTY"
  rm -rf "${new_gen}"
  mkdir -p "${new_gen}"
  synced_names=(); synced_shas=()
  for name in "${uv_repos[@]}"; do
    src="${SRC_DIR}/${name}"
    log "-- ${name}: uv sync --frozen into ${generation}"
    if [ "${proxy_unavailable}" = 0 ]; then
      # The prefix swap of the header: this clone's lock only; git resets it
      # on the next fetch. Hashed BEFORE the rewrite (step 1).
      sed -i "s#${PYPI_FILES_PREFIX}#${PYPI_FILES_PROXY}/packages/#g" "${src}/uv.lock"
    fi
    venv="${SCRATCH}/venv-${name}"
    rm -rf "${venv}"
    if UV_CACHE_DIR="${new_gen}" UV_PROJECT_ENVIRONMENT="${venv}" \
       uv sync --frozen --all-groups --no-install-project --no-install-workspace \
         --project "${src}" --quiet; then
      synced=$((synced + 1))
      synced_names+=("${name}"); synced_shas+=("${lock_sha[${name}]}")
      log "   uv: synced"
    else
      log "   uv sync failed; skipping (its lock stays out of the manifest, so the next run rebuilds)"
      failed+=("${name}")
    fi
    rm -rf "${venv}"
    git -C "${src}" checkout --quiet -- uv.lock 2>/dev/null || true
  done
  if [ -n "${WARM_INJECT_TEST}" ]; then
    log "NEGATIVE TEST: WARM_INJECT_TEST=${WARM_INJECT_TEST} — syncing an UNROUTED project into ${generation}; the verifier MUST reject this generation"
    venv="${SCRATCH}/venv-inject"
    UV_CACHE_DIR="${new_gen}" UV_PROJECT_ENVIRONMENT="${venv}" \
      uv sync --frozen --no-install-project --no-install-workspace --project "${WARM_INJECT_TEST}" --quiet \
      || log "   inject sync failed (the test may not be exercising the verifier)"
    rm -rf "${venv}"
  fi
  # Proxy hit ratio: new objects in the store against the distributions
  # this build fetched THROUGH the proxy (uv's .http pointers name the URL).
  proxy_after="$(proxy_store_objects || true)"
  proxied_downloads="$(find "${new_gen}" -name '*.http' -type f -exec grep -l -a -F "${PYPI_FILES_PROXY}/packages/" {} + 2>/dev/null | wc -l)"
  if [ -n "${proxy_before}" ] && [ -n "${proxy_after}" ] && [ "${proxied_downloads}" -gt 0 ]; then
    proxy_hit_ratio="$(python3 -c 'import sys; b,a,d=map(int,sys.argv[1:]); print(round(max(0.0, 1 - (a-b)/d), 4))' "${proxy_before}" "${proxy_after}" "${proxied_downloads}")"
    log "proxy: ${proxied_downloads} distributions fetched through it, store ${proxy_before} -> ${proxy_after} objects, hit_ratio=${proxy_hit_ratio}"
  else
    log "proxy: hit ratio unavailable (store readable: $([ -n "${proxy_before}" ] && echo yes || echo no); proxied downloads: ${proxied_downloads})"
  fi

  # VERIFY against EVERY current lock (a failed repository's partial fetches
  # are still referenced by ITS lock; the manifest, not the verifier, records
  # which locks are actually warm).
  lock_files=()
  for name in "${uv_repos[@]}"; do lock_files+=("${SRC_DIR}/${name}/uv.lock"); done
  log "verifying ${generation} against ${#lock_files[@]} lock(s)"
  python3 "${VERIFIER}" --cache "${new_gen}" --json "${lock_files[@]}" > "${SCRATCH}/verify.json" 2> "${SCRATCH}/verify.err"
  verify_exit=$?
  if [ "${verify_exit}" -eq 0 ] || [ "${verify_exit}" -eq 1 ]; then
    python3 - "${SCRATCH}/verify.json" <<'PY' | sed 's/^/   /'
import json, sys
s = json.load(open(sys.argv[1]))
r, b = s["referenced"], s["build_deps"]
print(f"generation: {s['generation_bytes']} bytes, {s['generation_files']} files; lock union: {s['lock_pairs']} (name,version) pairs")
print(f"referenced: {r['entries']} entries, {r['bytes']} bytes, {r['files']} files")
print(f"build-deps: {b['entries']} entries, {b['bytes']} bytes, {b['files']} files: {' '.join(b['names'])}")
for e in s["unreferenced"]:
    print(f"UNREFERENCED {e['bucket']}/{e['entry']} -> ({e['name']}, {e['version']}) {e['bytes']} bytes {e['files']} files")
for e in s["unknown"]:
    print(f"UNKNOWN {e['bucket']}/{e['entry']} {e['bytes']} bytes {e['files']} files")
PY
    unreferenced="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["unreferenced"]))' "${SCRATCH}/verify.json" 2>/dev/null || echo 0)"
    unknown="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["unknown"]))' "${SCRATCH}/verify.json" 2>/dev/null || echo 0)"
  else
    log "verifier did not run to a verdict (exit ${verify_exit}): $(head -3 "${SCRATCH}/verify.err" | tr '\n' ' ')"
  fi
  new_bytes="$(gen_bytes "${new_gen}")"
  new_files="$(gen_files "${new_gen}")"
  log "generation ${generation}: ${new_bytes} bytes, ${new_files} files (budget ${WARM_BUDGET_BYTES} bytes, ${WARM_BUDGET_FILES} files)"

  # The manifest lives INSIDE the generation so it is kept, renamed and
  # pruned with it; the verifier knows the file name.
  python3 - "${new_gen}/.warm-manifest.json" "${generation}" "${run_started}" "${new_bytes}" "${new_files}" \
      "${WARM_BUDGET_BYTES}" "${WARM_BUDGET_FILES}" "${SCRATCH}/verify.json" "${verify_exit}" "${proxy_unavailable}" \
      "${proxy_before}" "${proxy_after}" "${proxied_downloads}" "${proxy_hit_ratio}" \
      "${synced_names[@]}" -- "${synced_shas[@]}" <<'PY' || log "WARN: generation manifest not written"
import json, os, sys, time
(path, gen, started, nbytes, nfiles, bb, bf, vjson, vexit, proxy_unavail,
 pbefore, pafter, pdl, hit) = sys.argv[1:15]
rest = sys.argv[15:]
sep = rest.index("--"); names, shas = rest[:sep], rest[sep + 1:]
now = int(time.time())
try:
    verify = json.load(open(vjson))
    verify_summary = {k: verify[k] for k in ("lock_pairs", "referenced", "build_deps", "unreferenced", "unknown")}
except (OSError, ValueError, KeyError):
    verify_summary = None
doc = {"generation": gen, "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
       "published_at_epoch": now, "populate_seconds": now - int(started),
       "generation_bytes": int(nbytes), "generation_files": int(nfiles),
       "budget_bytes": int(bb), "budget_files": int(bf),
       "locks": dict(zip(names, shas)),
       "verify_exit": int(vexit), "verify": verify_summary,
       "proxy_unavailable": int(proxy_unavail),
       "proxy_store_objects_before": int(pbefore) if pbefore else None,
       "proxy_store_objects_after": int(pafter) if pafter else None,
       "proxied_downloads": int(pdl), "proxy_hit_ratio": None if hit == "null" else float(hit)}
tmp = path + ".tmp"
with open(tmp, "w") as f: json.dump(doc, f, indent=1)
os.replace(tmp, path)
PY

  if [ "${synced}" -eq 0 ] && [ "${#failed[@]}" -gt 0 ]; then
    # Nothing synced and something failed (a forge or PyPI outage): an empty
    # generation would replace a good one and make every job cold. Keep the
    # published generation; the next tick retries. (Zero locks with zero
    # failures is a legitimately empty union and publishes.)
    uv_exit=1
    rm -rf "${new_gen}"
    log "DISCARDED: no routed repository synced into ${generation}; the symlink is UNCHANGED"
  elif [ "${verify_exit}" -ne 0 ]; then
    verified=0; uv_exit=1
    mv -T "${new_gen}" "${new_gen}.unverified"
    log "REJECTED: generation ${generation} did not verify (${unreferenced} unreferenced, ${unknown} unknown entries; verifier exit ${verify_exit}); kept as ${generation}.unverified for one cycle; the symlink is UNCHANGED"
  elif [ "${new_bytes}" -gt "${WARM_BUDGET_BYTES}" ] || [ "${new_files}" -gt "${WARM_BUDGET_FILES}" ]; then
    refused=1; uv_exit=3
    mv -T "${new_gen}" "${new_gen}.refused"
    log "REFUSED: generation ${generation} is OVER BUDGET (${new_bytes} bytes vs ${WARM_BUDGET_BYTES}; ${new_files} files vs ${WARM_BUDGET_FILES}); kept as ${generation}.refused for one cycle; the symlink is UNCHANGED"
  else
    # Publish: one atomic rename of a relative symlink, so the link stays
    # valid wherever the warm root is mounted (the provisioner's helper pod
    # sees it at its node path, not at this container's /warm).
    ln -sfn "uv-generations/${generation}" "${CURRENT_LINK}.tmp"
    mv -T "${CURRENT_LINK}.tmp" "${CURRENT_LINK}"
    published_gen="${new_gen}"
    if [ -n "${prev_bytes}" ]; then
      trimmed_bytes=$(( prev_bytes - new_bytes ))
      trimmed_files=$(( prev_files - new_files ))
    fi
    log "published generation ${generation} (${synced}/${#uv_repos[@]} repositories synced; ${new_bytes} bytes, ${new_files} files; trimmed ${trimmed_bytes} bytes, ${trimmed_files} files against the previous generation)"
  fi
fi
populate_seconds=$(( $(date +%s) - run_started ))

# ---------------------------------------------------------------------------
# 4. PRUNE: keep the newest KEEP_GENERATIONS published generations (the one
#    just published is always among them); drop every refused / unverified
#    directory from an EARLIER run (this run's stays one cycle to be
#    inspected).
mapfile -t gens < <(find "${GENERATIONS_DIR}" -mindepth 1 -maxdepth 1 -type d -name '[0-9]*Z' -printf '%f\n' | sort)
if [ "${#gens[@]}" -gt "${KEEP_GENERATIONS}" ]; then
  for old in "${gens[@]:0:$(( ${#gens[@]} - KEEP_GENERATIONS ))}"; do
    [ "${GENERATIONS_DIR}/${old}" = "${published_gen}" ] && continue
    log "pruning generation ${old}"
    rm -rf "${GENERATIONS_DIR:?}/${old}"
  done
fi
while IFS= read -r rejected; do
  [ -n "${rejected}" ] || continue
  case "${rejected}" in "${generation}".*) continue ;; esac
  log "pruning rejected generation ${rejected}"
  rm -rf "${GENERATIONS_DIR:?}/${rejected}"
done < <(find "${GENERATIONS_DIR}" -mindepth 1 -maxdepth 1 -type d \( -name '*.refused' -o -name '*.unverified' \) -printf '%f\n' | sort)

# ---------------------------------------------------------------------------
# 5. last-run.json — the sweep's input (header "METRICS"). Written NOW, before
#    the cargo work and before any non-zero exit, so a refused or rejected run
#    is emitted too. Atomic rename; the sweep may read while the next run
#    writes.
python3 - "${LAST_RUN}" "${generation}" "${run_started}" "${rebuilt}" "${refused}" "${verified}" \
    "$(basename "${published_gen:-}")" "${new_bytes:-0}" "${new_files:-0}" "${prev_bytes}" "${prev_files}" \
    "${trimmed_bytes}" "${trimmed_files}" "${populate_seconds}" "${synced}" "${#failed[@]}" \
    "${WARM_BUDGET_BYTES}" "${WARM_BUDGET_FILES}" "${proxy_unavailable}" "${proxy_hit_ratio}" "${proxied_downloads}" \
    "${unreferenced}" "${unknown}" "${uv_exit}" "${rebuild_reason}" "${failed[@]:-}" <<'PY' || log "WARN: last-run.json not written"
import json, os, sys, time
(path, run_id, started, rebuilt, refused, verified, published, nbytes, nfiles, pbytes, pfiles,
 tbytes, tfiles, secs, synced, nfailed, bb, bf, proxy_unavail, hit, pdl, unref, unk, uv_exit, reason) = sys.argv[1:26]
failed = [f for f in sys.argv[26:] if f]
now = int(time.time())
doc = {"run_id": run_id, "started_at_epoch": int(started), "finished_uv_at_epoch": now,
       "finished_uv_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
       "rebuilt": int(rebuilt), "refused": int(refused), "verified": int(verified), "uv_exit": int(uv_exit),
       "rebuild_reason": reason or None, "published_generation": published or None,
       "generation_bytes": int(nbytes), "generation_files": int(nfiles),
       "previous_generation_bytes": int(pbytes) if pbytes else None,
       "previous_generation_files": int(pfiles) if pfiles else None,
       "trimmed_bytes": int(tbytes), "trimmed_files": int(tfiles),
       "populate_seconds": int(secs), "repos_synced": int(synced), "repos_failed": int(nfailed), "failed": failed,
       "budget_bytes": int(bb), "budget_files": int(bf),
       "proxy_unavailable": int(proxy_unavail), "proxied_downloads": int(pdl),
       "proxy_hit_ratio": None if hit == "null" else float(hit),
       "unreferenced_entries": int(unref), "unknown_entries": int(unk)}
tmp = path + ".tmp"
with open(tmp, "w") as f: json.dump(doc, f, indent=1)
os.replace(tmp, path)
PY

# ---------------------------------------------------------------------------
# 6. THE CARGO HALF and the compilation cache's writer build, per fetched
#    repository (the header's "THE CARGO HALF" / "THE COMPILATION CACHE'S ONE
#    WRITER" / "GUARDRAILS"). Independent of the uv generation above.
cargo_warmed=0
sccache_built=0
sccache_skipped=0
sccache_skipped_busy=0
admitted_last=""
for name in "${fetched[@]}"; do
  src="${SRC_DIR}/${name}"
  if [ -f "${src}/Cargo.lock" ]; then
    log "-- ${name}: cargo"
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
        elif ! admitted_last="$(admitted_jobs)"; then
          log "   sccache: cannot read the pool's admitted-job count (Kueue API); treating the pool as busy — no build"
          admitted_last=""
          failed+=("${name}:sccache-admitted-unreadable")
        elif [ "${admitted_last}" -gt "${POPULATE_ADMITTED_JOB_THRESHOLD}" ]; then
          log "   sccache: pool busy (${admitted_last} admitted jobs > threshold ${POPULATE_ADMITTED_JOB_THRESHOLD}); skipping the build this tick (guardrail)"
          sccache_skipped_busy=$((sccache_skipped_busy + 1))
        else
          log "   sccache: pool has ${admitted_last} admitted jobs (threshold ${POPULATE_ADMITTED_JOB_THRESHOLD}); building"
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
done

# ---------------------------------------------------------------------------
# 4. TARGET GENERATIONS — a warmed `target/` tree per (repository, key), for
#    the compile shapes sccache reaches least. First and so far only key:
#    `asan-fuzz`, the console's `cargo +nightly fuzz build` tree (console plan
#    optimize-console-builds, `livespec-console-beads-fabro-ydlant`; the spike
#    that sized it is that plan's research/010). Measured 2026-09-06 on this
#    node: the tree is 253 MB and builds cold in 33-41 s at 12 jobs with
#    0 % sccache hits (nothing else compiles with -Zsanitizer=address); a job
#    that receives it Fresh and restores source mtimes compiles in ~0.1 s,
#    and a PR that edits a domain crate still saves the ~12 s of sanitized
#    dependencies. The job's 79 s P50 compile phase is the target.
#
#    Layout mirrors the uv tier so the same provisioner seed applies:
#      ${WARM_ROOT}/target-generations/<repo>/<key>/<stamp>/tree   the tree
#      ${WARM_ROOT}/target-generations/<repo>/<key>/<stamp>/.target-manifest.json
#      ${WARM_ROOT}/target/<repo>/<key> -> ../../target-generations/<repo>/<key>/<stamp>
#    Published by one atomic symlink rename, pruned to KEEP_GENERATIONS (the
#    live one is never pruned). The provisioner reflink-copies every published
#    link under <volume>/_warm/target/<repo>/<key> (a copy-on-write copy the
#    job owns; no inode is shared), and the consuming job moves the tree into
#    place and restores mtimes for sources unchanged vs `source_sha`.
#
#    Path identity: the tree is built at the job's own checkout path
#    (${JOB_WORK_ROOT}/<repo>/<repo>) — cargo fingerprints embed the SOURCE
#    path — and with the job's own wrapper (sccache, as the writer here, so
#    the sanitized objects also land in the compilation cache). Rebuilt only
#    when the default-branch commit or the fuzz toolchain (nightly rustc +
#    cargo-fuzz) changed, under the same admitted-job gate and nice/ionice as
#    the sccache writer build. Needs the python-rust-fuzz image (nightly,
#    cargo-fuzz, c++); on any other image every repository is skipped, loudly.
TARGET_GEN_ROOT="${WARM_ROOT}/target-generations"
TARGET_LINK_ROOT="${WARM_ROOT}/target"
target_built=0; target_skipped=0; target_skipped_busy=0
fuzz_toolchain=""
if command -v cargo >/dev/null && command -v c++ >/dev/null \
   && rustc +nightly --version >/dev/null 2>&1 && cargo +nightly fuzz --version >/dev/null 2>&1; then
  fuzz_toolchain="nightly-$(rustc +nightly --version 2>/dev/null | awk '{print $2}')@cargo-fuzz-$(cargo +nightly fuzz --version 2>/dev/null | awk '{print $2}')"
fi
for name in "${fetched[@]}"; do
  src="${SRC_DIR}/${name}"
  [ -f "${src}/fuzz/Cargo.toml" ] || continue
  key="asan-fuzz"
  log "-- ${name}: target generation ${key}"
  if [ -z "${fuzz_toolchain}" ]; then
    log "   fuzz toolchain absent in this image (needs python-rust-fuzz: nightly + cargo-fuzz + c++); skipping"
    target_skipped=$((target_skipped + 1)); continue
  fi
  sha="$(git -C "${src}" rev-parse HEAD)"
  gen_dir="${TARGET_GEN_ROOT}/${name}/${key}"; link="${TARGET_LINK_ROOT}/${name}/${key}"
  mkdir -p "${gen_dir}" "${TARGET_LINK_ROOT}/${name}"
  cur=""
  if [ -L "${link}" ]; then cur="$(readlink -f "${link}" || true)"; [ -d "${cur}" ] || cur=""; fi
  have_sha=""; have_tc=""
  if [ -n "${cur}" ] && [ -r "${cur}/.target-manifest.json" ]; then
    have_sha="$(manifest_field "${cur}/.target-manifest.json" source_sha || true)"
    have_tc="$(manifest_field "${cur}/.target-manifest.json" toolchain || true)"
  fi
  if [ "${have_sha}" = "${sha}" ] && [ "${have_tc}" = "${fuzz_toolchain}" ]; then
    log "   generation $(basename "${cur}") already holds ${sha:0:8} @ ${fuzz_toolchain}; no build"
    target_skipped=$((target_skipped + 1)); continue
  fi
  if [ -z "${admitted_last}" ] && ! admitted_last="$(admitted_jobs)"; then
    log "   cannot read the pool's admitted-job count (Kueue API); treating the pool as busy — no build"
    admitted_last=""; failed+=("${name}:target-admitted-unreadable"); continue
  fi
  if [ "${admitted_last}" -gt "${POPULATE_ADMITTED_JOB_THRESHOLD}" ]; then
    log "   pool busy (${admitted_last} admitted jobs > threshold ${POPULATE_ADMITTED_JOB_THRESHOLD}); skipping the build this tick (guardrail)"
    target_skipped_busy=$((target_skipped_busy + 1)); continue
  fi
  build_dir="${JOB_WORK_ROOT}/${name}/${name}"
  rm -rf "${JOB_WORK_ROOT:?}/${name}"; mkdir -p "${JOB_WORK_ROOT}/${name}"; cp -a "${src}" "${build_dir}"
  wrapper_env=()
  if [ -x "${SCCACHE_BIN}" ] && [ -n "${SCCACHE_REDIS_WRITER_PASSWORD}" ] && [ -n "${SCCACHE_REDIS_WRITER_USERNAME}" ]; then
    wrapper_env=(RUSTC_WRAPPER="${SCCACHE_BIN}" SCCACHE_REDIS_ENDPOINT="${SCCACHE_REDIS_ENDPOINT}"
                 SCCACHE_REDIS_USERNAME="${SCCACHE_REDIS_WRITER_USERNAME}" SCCACHE_REDIS_PASSWORD="${SCCACHE_REDIS_WRITER_PASSWORD}"
                 SCCACHE_REDIS_RW_MODE=READ_WRITE)
  else
    log "   sccache writer not available here; building without the wrapper (the tree is still valid for jobs)"
  fi
  log "   building ${sha:0:8} @ ${fuzz_toolchain} (had: ${have_sha:0:8}${have_sha:+ @ }${have_tc})"
  t0=$(date +%s)
  if (cd "${build_dir}" && env "${wrapper_env[@]}" nice -n 19 ionice -c 3 cargo +nightly fuzz build > "${SCRATCH}/fuzz-build-${name}.log" 2>&1); then
    secs=$(( $(date +%s) - t0 ))
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"; new="${gen_dir}/${stamp}"
    rm -rf "${new}"; mkdir -p "${new}"
    if cp -a --reflink=auto "${build_dir}/fuzz/target" "${new}/tree" && find "${new}/tree" -type d -exec chmod 0777 {} +; then
      tb="$(gen_bytes "${new}/tree")"; tf="$(gen_files "${new}/tree")"
      python3 - "${new}/.target-manifest.json" "${stamp}" "${name}" "${key}" "${sha}" "${fuzz_toolchain}" "${tb}" "${tf}" "${secs}" <<'PY' || log "WARN: target manifest not written"
import json, os, sys, time
path, gen, repo, key, sha, tc, nbytes, nfiles, secs = sys.argv[1:10]
now = int(time.time())
doc = {"generation": gen, "repo": repo, "key": key, "source_sha": sha, "toolchain": tc,
       "build_command": "cargo +nightly fuzz build", "tree": "tree",
       "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "built_at_epoch": now,
       "build_seconds": int(secs), "generation_bytes": int(nbytes), "generation_files": int(nfiles)}
tmp = path + ".tmp"
with open(tmp, "w") as f: json.dump(doc, f, indent=1)
os.replace(tmp, path)
PY
      ln -sfn "../../target-generations/${name}/${key}/${stamp}" "${link}.tmp"
      mv -T "${link}.tmp" "${link}"
      target_built=$((target_built + 1))
      log "   built in ${secs} s; published ${stamp} (${tb} bytes, ${tf} files)"
    else
      log "   copying fuzz/target into the generation failed; discarded"
      rm -rf "${new}"; failed+=("${name}:target-copy")
    fi
  else
    log "   cargo +nightly fuzz build FAILED after $(( $(date +%s) - t0 )) s: $(tail -3 "${SCRATCH}/fuzz-build-${name}.log" | tr '\n' ' ')"
    failed+=("${name}:target-build")
  fi
  [ -x "${SCCACHE_BIN}" ] && "${SCCACHE_BIN}" --stop-server >/dev/null 2>&1 || true
  rm -rf "${JOB_WORK_ROOT:?}/${name}"
  live="$(readlink -f "${link}" 2>/dev/null || true)"
  mapfile -t tgens < <(find "${gen_dir}" -mindepth 1 -maxdepth 1 -type d -name '[0-9]*Z' -printf '%f\n' | sort)
  if [ "${#tgens[@]}" -gt "${KEEP_GENERATIONS}" ]; then
    for old in "${tgens[@]:0:$(( ${#tgens[@]} - KEEP_GENERATIONS ))}"; do
      [ "${gen_dir}/${old}" = "${live}" ] && continue
      log "   pruning target generation ${old}"
      rm -rf "${gen_dir:?}/${old}"
    done
  fi
done

log "run summary: uv generation $(basename "${published_gen:-none}") (rebuilt=${rebuilt} refused=${refused} verified=${verified}, ${synced} repositories synced), ${cargo_warmed} pre-warmed for cargo, sccache builds: ${sccache_built} built / ${sccache_skipped} skipped / ${sccache_skipped_busy} skipped-busy, target generations: ${target_built} built / ${target_skipped} skipped / ${target_skipped_busy} skipped-busy"

# MANIFEST: what this run did, for the host gauges (ci-runner/observability/
# ci-cache-gauges.sh reads it every 5 min into livespec.ci_cache.populate.*
# — duration, counts, toolchain — the "per-generation manifest" of the v054
# populator-guardrails clause). Atomic rename beside the generations; the
# reader may open it while the next run writes. `generation` names the LIVE
# generation (unchanged on a rebuilt=0, refused or rejected run).
toolchain_version="$(command -v rustc >/dev/null && rustc --version 2>/dev/null | awk '{print $2}' || echo "")"
python3 - "${WARM_ROOT}/populate-manifest.json" "$(basename "${published_gen:-}")" "${run_started}" "${synced}" "${#failed[@]}" "${cargo_warmed}" "${sccache_built}" "${sccache_skipped}" "${toolchain_version}" "${sccache_skipped_busy}" "${admitted_last}" "${POPULATE_ADMITTED_JOB_THRESHOLD}" "${generation}" "${rebuilt}" "${refused}" "${verified}" "${target_built}" "${target_skipped}" "${target_skipped_busy}" "${fuzz_toolchain}" "${failed[@]:-}" <<'PY' || log "WARN: manifest not written"
import json, sys, time, os
(path, gen, started, synced, nfailed, warmed, built, skipped, toolchain, skipped_busy, admitted, threshold, run_id,
 rebuilt, refused, verified, tbuilt, tskipped, tskipped_busy, fuzz_toolchain) = sys.argv[1:21]
failed = [f for f in sys.argv[21:] if f]
now = int(time.time())
doc = {"generation": gen, "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "published_at_epoch": now,
       "duration_s": now - int(started), "repos_synced": int(synced), "repos_failed": int(nfailed), "failed": failed,
       "cargo_warmed": int(warmed), "sccache_built": int(built), "sccache_skipped": int(skipped), "sccache_skipped_busy": int(skipped_busy),
       "admitted_jobs": int(admitted) if admitted else None, "admitted_job_threshold": int(threshold), "toolchain_version": toolchain,
       "run_id": run_id, "rebuilt": int(rebuilt), "refused": int(refused), "verified": int(verified),
       "target_built": int(tbuilt), "target_skipped": int(tskipped), "target_skipped_busy": int(tskipped_busy),
       "fuzz_toolchain": fuzz_toolchain or None}
tmp = path + ".tmp"
with open(tmp, "w") as f: json.dump(doc, f, indent=1)
os.replace(tmp, path)
PY

rm -rf "${SCRATCH}"
if [ "${uv_exit}" -eq 3 ]; then
  log "REFUSED (over budget); exit 3"
  exit 3
fi
if [ "${#failed[@]}" -gt 0 ]; then
  log "FAILED repositories: ${failed[*]}"
  exit 1
fi
if [ "${uv_exit}" -ne 0 ]; then
  log "generation rejected by the verifier; exit ${uv_exit}"
  exit "${uv_exit}"
fi
log "ok"
