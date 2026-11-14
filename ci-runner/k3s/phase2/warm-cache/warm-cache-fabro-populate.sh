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
FABRO_BUN_VERSION="${FABRO_BUN_VERSION:-1.3.14}"
FABRO_NEXTEST_VERSION="${FABRO_NEXTEST_VERSION:-0.9.150}"
FABRO_WAIT_FOR_REGULAR_SECONDS="${FABRO_WAIT_FOR_REGULAR_SECONDS:-3000}"
FABRO_REGULAR_POLL_SECONDS="${FABRO_REGULAR_POLL_SECONDS:-30}"
REGULAR_CRONJOB="${REGULAR_CRONJOB:-warm-cache-populate}"
CRATES_PROXY_URL="${CRATES_PROXY_URL:-http://crates-proxy.ci-crates-proxy.svc.cluster.local:3080}"
POPULATE_ADMITTED_JOB_THRESHOLD="${POPULATE_ADMITTED_JOB_THRESHOLD:-16}"
K8S_SA_DIR="${K8S_SA_DIR:-/var/run/secrets/kubernetes.io/serviceaccount}"
SCRATCH="${SCRATCH:-$(mktemp -d)}"

log() { printf '[warm-cache-fabro %s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "FATAL: $*"; exit 2; }

# redis_resp USER PASS COMMAND [ARG...] — one RESP exchange.  It prints a simple
# or bulk reply and fails closed on a Redis error: a missing memory read must not
# become permission to fill the cache.  An empty USER sends no AUTH, so the
# exchange runs as the ACL's unauthenticated default user.
redis_resp() {
  local user="$1" pass="$2"
  shift 2
  REDIS_USER="${user}" REDIS_PASS="${pass}" \
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
    if os.environ["REDIS_USER"]:
        client.sendall(encode("AUTH", os.environ["REDIS_USER"], os.environ["REDIS_PASS"]))
        reply(reader)
    client.sendall(encode(*parts))
    print(reply(reader))
PY
}

# redis_raw COMMAND [ARG...] — as the sccache-writer, for the marker GET/SET and
# BGSAVE the writer ACL grants.
redis_raw() { redis_resp "${SCCACHE_REDIS_WRITER_USERNAME}" "${SCCACHE_REDIS_WRITER_PASSWORD}" "$@"; }

# redis_default_raw COMMAND [ARG...] — as the unauthenticated default user.  The
# sccache ACL grants +info to that user alone; the writer has no +info, so the
# headroom read must not authenticate as the writer.
redis_default_raw() { redis_resp "" "" "$@"; }

admitted_jobs() {
  local token
  [ -r "${K8S_SA_DIR}/token" ] || return 1
  token="$(cat "${K8S_SA_DIR}/token")"
  curl --silent --fail --max-time 10 \
    --cacert "${K8S_SA_DIR}/ca.crt" -H "Authorization: Bearer ${token}" \
    "https://kubernetes.default.svc/apis/kueue.x-k8s.io/v1beta2/clusterqueues" \
    | python3 -c 'import json,sys; print(sum(int((item.get("status") or {}).get("admittedWorkloads") or 0) for item in json.load(sys.stdin)["items"]))'
}

# regular_pass_active — success while a Job of the regular warm-cache CronJob is
# unfinished.  The two CronJobs have separate concurrencyPolicy scopes, so Forbid
# on either does not order them; this read does.  A Job counts until it carries a
# true Complete or Failed condition, not only while status.active is non-zero, so
# a regular Job the CronJob created but whose pod is not yet counted (queued) is
# waited out too.  Fails closed (reports active) when the Job list cannot be read.
regular_pass_active() {
  local token namespace jobs
  [ -r "${K8S_SA_DIR}/token" ] && [ -r "${K8S_SA_DIR}/namespace" ] || return 0
  token="$(cat "${K8S_SA_DIR}/token")"
  namespace="$(cat "${K8S_SA_DIR}/namespace")"
  jobs="$(curl --silent --fail --max-time 10 \
    --cacert "${K8S_SA_DIR}/ca.crt" -H "Authorization: Bearer ${token}" \
    "https://kubernetes.default.svc/apis/batch/v1/namespaces/${namespace}/jobs")" || return 0
  python3 -c '
import json, sys
cronjob = sys.argv[1]
for item in json.load(sys.stdin)["items"]:
    owners = item["metadata"].get("ownerReferences") or []
    if any(o.get("kind") == "CronJob" and o.get("name") == cronjob for o in owners):
        status = item.get("status") or {}
        finished = any(
            c.get("type") in ("Complete", "Failed") and c.get("status") == "True"
            for c in status.get("conditions") or []
        )
        if int(status.get("active") or 0) > 0 or not finished:
            sys.exit(0)
sys.exit(1)
' "${REGULAR_CRONJOB}" <<<"${jobs}" || return 1
}

# wait_for_regular_pass — hold the fork pass behind any running regular pass, up to
# FABRO_WAIT_FOR_REGULAR_SECONDS, so the fork's build never contends with the
# routed repositories' 3600-second warm.  Returns 1 when the wait ran out.
wait_for_regular_pass() {
  local waited=0
  while regular_pass_active; do
    if [ "${waited}" -ge "${FABRO_WAIT_FOR_REGULAR_SECONDS}" ]; then
      return 1
    fi
    [ "${waited}" -ne 0 ] || log "regular warm-cache pass is running; waiting for it before any Fabro work"
    sleep "${FABRO_REGULAR_POLL_SECONDS}"
    waited=$((waited + FABRO_REGULAR_POLL_SECONDS))
  done
}

sccache_env=(
  "RUSTC_WRAPPER=${SCCACHE_BIN}"
  "SCCACHE_SERVER_PORT=${SCCACHE_WRITER_PORT}"
  "SCCACHE_REDIS_ENDPOINT=${SCCACHE_REDIS_ENDPOINT}"
  "SCCACHE_REDIS_USERNAME=${SCCACHE_REDIS_WRITER_USERNAME}"
  "SCCACHE_REDIS_PASSWORD=${SCCACHE_REDIS_WRITER_PASSWORD}"
  "SCCACHE_REDIS_RW_MODE=READ_WRITE"
)

# The two CARGO_* variables both fork workflows set at workflow level.  sccache
# hashes every CARGO_* variable into a compile's key, so the warm must carry the
# workflows' values rather than the image's (CARGO_NET_RETRY=5), or it writes
# keys the ARC jobs never ask for.
cargo_env=(
  "CARGO_NET_RETRY=10"
  "CARGO_TERM_COLOR=always"
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
  memory="$(redis_default_raw INFO memory)" || return 1
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

# ensure_fork_toolchain_bootstrap — the fork's ARC jobs use buildpack-deps:noble,
# whose build tools include make, then provision Rust through rustup.  The warm
# uses that same base and adds only the Python and Rust runtime tools it needs.
ensure_fork_toolchain_bootstrap() {
  if command -v python3 >/dev/null && command -v rustup >/dev/null; then
    export PATH="${HOME}/.cargo/bin:${PATH}"
    return 0
  fi
  DEBIAN_FRONTEND=noninteractive apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 rustup
  export PATH="${HOME}/.cargo/bin:${PATH}"
  command -v python3 >/dev/null && command -v rustup >/dev/null
}

# ensure_toolchain TOOLCHAIN [COMPONENT] — the fork's jobs compile with a pinned
# nightly and a pinned stable, so each profile installs the toolchain it compiles
# with.  rustup is idempotent: a toolchain already present is a no-op.
ensure_toolchain() {
  local toolchain="$1" component="${2:-}"
  command -v rustup >/dev/null || { log "rustup is not on PATH; cannot install ${toolchain}"; return 1; }
  if [ -n "${component}" ]; then
    rustup toolchain install "${toolchain}" --profile minimal --component "${component}" --no-self-update
  else
    rustup toolchain install "${toolchain}" --profile minimal --no-self-update
  fi
}

# ensure_bun — carrier-build installs Bun ${FABRO_BUN_VERSION} (setup-bun) before
# `cargo dev build`, whose SPA refresh runs `bun run build`.  The image has no
# Bun, so the release warm fetches the same release.
ensure_bun() {
  local arch archive
  if command -v bun >/dev/null && [ "$(bun --version)" = "${FABRO_BUN_VERSION}" ]; then
    return 0
  fi
  case "$(uname -m)" in
    x86_64) arch=x64 ;;
    aarch64|arm64) arch=aarch64 ;;
    *) log "no Bun release for $(uname -m)"; return 1 ;;
  esac
  archive="${SCRATCH}/bun.zip"
  curl --silent --fail --location --max-time 300 --output "${archive}" \
    "https://github.com/oven-sh/bun/releases/download/bun-v${FABRO_BUN_VERSION}/bun-linux-${arch}.zip" \
    || { log "Bun ${FABRO_BUN_VERSION} could not be downloaded"; return 1; }
  python3 -c '
