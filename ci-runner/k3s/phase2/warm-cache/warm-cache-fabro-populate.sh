#!/usr/bin/env bash
# warm-cache-fabro-populate.sh — the separately-budgeted writer pass for the
# thewoolleyman/fabro ARC fork.  Fabro remains absent from the regular
# warm-cache repository list: its roughly 98 GiB workspace cannot run ahead of
# the console inside that pass's 3600-second deadline.  This script is mounted
# only by warm-cache-populate-fabro, whose longer deadline and hourly schedule
# isolate that cost while retaining the compilation cache's populator-only
# writer boundary.
#
# The three arrays below deliberately reproduce the fork jobs' command, branch,
# toolchain and profile shapes.  sccache keys its entries on all of those inputs,
# including the /__w/fabro/fabro checkout path, so a generic cargo build at a
# different path is not a useful warmup.  The release profile alone carries
# NODE_ENV=production, exactly as carrier-build does.
set -euo pipefail

FABRO_URL="${FABRO_URL:-https://github.com/thewoolleyman/fabro.git}"
JOB_WORK_ROOT="${JOB_WORK_ROOT:-/__w}"
SCCACHE_BIN="${SCCACHE_BIN:-/opt/ci-runner/bin/sccache}"
SCCACHE_REDIS_ENDPOINT="${SCCACHE_REDIS_ENDPOINT:-redis://sccache-redis.ci-sccache.svc.cluster.local:6379}"
SCCACHE_REDIS_WRITER_USERNAME="${SCCACHE_REDIS_WRITER_USERNAME:-}"
SCCACHE_REDIS_WRITER_PASSWORD="${SCCACHE_REDIS_WRITER_PASSWORD:-}"
SCCACHE_WRITER_PORT="${SCCACHE_WRITER_PORT:-4228}"
SCCACHE_FABRO_MIN_FREE_BYTES="${SCCACHE_FABRO_MIN_FREE_BYTES:-}"
CRATES_PROXY_URL="${CRATES_PROXY_URL:-http://crates-proxy.ci-crates-proxy.svc.cluster.local:3080}"
POPULATE_ADMITTED_JOB_THRESHOLD="${POPULATE_ADMITTED_JOB_THRESHOLD:-16}"
K8S_SA_DIR="${K8S_SA_DIR:-/var/run/secrets/kubernetes.io/serviceaccount}"
SCRATCH="${SCRATCH:-$(mktemp -d)}"

