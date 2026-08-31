#!/bin/sh
# livespec cargo-phase telemetry shim — fabro-sandbox python-rust image ONLY.
#
# Interposed on PATH ahead of the rustup cargo (see the python-rust Dockerfile)
# so a FACTORY console build — a fabro dispatch, build.env=factory — emits one
# build-telemetry OTLP span per measured cargo phase, WITHOUT any change to the
# console repo (the console workflow.toml runs cargo via its agent + git hooks,
# not via a wrappable prepare step, so the wrap point has to live in the image).
#
# It runs the REAL cargo UNCHANGED, then best-effort hands the timing to the
# baked livespec-cargo-phase-timer. The stopwatch is strictly non-fatal: cargo's
# own exit code is always propagated, and cargo still runs when the timer binary
# is absent or fails. Unmeasured subcommands (fmt, clippy, tree, metadata,
# --version, …) exec the real cargo directly with zero added overhead.
set -u

REAL_CARGO=/root/.cargo/bin/cargo

sub=${1:-}
phase=
case "$sub" in
  build | b | check | c | rustc) phase="compile" ;;
  test | t | nextest) phase="test" ;;
  llvm-cov) phase="test" ;;
  fuzz) phase="fuzz" ;;
  fetch) phase="fetch" ;;
esac

if [ -z "$phase" ]; then
  exec "$REAL_CARGO" "$@"
fi

start=$(date +%s%N)
"$REAL_CARGO" "$@"
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