import sys, zipfile
zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])
' "${archive}" "${SCRATCH}/bun" || return 1
  chmod 755 "${SCRATCH}/bun/bun-linux-${arch}/bun"
  export PATH="${SCRATCH}/bun/bun-linux-${arch}:${PATH}"
}

# ensure_nextest — the fork's Test job installs cargo-nextest (taiki-e's
# install-action) before `cargo nextest run`; the image carries only cargo-fuzz.
# A pinned musl release is fetched and its published sha256 verified, then put on
# PATH, where cargo resolves the `nextest` subcommand.  The nextest version is
# not part of any sccache key: nextest builds through `cargo test --no-run`, and
# only rustc's own invocations are hashed.
ensure_nextest() {
  local target want archive dir
  if command -v cargo-nextest >/dev/null; then
    return 0
  fi
  if ! command -v sha256sum >/dev/null || ! command -v tar >/dev/null; then
    log "sha256sum or tar is not on PATH; cannot install cargo-nextest"
    return 1
  fi
  case "$(uname -m)" in
    x86_64)
      target=x86_64-unknown-linux-musl
      want=84f0f9ba75d0b6fa117bc418d49747ba78e20e4583057f6fa628f1b17c17234d
      ;;
    aarch64|arm64)
      target=aarch64-unknown-linux-musl
      want=5a7fe62b64a9006e1e47422021df7b1d308cc76c528c9eaf4649a488615ed6fb
      ;;
    *) log "no cargo-nextest release for $(uname -m)"; return 1 ;;
  esac
  [ "${FABRO_NEXTEST_VERSION}" = "0.9.150" ] \
    || { log "cargo-nextest ${FABRO_NEXTEST_VERSION} has no pinned checksum here"; return 1; }
  archive="${SCRATCH}/cargo-nextest.tar.gz"
  dir="${SCRATCH}/nextest"
  curl --silent --fail --location --max-time 300 --output "${archive}" \
    "https://github.com/nextest-rs/nextest/releases/download/cargo-nextest-${FABRO_NEXTEST_VERSION}/cargo-nextest-${FABRO_NEXTEST_VERSION}-${target}.tar.gz" \
    || { log "cargo-nextest ${FABRO_NEXTEST_VERSION} could not be downloaded"; return 1; }
  printf '%s  %s\n' "${want}" "${archive}" | sha256sum --check --status \
    || { log "cargo-nextest ${FABRO_NEXTEST_VERSION} failed its sha256 check"; return 1; }
  mkdir -p "${dir}"
  tar --no-same-owner -xzf "${archive}" -C "${dir}" cargo-nextest || return 1
  chmod 755 "${dir}/cargo-nextest"
  export PATH="${dir}:${PATH}"
}

