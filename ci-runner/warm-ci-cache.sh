#!/usr/bin/env bash
# warm-ci-cache.sh — the TRUSTED write-back path for T10 cache-tiering
# (livespec-dev-tooling-9mp).
#
# sanitize-hook.js mounts /home/ci-runner/cache/<reposlug>/{cargo,target,uv} into
# each job container READ-ONLY through a throwaway overlay, so a job container can
# NEVER write the shared lower. Something trusted must therefore populate (and
# refresh) those lowers. That is THIS script: it builds a repo checkout in the
# baked sandbox image AS ci-runner, on the HOST, with the lower dirs mounted
# READ-WRITE — a context a fork PR can never reach. There is no tier decision
# anywhere (the hook makes none; this runs outside any job), so no forgeable
# signal exists. Run it by hand, from the supervisor, or from a systemd timer;
# NEVER from inside a job container.
#
# It reproduces the compile-producing steps the CI matrix runs, so the warm
# `target/` holds the dependency artifacts every matrix job would otherwise
# rebuild TEN times concurrently (the cause of the Rust matrix's 2x regression).
#
# Usage:
#   warm-ci-cache.sh --repo <reposlug> --clone <path> [--image <tag>]
#                    [--rust] [--with-tools] [--warm-cmd '<shell>']
#     --repo       dash-form repo slug, e.g. thewoolleyman-livespec-console-beads-fabro
#                  (must match the sanitize-hook cache namespace / provisioned lower)
#     --clone      a checkout of that repo to build (read-only mount)
#     --image      sandbox image tag (default: the console's python-rust tag)
#     --rust       warm cargo registry + target (default: uv only)
#     --with-tools cargo-install the extra tools (nextest/llvm-cov/deny/machete)
#                  into the warm cargo/bin so coverage/nextest builds warm too
#                  and jobs need no per-run download (slow first pass; cached after)
#     --warm-cmd   override the in-container warm-up shell (advanced)
set -euo pipefail

RUNNER_USER=ci-runner
CACHE_ROOT=/home/${RUNNER_USER}/cache
IMAGE=ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-rust-v0.48.2
REPO="" CLONE="" RUST=0 WITH_TOOLS=0 WARM_CMD=""

while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2;;
    --clone) CLONE="$2"; shift 2;;
    --image) IMAGE="$2"; shift 2;;
    --rust) RUST=1; shift;;
    --with-tools) WITH_TOOLS=1; shift;;
    --warm-cmd) WARM_CMD="$2"; shift 2;;
    *) echo "warm-ci-cache: unknown argument: $1" >&2; exit 2;;
  esac
done
[ -n "$REPO" ]  || { echo "warm-ci-cache: --repo <reposlug> required" >&2; exit 2; }
[ -n "$CLONE" ] || { echo "warm-ci-cache: --clone <path> required" >&2; exit 2; }
[ -d "$CLONE" ] || { echo "warm-ci-cache: clone not found: $CLONE" >&2; exit 2; }

# /home/ci-runner is mode 750 (untraversable by the admin invoking this), so the
# cache-dir existence probes MUST run AS ci-runner, not as the calling admin.
run_test_d() { sudo -n -u "$RUNNER_USER" test -d "$1"; }
LOWER="${CACHE_ROOT}/${REPO}"
run_test_d "$LOWER" || { echo "warm-ci-cache: no cache tree at $LOWER — run provision-ci-runner.sh first" >&2; exit 1; }

# Mounts: clone READ-ONLY (:ro only — NEVER :U, which would recursively chown the
# real checkout; repo files are world-readable so the ci-runner-mapped container
# root can read them). The lower dirs are READ-WRITE at the SAME container targets
# the hook uses, with the SAME env, so artifacts land keyed exactly as a job looks
# them up. Build scripts write only to OUT_DIR (under CARGO_TARGET_DIR), so a
# read-only source tree is fine with --locked.
declare -a MOUNTS ENVS
add_cache() { # <subdir> <container-target> <ENV_NAME>
  local sub="$1" tgt="$2" env="$3"
  run_test_d "${LOWER}/${sub}" || return 0
  MOUNTS+=("-v" "${LOWER}/${sub}:${tgt}")
  ENVS+=("-e" "${env}=${tgt}")
}
add_cache uv /opt/ci-cache/uv UV_CACHE_DIR
if [ "$RUST" = 1 ]; then
  add_cache cargo /opt/ci-cache/cargo CARGO_HOME
  add_cache target /opt/ci-cache/target CARGO_TARGET_DIR
fi

# Default warm-up: fetch + the compile-producing check recipes' cargo commands,
# mirroring the console CI matrix so every profile (build / clippy / test / cov)
# is warm. Skips nextest/llvm-cov unless --with-tools installed them.
if [ -z "$WARM_CMD" ]; then
  WARM_CMD='set -eux; cd /src'
  if [ "$RUST" = 1 ]; then
    if [ "$WITH_TOOLS" = 1 ]; then
      WARM_CMD="$WARM_CMD"'
        command -v cargo-nextest  >/dev/null || cargo install --locked cargo-nextest
        command -v cargo-llvm-cov >/dev/null || cargo install --locked cargo-llvm-cov
        command -v cargo-deny     >/dev/null || cargo install --locked cargo-deny
        command -v cargo-machete  >/dev/null || cargo install --locked cargo-machete'
    fi
    WARM_CMD="$WARM_CMD"'
      cargo fetch --locked
      cargo build --workspace --all-targets --all-features --locked
      cargo clippy --workspace --all-targets --all-features --locked -- -D warnings || true
      cargo test --workspace --all-features --locked --no-run || true'
    if [ "$WITH_TOOLS" = 1 ]; then
      WARM_CMD="$WARM_CMD"'
        cargo nextest run --workspace --all-features --no-run || true
        cargo llvm-cov --workspace --all-features --lib --no-report || true'
    fi
  fi
  # A uv warm-up if the repo carries Python deps (harmless no-op otherwise).
  WARM_CMD="$WARM_CMD"'
    if [ -f pyproject.toml ] || [ -f uv.lock ]; then uv sync --all-groups || true; fi'
fi

echo "== warming ${REPO} cache in ${IMAGE} (rust=${RUST} with-tools=${WITH_TOOLS}) =="
set -x
sudo -n -u "$RUNNER_USER" env XDG_RUNTIME_DIR="/run/user/$(id -u "$RUNNER_USER")" \
  podman run --rm \
  -v "${CLONE}:/src:ro" \
  "${MOUNTS[@]}" "${ENVS[@]}" \
  "$IMAGE" bash -lc "$WARM_CMD"
set +x
echo "== warm complete — lower dirs populated under ${LOWER} =="
sudo -n -u "$RUNNER_USER" du -sh "${LOWER}"/* 2>/dev/null || true
