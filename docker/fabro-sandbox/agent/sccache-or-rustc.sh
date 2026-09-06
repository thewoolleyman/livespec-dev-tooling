#!/bin/sh
# sccache-or-rustc — the sandbox's `rustc-wrapper`: sccache when its server is
# up or can be started, plain rustc otherwise. Console plan
# optimize-console-builds, livespec-console-beads-fabro-di6fn5 (bullet 5: a
# telemetry or cache fault never changes a run's cargo exit code).
#
# WHY NOT `rustc-wrapper = sccache` DIRECTLY: sccache falls back to a plain
# compile when a cache OPERATION fails, but when its SERVER cannot start —
# which is what an unreachable redis looks like at first use — the client
# exits non-zero ("Timed out waiting for server startup") and cargo fails the
# build. Measured 2026-09-06 in the agent image with no redis listening. A
# factory host without the sccache-redis service (or with it down) must build
# exactly as it did before, so the decision is made ONCE per container, by a
# bounded probe, and remembered in a marker file:
#   /tmp/.sccache-or-rustc/usable   -> exec sccache "$@"
#   /tmp/.sccache-or-rustc/unusable -> exec "$@"  (plain rustc)
# The probe is the FIRST real request itself (cargo's own `rustc -vV`), run
# through sccache under a bounded timeout: a server that starts but cannot
# reach its backend only fails at the first compile, so nothing short of a
# real request is evidence (measured: `--start-server` and `--show-stats`
# both "succeed" with no redis, and the compile still fails). On failure the
# request is re-run plainly — sccache's error went to the probe log, so the
# compiler's output is emitted exactly once — and the verdict is remembered.
# sccache reads its backend from ~/.config/sccache/config (the image bakes the
# endpoint) and needs no environment — fabro's spawn allowlist cannot strip a
# file. Cost when the cache is down: one bounded probe per container.
state=/tmp/.sccache-or-rustc
if [ -e "$state/usable" ]; then
    exec sccache "$@"
fi
if [ -e "$state/unusable" ] || ! command -v sccache >/dev/null 2>&1; then
    exec "$@"
fi
mkdir -p "$state" 2>/dev/null
if SCCACHE_STARTUP_TIMEOUT_MS=5000 timeout 20 sccache "$@" 2>"$state/probe.log"; then
    : > "$state/usable"
    exit 0
fi
: > "$state/unusable"
exec "$@"