# prepare_carrier_release — the steps carrier-build runs before its compile:
# Bun, `bun install --frozen-lockfile`, then a clean of the SPA crate so the
# release build re-runs the SPA refresh exactly as the workflow does.
prepare_carrier_release() {
  ensure_bun || return 1
  (
    cd "${build_dir}"
    bun install --frozen-lockfile
    RUSTUP_TOOLCHAIN=1.97.1 cargo clean --release -p fabro-spa
  )
}

warm_profile() {
  local branch="$1" profile="$2" toolchain="$3" component="$4" node_env="$5" prepare="$6"
  local sha marker want have started
  shift 6
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
  if ! ensure_toolchain "${toolchain}" "${component}"; then
    log "${branch}/${profile} toolchain ${toolchain} could not be installed; marker remains absent for the next tick"
    return 1
  fi
  if [ -n "${prepare}" ] && ! "${prepare}"; then
    log "${branch}/${profile} preparation ${prepare} failed; marker remains absent for the next tick"
    return 1
  fi
  if [ -n "${node_env}" ]; then
    if (cd "${build_dir}" && env "${sccache_env[@]}" "${cargo_env[@]}" "NODE_ENV=${node_env}" nice -n 19 ionice -c 3 "$@"); then
      started=true
    else
      started=false
    fi
  elif (cd "${build_dir}" && env "${sccache_env[@]}" "${cargo_env[@]}" nice -n 19 ionice -c 3 "$@"); then
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
ensure_fork_toolchain_bootstrap || die "the fork build image could not bootstrap python3 and rustup"
command -v make >/dev/null || die "make is not on PATH"
command -v git >/dev/null || die "git is not on PATH"
command -v python3 >/dev/null || die "python3 is not on PATH"

wait_for_regular_pass \
  || { log "regular warm-cache pass still running after ${FABRO_WAIT_FOR_REGULAR_SECONDS}s; skipping this tick"; exit 0; }
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

clippy_command=(cargo +nightly-2026-04-14 clippy --workspace --all-targets -- -D warnings)
# The Test job runs `tini -s -- cargo nextest run --locked --workspace --profile ci`.
# `nextest list` with the same arguments compiles the same test binaries through
# the same `cargo test --no-run` call, so it writes the keys that job asks for,
# without running the fork's test suite inside this pass: a failing fork test
# would otherwise leave the profile's marker unset and fail every hourly tick.
test_command=(cargo +1.97.1 nextest list --locked --workspace --profile ci)
release_command=(cargo +1.97.1 dev build --release -p fabro-cli)

failed=0
warm_profile factory-integration clippy nightly-2026-04-14 clippy "" "" "${clippy_command[@]}" || failed=1
warm_profile factory-integration test 1.97.1 "" "" ensure_nextest "${test_command[@]}" || failed=1
warm_profile carrier-candidate-registered-20261023 carrier-release 1.97.1 "" production prepare_carrier_release "${release_command[@]}" || failed=1
SCCACHE_SERVER_PORT="${SCCACHE_WRITER_PORT}" "${SCCACHE_BIN}" --show-stats 2>/dev/null \
  | grep -E 'Compile requests|Cache hits|Cache misses|Cache errors|Cache write|Non-cacheable' \
  | sed 's/^/sccache stats: /' || true

[ "${failed}" -eq 0 ] || exit 1
