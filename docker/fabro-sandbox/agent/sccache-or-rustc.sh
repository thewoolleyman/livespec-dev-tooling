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
#   <state>/usable   -> exec sccache "$@"
#   <state>/unusable -> exec "$@"  (plain rustc)
#
# THE PROBE IS A SYNTHETIC COMPILE, NEVER THE CALLER'S REQUEST. The first
# version of this wrapper ran the caller's own request under `timeout 20`,
# assuming it would be cargo's `rustc -vV`. It is not always: whenever the
# markers are absent while a build is already under way — a fresh /tmp, or
# the marker directory removed by whatever the job runs — the "probe" is a
# real crate compile, which on the sandbox's 4 vCPUs routinely takes longer
# than 20 s, so the timeout killed it, the verdict became `unusable`, and the
# rest of the container built plainly (measured 2026-09-06, console run
# 01M1TZ95M45VS8SMVCDXQM3XS6: verdict flipped to unusable at 09:57 after 15
# cache hits, then 284 misses and zero sccache traffic). Now the probe
# compiles a one-line crate through sccache with the cache's real backend in
# the path (a lookup and a write), bounded by the timeout, while the caller's
# request runs unbounded afterwards. Concurrent first callers (cargo starts
# several rustc at once) do not race the probe: one takes the lock and
# probes, the others compile plainly this once and read the verdict next
# time.
#
# sccache reads its backend from ~/.config/sccache/config (the image bakes the
# endpoint) and needs no environment — fabro's spawn allowlist cannot strip a
# file. The server's idle timeout is disabled here so a long test phase does
# not leave a later compile to restart it against a backend that may have
# gone away since the verdict (that restart is the one path that would fail
# cargo). Cost when the cache is down: one bounded probe per container.
state="${SCCACHE_OR_RUSTC_STATE:-/var/lib/sccache-or-rustc}"
export SCCACHE_IDLE_TIMEOUT="${SCCACHE_IDLE_TIMEOUT:-0}"

if [ -e "$state/usable" ]; then
    exec sccache "$@"
fi
if [ -e "$state/unusable" ] || ! command -v sccache >/dev/null 2>&1; then
    exec "$@"
fi

# No verdict yet. Exactly one caller probes; the rest compile plainly now.
mkdir -p "$state" 2>/dev/null
if ! mkdir "$state/probe.lock" 2>/dev/null; then
    exec "$@"
fi
probe_dir="$state/probe"
mkdir -p "$probe_dir"
printf 'fn main() {}\n' > "$probe_dir/probe.rs"
if SCCACHE_STARTUP_TIMEOUT_MS=5000 timeout 20 \
     sccache rustc --edition 2021 --crate-type bin \
       -o "$probe_dir/probe" "$probe_dir/probe.rs" >"$state/probe.log" 2>&1; then
    : > "$state/usable"
    rmdir "$state/probe.lock" 2>/dev/null
    exec sccache "$@"
fi
: > "$state/unusable"
rmdir "$state/probe.lock" 2>/dev/null
exec "$@"
