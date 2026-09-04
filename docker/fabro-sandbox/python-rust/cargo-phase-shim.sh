#!/usr/bin/env bash
# livespec cargo-phase telemetry shim — fabro-sandbox python-rust image ONLY.
#
# INSTALLED AS /root/.cargo/bin/cargo ITSELF (the rustup proxy is renamed to
# cargo-real alongside it; see the python-rust Dockerfile). This is deliberate:
# a shim placed on a SEPARATE PATH entry is bypassed the moment a consumer's
# `.mise.toml` re-prepends `~/.cargo/bin` — which livespec-console-beads-fabro
# does (`_.path = ["~/.cargo/bin"]`, so `mise exec -- just check` resolves
# `cargo` to the rustup proxy, never the shim). Being `~/.cargo/bin/cargo`
# itself means `cargo` resolves here under ANY PATH order that can run cargo at
# all — mise prepend included.
#
# It runs the REAL cargo UNCHANGED and best-effort hands each measured phase's
# timing to the baked livespec-cargo-phase-timer, which POSTs one OTLP span to the
# host OTel receiver (routed to the github-ci Honeycomb dataset by service.name —
# the keyless prepare.* seam), carrying the pool's build.cache.* compilation- and
# registry-cache attributes alongside the timing. The timer labels that span
# build.env=factory here and build.env=ci in a GitHub Actions job container, where
# it skips the POST altogether unless a (pod-reachable) endpoint is configured.
# Strictly non-fatal: cargo's own exit code is always propagated, and cargo
# still runs when the timer is absent or fails. Unmeasured subcommands (fmt,
# tree, metadata, --version, …) exec the real cargo directly with zero added
# overhead.
#
# cargo-real is the RENAMED rustup proxy, which dispatches on argv[0]: invoking
# it as `cargo-real` is rejected ("unknown proxy name"), so every call preserves
# argv[0]=cargo via `exec -a cargo` (hence bash, not POSIX sh).
set -u

REAL_CARGO=/root/.cargo/bin/cargo-real

sub=${1:-}
phase=
case "$sub" in
  build | b | check | c | rustc | clippy | doc | d | run | r) phase="compile" ;;
  test | t | nextest) phase="test" ;;
  llvm-cov) phase="test" ;;
  fuzz) phase="fuzz" ;;
  fetch) phase="fetch" ;;
esac

if [ -z "$phase" ]; then
  exec -a cargo "$REAL_CARGO" "$@"
fi

# Zero the compilation cache's counters BEFORE the measured phase, so the
# build.cache.sccache.* counts the span carries describe THIS phase rather than
# the sandbox's whole life. Deliberately outside the start/end stamps: the
# zeroing is the timer's cost, not cargo's. Best-effort like every other step
# here — a sandbox with no sccache simply has nothing to zero, and the span
# degrades to build.cache.sccache.enabled=false.
if command -v livespec-cargo-phase-timer >/dev/null 2>&1; then
  livespec-cargo-phase-timer --zero-stats >/dev/null 2>&1 || true
fi

start=$(date +%s%N)
( exec -a cargo "$REAL_CARGO" "$@" )
code=$?
end=$(date +%s%N)

if command -v livespec-cargo-phase-timer >/dev/null 2>&1; then
  BUILD_PHASE="$phase" \
    BUILD_SUBCMD="$sub" \
    BUILD_START_NANO="$start" \
    BUILD_END_NANO="$end" \
    BUILD_EXIT_CODE="$code" \
    livespec-cargo-phase-timer || true
fi

exit "$code"