log() { printf '[warm-cache-fabro %s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "FATAL: $*"; exit 2; }

# redis_raw COMMAND [ARG...] — one authenticated RESP exchange.  It prints a
# simple or bulk reply and fails closed on a Redis error: a missing memory read
# must not become permission to fill the cache.
redis_raw() {
  REDIS_USER="${SCCACHE_REDIS_WRITER_USERNAME}" REDIS_PASS="${SCCACHE_REDIS_WRITER_PASSWORD}" \
    python3 - "${SCCACHE_REDIS_ENDPOINT}" "$@" <<'PY'
import os
import socket
import sys
from urllib.parse import urlparse

endpoint = urlparse(sys.argv[1])
parts = sys.argv[2:]

def encode(*values: str) -> bytes:
    encoded = b"*%d\r\n" % len(values)
    for value in values:
        raw = value.encode()
        encoded += b"$%d\r\n%s\r\n" % (len(raw), raw)
    return encoded

def reply(reader) -> str:
    line = reader.readline()
    if not line:
        raise SystemExit("redis EOF")
    kind, body = chr(line[0]), line[1:-2].decode()
    if kind == "+":
        return body
    if kind == "-":
        raise SystemExit("redis error: " + body)
    if kind == ":":
        return body
    if kind == "$":
        length = int(body)
        if length < 0:
            return "(nil)"
        return reader.read(length + 2)[:-2].decode()
    raise SystemExit("unsupported redis reply: " + kind)

with socket.create_connection((endpoint.hostname, endpoint.port or 6379), timeout=10) as client:
    reader = client.makefile("rb")
    if not os.environ["REDIS_USER"] or not os.environ["REDIS_PASS"]:
        raise SystemExit("missing writer credential")
    client.sendall(encode("AUTH", os.environ["REDIS_USER"], os.environ["REDIS_PASS"]))
    reply(reader)
    client.sendall(encode(*parts))
    print(reply(reader))
PY
}

admitted_jobs() {
  local token
  [ -r "${K8S_SA_DIR}/token" ] || return 1
  token="$(cat "${K8S_SA_DIR}/token")"
  curl --silent --fail --max-time 10 \
    --cacert "${K8S_SA_DIR}/ca.crt" -H "Authorization: Bearer ${token}" \
    "https://kubernetes.default.svc/apis/kueue.x-k8s.io/v1beta2/clusterqueues" \
    | python3 -c 'import json,sys; print(sum(int((item.get("status") or {}).get("admittedWorkloads") or 0) for item in json.load(sys.stdin)["items"]))'
}

sccache_env=(
  "RUSTC_WRAPPER=${SCCACHE_BIN}"
  "SCCACHE_SERVER_PORT=${SCCACHE_WRITER_PORT}"
  "SCCACHE_REDIS_ENDPOINT=${SCCACHE_REDIS_ENDPOINT}"
  "SCCACHE_REDIS_USERNAME=${SCCACHE_REDIS_WRITER_USERNAME}"
  "SCCACHE_REDIS_PASSWORD=${SCCACHE_REDIS_WRITER_PASSWORD}"
  "SCCACHE_REDIS_RW_MODE=READ_WRITE"
)

sccache_writer_stop() {
  SCCACHE_SERVER_PORT="${SCCACHE_WRITER_PORT}" "${SCCACHE_BIN}" --stop-server >/dev/null 2>&1 || true
}

sccache_writer_start() {
  local log_file="${SCRATCH}/sccache-writer.log" attempt started=false
  sccache_writer_stop
  : > "${log_file}"
  for attempt in 1 2 3 4 5; do
    if env "${sccache_env[@]}" SCCACHE_LOG=info SCCACHE_ERROR_LOG="${log_file}" \
      "${SCCACHE_BIN}" --start-server >/dev/null 2>&1; then
      started=true
      break
    fi
    sleep "${attempt}"
  done
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    grep -q 'server has setup with' "${log_file}" 2>/dev/null && break
    sleep 1
  done
  if [ "${started}" = true ] && grep -q 'server has setup with ReadWrite' "${log_file}"; then
    log "sccache writer is ReadWrite on port ${SCCACHE_WRITER_PORT}"
    return 0
  fi
  log "sccache writer is not ReadWrite; refusing every fork build"
  return 1
}

check_redis_headroom() {
  local memory used max free
  memory="$(redis_raw INFO memory)" || return 1
  used="$(awk -F: '$1 == "used_memory" { print $2 }' <<<"${memory}" | tr -d '\r')"
  max="$(awk -F: '$1 == "maxmemory" { print $2 }' <<<"${memory}" | tr -d '\r')"
  [[ "${used}" =~ ^[0-9]+$ ]] && [[ "${max}" =~ ^[0-9]+$ ]] && [ "${max}" -gt 0 ] || return 1
  free=$((max - used))
  if [ "${free}" -lt "${SCCACHE_FABRO_MIN_FREE_BYTES}" ]; then
    log "Redis has ${free} bytes free, below the required ${SCCACHE_FABRO_MIN_FREE_BYTES}; refusing Fabro writes"
    return 1
  fi
  log "Redis has ${free} bytes free before the first Fabro write"
}

checkout_branch() {
  local branch="$1" repo="$2"
  git -C "${repo}" fetch --quiet --depth 1 origin "${branch}"
  git -C "${repo}" checkout --quiet --force FETCH_HEAD
  git -C "${repo}" clean -ffdx >/dev/null
}

warm_profile() {
  local branch="$1" profile="$2" toolchain="$3" node_env="$4"
  local sha marker want have started
  shift 4
  checkout_branch "${branch}" "${build_dir}"
  sha="$(git -C "${build_dir}" rev-parse HEAD)"
  marker="livespec:sccache:populated:fabro:${branch}:${profile}"
  want="${sha}@${toolchain}"
  have="$(redis_raw GET "${marker}" 2>/dev/null || printf '(unreachable)')"
  if [ "${have}" = "${want}" ]; then
    log "${branch}/${profile} already warmed at ${sha:0:8}@${toolchain}"
    return 0
  fi
  if [ "${have}" = '(unreachable)' ]; then
    log "Redis became unreachable before ${branch}/${profile}; no write"
    return 1
  fi
  if [ -n "${node_env}" ]; then
    if (cd "${build_dir}" && env "${sccache_env[@]}" "NODE_ENV=${node_env}" nice -n 19 ionice -c 3 "$@"); then
      started=true
    else
      started=false
    fi
  elif (cd "${build_dir}" && env "${sccache_env[@]}" nice -n 19 ionice -c 3 "$@"); then
    started=true
  else
    started=false
  fi
  if [ "${started}" = false ]; then
    log "${branch}/${profile} failed; marker remains absent for the next tick"
    return 1
  fi
  if ! redis_raw SET "${marker}" "${want}" >/dev/null; then
    log "${branch}/${profile} built but its marker was not recorded"
    return 1
  fi
  redis_raw BGSAVE >/dev/null 2>&1 || log "BGSAVE already running or refused; timed persistence remains enabled"
  log "${branch}/${profile} warmed at ${sha:0:8}@${toolchain}"
}

[ -x "${SCCACHE_BIN}" ] || die "${SCCACHE_BIN} is not mounted"
[ -n "${SCCACHE_REDIS_WRITER_USERNAME}" ] && [ -n "${SCCACHE_REDIS_WRITER_PASSWORD}" ] || die "writer credential is absent"
[[ "${SCCACHE_FABRO_MIN_FREE_BYTES}" =~ ^[0-9]+$ ]] && [ "${SCCACHE_FABRO_MIN_FREE_BYTES}" -gt 0 ] \
  || die "SCCACHE_FABRO_MIN_FREE_BYTES must be a positive integer"
command -v cargo >/dev/null || die "cargo is not on PATH"
command -v tini >/dev/null || die "tini is not on PATH"
command -v git >/dev/null || die "git is not on PATH"
command -v python3 >/dev/null || die "python3 is not on PATH"

admitted="$(admitted_jobs)" || die "cannot read Kueue admitted-job count"
[[ "${admitted}" =~ ^[0-9]+$ ]] || die "invalid Kueue admitted-job count: ${admitted}"
[ "${admitted}" -le "${POPULATE_ADMITTED_JOB_THRESHOLD}" ] \
  || { log "pool busy (${admitted} admitted jobs); skipping this tick"; exit 0; }
check_redis_headroom || die "Redis headroom is unavailable or insufficient"

mkdir -p /.cargo "${JOB_WORK_ROOT}/fabro"
printf '[source.crates-io]\nreplace-with = "ci-runner-pool"\n\n[source.ci-runner-pool]\nregistry = "sparse+%s/index/"\n\n[build]\nincremental = false\n' \
  "${CRATES_PROXY_URL}" > /.cargo/config.toml
build_dir="${JOB_WORK_ROOT}/fabro/fabro"
rm -rf "${JOB_WORK_ROOT:?}/fabro"
mkdir -p "${JOB_WORK_ROOT}/fabro"
git clone --quiet --no-checkout --depth 1 --branch factory-integration "${FABRO_URL}" "${build_dir}"
trap 'sccache_writer_stop; rm -rf "${JOB_WORK_ROOT:?}/fabro" "${SCRATCH}"' EXIT
sccache_writer_start || die "writer server did not prove ReadWrite"

clippy_command=(cargo +nightly-2026-04-14 clippy --workspace --all-targets)
test_command=(tini -s -- cargo +1.97.1 nextest run --locked --workspace --profile ci)
release_command=(cargo +1.97.1 dev build --release -p fabro-cli)

failed=0
warm_profile factory-integration clippy nightly-2026-04-14 "" "${clippy_command[@]}" || failed=1
warm_profile factory-integration test 1.97.1 "" "${test_command[@]}" || failed=1
warm_profile carrier-candidate-registered-20261023 carrier-release 1.97.1 production "${release_command[@]}" || failed=1
SCCACHE_SERVER_PORT="${SCCACHE_WRITER_PORT}" "${SCCACHE_BIN}" --show-stats 2>/dev/null \
  | grep -E 'Compile requests|Cache hits|Cache misses|Cache errors|Cache write|Non-cacheable' \
  | sed 's/^/sccache stats: /' || true

[ "${failed}" -eq 0 ] || exit 1
