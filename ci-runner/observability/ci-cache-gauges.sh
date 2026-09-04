#!/usr/bin/env bash
# ci-cache-gauges.sh — emit the CI host's BUILD-CACHE health gauges.
#
# The host-side half of SPECIFICATION/non-functional-requirements.md
# §"Runner-pool cache telemetry" (v054): "A tier with no emitted signal MUST
# NOT be considered shipped." Plan ci-runner-cache-tiers, child
# livespec-dev-tooling-gjqw2i; the contract is the plan's
# research/003-cache-observability.md §"Host gauges".
#
# Every five minutes (ci-cache-gauges.timer, the same cadence and the same
# loopback collector as ci-runner-heartbeat.sh) this posts ONE OTLP/HTTP
# metrics request to 127.0.0.1:4319, which the host otel-collector exports to
# the `livespec` Honeycomb environment's `metrics` dataset stamped host.name.
# service.name=ci-runner-liveness like the heartbeat, so the pool's host
# gauges are one query family. Gauges (all prefixed livespec.ci_cache.):
#
#   kill_switch                    0/1 — CI_CACHE_KILL_SWITCH set in the hook
#                                  pod template. Always emitted; it is the
#                                  column the cache dead-man trigger counts.
#   generation_age_s {tier=uv}     seconds since the current warm-uv
#   generation_bytes {tier=uv}     generation was published, and its size.
#   registry.up                    whether the crates proxy's stub_status
#   registry.requests_5m           answered, and requests it served since
#                                  the last tick. (No store-size gauge: nginx
#                                  keeps its cache tree 0700 and this emitter
#                                  is unprivileged; a du as root on the host
#                                  answers that question when asked.)
#   sccache.up                     redis answered INFO.
#   sccache.keys                   DBSIZE.
#   sccache.keyspace_hits/misses   redis's cumulative counters (gauges of a
#                                  counter; the 5m ratio below is the
#                                  actionable one).
#   sccache.hit_ratio_5m           hits/(hits+misses) over the last tick,
#                                  emitted ONLY when there was traffic — an
#                                  idle host is not a cold cache.
#   sccache.used_memory_bytes, .maxmemory_bytes, .evicted_keys
#   sccache.memory_ratio           used/max — the eviction-pressure signal.
#   sccache.populated_repos        marker keys present (one per routed Rust
#                                  repository whose default branch is built).
#   populate.age_s {toolchain}     seconds since the populator last
#                                  published, from its manifest, plus
#   populate.duration_s, .repos_synced, .repos_failed, .cargo_warmed,
#   .sccache_built                 the manifest's counts.
#
# FAIL-CLOSED PER SOURCE, like the heartbeat's split: a source that cannot be
# READ (the warm root missing, the manifest unparseable, the template
# absent) emits NOTHING for its gauges and makes this script exit non-zero,
# so the journal is red and the dead-man can fire on the missing column. A
# source that answers "down" (the proxy's status page or redis refusing the
# connection) is a genuine reading — `registry.up=0` / `sccache.up=0` ARE
# emitted, and the rest of that source's gauges are omitted rather than sent
# as false zeros. 0 hits on an idle host, 0 failed repositories, and a 0
# kill switch are legitimate zeros and are emitted.
#
# WHO READS THESE (the precedent in the heartbeat's header: a metric with no
# named reader is indistinguishable from one that stopped): the triggers in
# ./triggers/ci-cache-*.json (dead-man on kill_switch datapoints; stale
# generation; populate failing; sccache hit floor; redis memory pressure),
# and the plan's archive-evidence queries (research/003 §"Acceptance
# evidence"). The per-JOB cache spans are a different emitter (the pod
# lifecycle hooks, livespec-dev-tooling-mlg5sf).
#
# Runs as a DynamicUser with StateDirectory=ci-cache-gauges for the
# previous tick's counters (the 5m deltas). Every read here is unprivileged:
# the warm root and the proxy store are world-readable, the proxy's
# stub_status and redis are reached over loopback through their hostPorts,
# redis's unauthenticated user has +info +@read for exactly this, and the
# hook template is read from the boot-durable copy the converge applies
# (/usr/local/lib/ci-runner-k3s/arc/), not from the cluster, so no kubectl
# credential is needed.
set -uo pipefail

OTLP_ENDPOINT="${CI_RUNNER_HEARTBEAT_OTLP:-http://127.0.0.1:4319/v1/metrics}"
WARM_ROOT="${CI_CACHE_WARM_ROOT:-/var/cache/ci-runner/warm}"
PROXY_STATUS_URL="${CI_CACHE_PROXY_STATUS_URL:-http://127.0.0.1:3080/nginx_status}"
REDIS_HOST="${CI_CACHE_REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${CI_CACHE_REDIS_PORT:-6379}"
MANIFEST="${CI_CACHE_POPULATE_MANIFEST:-${WARM_ROOT}/populate-manifest.json}"
TEMPLATE="${CI_CACHE_HOOK_TEMPLATE:-/usr/local/lib/ci-runner-k3s/arc/hook-pod-template.yaml}"
STATE_DIR="${STATE_DIRECTORY:-/var/lib/ci-cache-gauges}"
STATE_FILE="${STATE_DIR}/last.env"

log() { printf 'ci-cache-gauges: %s\n' "$*"; }
now="$(date +%s)"
now_ns="$(date +%s%N)"
host_name="$(hostname)"
readings="$(mktemp)"
trap 'rm -f "${readings}"' EXIT
failed=0
put() { printf '%s=%s\n' "$1" "$2" >> "${readings}"; }

# ---- previous tick (for the 5m deltas) --------------------------------------
prev_requests=""; prev_hits=""; prev_misses=""
if [ -r "${STATE_FILE}" ]; then
  # shellcheck disable=SC1090  # our own key=value file
  . "${STATE_FILE}" || true
fi

# ---- kill switch (always emitted; the dead-man column) -----------------------
if [ -r "${TEMPLATE}" ]; then
  ks="$(awk '/name: CI_CACHE_KILL_SWITCH/{getline; sub(/^[^:]*: */, ""); gsub(/"/, ""); print; exit}' "${TEMPLATE}")"
  if [ -n "${ks}" ]; then put kill_switch 1; else put kill_switch 0; fi
else
  log "hook template ${TEMPLATE} unreadable; refusing to emit a false kill_switch (dead-man will count this)" >&2
  failed=1
fi

# ---- warm uv tier ------------------------------------------------------------
if target="$(readlink -f "${WARM_ROOT}/uv" 2>/dev/null)" && [ -d "${target}" ]; then
  put uv_generation_age_s "$(( now - $(stat -c %Y "${target}") ))"
  put uv_generation_bytes "$(du -sb "${target}" | cut -f1)"
else
  log "warm root ${WARM_ROOT}/uv has no current generation; omitting the uv tier" >&2
  failed=1
fi

# ---- crates proxy ------------------------------------------------------------
if status="$(curl --silent --fail --max-time 5 "${PROXY_STATUS_URL}" 2>/dev/null)"; then
  put registry_up 1
  requests="$(printf '%s\n' "${status}" | awk 'prev ~ /server accepts handled requests/ {print $3; exit} {prev=$0}')"
  if [ -n "${requests}" ]; then
    put registry_requests_total "${requests}"
    if [ -n "${prev_requests}" ] && [ "${requests}" -ge "${prev_requests}" ]; then
      put registry_requests_5m "$(( requests - prev_requests ))"
    fi
  fi
else
  put registry_up 0
fi

# ---- sccache redis (python3 for RESP; no redis-cli on the host) ---------------
redis_out="$(python3 - "${REDIS_HOST}" "${REDIS_PORT}" <<'PY' 2>/dev/null
import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
def enc(*parts):
    out = b"*%d\r\n" % len(parts)
    for p in parts:
        b = p.encode(); out += b"$%d\r\n%s\r\n" % (len(b), b)
    return out
def reply(f):
    line = f.readline()
    if not line: raise SystemExit(2)
    t, body = chr(line[0]), line[1:-2].decode()
    if t in "+:": return body
    if t == "-": raise SystemExit("ERR " + body)
    if t == "$":
        n = int(body)
        return None if n < 0 else f.read(n + 2)[:-2].decode()
    if t == "*": return [reply(f) for _ in range(int(body))]
    raise SystemExit(2)
try:
    s = socket.create_connection((host, port), timeout=5)
except OSError:
    print("up=0"); raise SystemExit(0)
f = s.makefile("rb")
s.sendall(enc("INFO")); info = reply(f) or ""
kv = dict(l.split(":", 1) for l in info.splitlines() if ":" in l and not l.startswith("#"))
s.sendall(enc("DBSIZE")); keys = reply(f)
populated = 0; cursor = "0"
while True:
    s.sendall(enc("SCAN", cursor, "MATCH", "livespec:sccache:populated:*", "COUNT", "1000"))
    cursor, batch = reply(f); populated += len(batch)
    if cursor == "0": break
print("up=1")
for k in ("keyspace_hits", "keyspace_misses", "used_memory", "maxmemory", "evicted_keys"):
    print(f"{k}={kv.get(k, '')}")
print(f"keys={keys}"); print(f"populated={populated}")
PY
)" || true
if [ -z "${redis_out}" ]; then
  log "redis read failed in a way that is not 'down' (protocol/permission); omitting sccache gauges" >&2
  failed=1
else
  # shellcheck disable=SC2034  # keys are consumed via the case below
  while IFS='=' read -r k v; do
    case "$k" in
      up) put sccache_up "$v" ;;
      keyspace_hits) hits="$v"; put sccache_keyspace_hits "$v" ;;
      keyspace_misses) misses="$v"; put sccache_keyspace_misses "$v" ;;
      used_memory) used="$v"; put sccache_used_memory_bytes "$v" ;;
      maxmemory) maxmem="$v"; put sccache_maxmemory_bytes "$v" ;;
      evicted_keys) put sccache_evicted_keys "$v" ;;
      keys) put sccache_keys "$v" ;;
      populated) put sccache_populated_repos "$v" ;;
    esac
  done <<< "${redis_out}"
  if [ -n "${used:-}" ] && [ -n "${maxmem:-}" ] && [ "${maxmem}" -gt 0 ]; then
    put sccache_memory_ratio "$(awk -v u="${used}" -v m="${maxmem}" 'BEGIN{printf "%.4f", u / m}')"
  fi
  if [ -n "${hits:-}" ] && [ -n "${prev_hits}" ] && [ "${hits}" -ge "${prev_hits}" ] && [ "${misses}" -ge "${prev_misses}" ]; then
    dh=$(( hits - prev_hits )); dm=$(( misses - prev_misses ))
    if [ $(( dh + dm )) -gt 0 ]; then
      put sccache_hit_ratio_5m "$(awk -v h="${dh}" -v m="${dm}" 'BEGIN{printf "%.4f", h / (h + m)}')"
    fi
  fi
fi

# ---- populate manifest ---------------------------------------------------------
if [ -r "${MANIFEST}" ]; then
  if ! python3 - "${MANIFEST}" "${now}" >> "${readings}" <<'PY'
import json, sys
m = json.load(open(sys.argv[1])); now = int(sys.argv[2])
print(f"populate_age_s={now - int(m['published_at_epoch'])}")
for k in ("duration_s", "repos_synced", "repos_failed", "cargo_warmed", "sccache_built"):
    print(f"populate_{k}={int(m[k])}")
print(f"populate_toolchain={m.get('toolchain_version', '')}")
PY
  then
    log "manifest ${MANIFEST} unparseable; omitting populate gauges" >&2
    failed=1
  fi
else
  log "manifest ${MANIFEST} absent (the populator has not published one yet); omitting populate gauges" >&2
  failed=1
fi

# ---- assemble + POST -----------------------------------------------------------
payload="$(python3 - "${readings}" "${now_ns}" "${host_name}" <<'PY'
import json, sys
r = {}
for line in open(sys.argv[1]):
    k, _, v = line.rstrip("\n").partition("="); r[k] = v
now_ns, host = sys.argv[2], sys.argv[3]
def attrs(d): return [{"key": k, "value": {"stringValue": v}} for k, v in d.items()]
def g(name, key, unit, desc, a=None, double=False):
    if key not in r or r[key] == "": return None
    dp = {"timeUnixNano": now_ns}
    dp["asDouble" if double else "asInt"] = float(r[key]) if double else str(int(float(r[key])))
    if a: dp["attributes"] = attrs(a)
    return {"name": "livespec.ci_cache." + name, "description": desc, "unit": unit, "gauge": {"dataPoints": [dp]}}
spec = [
  ("kill_switch", "kill_switch", "1", "1 when CI_CACHE_KILL_SWITCH is set in the hook pod template (every tier off for every job)", None, False),
  ("generation_age_s", "uv_generation_age_s", "s", "Seconds since the current warm-cache generation was published", {"tier": "uv"}, False),
  ("generation_bytes", "uv_generation_bytes", "By", "Size of the current warm-cache generation", {"tier": "uv"}, False),
  ("registry.up", "registry_up", "1", "1 when the crates proxy's stub_status answered over loopback", None, False),
  ("registry.requests_total", "registry_requests_total", "{requests}", "Requests the crates proxy has served since it started (cumulative)", None, False),
  ("registry.requests_5m", "registry_requests_5m", "{requests}", "Requests the crates proxy served since the previous tick", None, False),
  ("sccache.up", "sccache_up", "1", "1 when the sccache redis answered INFO over loopback", None, False),
  ("sccache.keys", "sccache_keys", "{keys}", "Entries in the sccache redis (DBSIZE)", None, False),
  ("sccache.keyspace_hits", "sccache_keyspace_hits", "{hits}", "redis keyspace_hits (cumulative since redis started)", None, False),
  ("sccache.keyspace_misses", "sccache_keyspace_misses", "{misses}", "redis keyspace_misses (cumulative since redis started)", None, False),
  ("sccache.hit_ratio_5m", "sccache_hit_ratio_5m", "1", "hits/(hits+misses) over the previous tick; absent when there was no traffic", None, True),
  ("sccache.used_memory_bytes", "sccache_used_memory_bytes", "By", "redis used_memory", None, False),
  ("sccache.maxmemory_bytes", "sccache_maxmemory_bytes", "By", "redis maxmemory (the configured ceiling)", None, False),
  ("sccache.evicted_keys", "sccache_evicted_keys", "{keys}", "redis evicted_keys (cumulative)", None, False),
  ("sccache.memory_ratio", "sccache_memory_ratio", "1", "used_memory / maxmemory", None, True),
  ("sccache.populated_repos", "sccache_populated_repos", "{repos}", "Marker keys present: routed Rust repositories whose default branch the populator built into the cache", None, False),
  ("populate.age_s", "populate_age_s", "s", "Seconds since the populator last published a generation (from its manifest)", {"toolchain": r.get("populate_toolchain", "")}, False),
  ("populate.duration_s", "populate_duration_s", "s", "Duration of the populator's last run", None, False),
  ("populate.repos_synced", "populate_repos_synced", "{repos}", "Repositories whose uv lock synced in the last populate", None, False),
  ("populate.repos_failed", "populate_repos_failed", "{repos}", "Repository steps that failed in the last populate", None, False),
  ("populate.cargo_warmed", "populate_cargo_warmed", "{repos}", "Repositories whose Cargo.lock was pre-warmed through the crates proxy in the last populate", None, False),
  ("populate.sccache_built", "populate_sccache_built", "{repos}", "Repositories the populator built into the compilation cache in the last populate", None, False),
]
metrics = [m for m in (g(*s) for s in spec) if m]
print(json.dumps({"resourceMetrics": [{"resource": {"attributes": attrs({"service.name": "ci-runner-liveness", "host.name": host})},
  "scopeMetrics": [{"scope": {"name": "ci-cache-gauges"}, "metrics": metrics}]}]}))
print(len(metrics), file=sys.stderr)
PY
)"

if ! curl --silent --show-error --fail --max-time 10 -X POST "${OTLP_ENDPOINT}" \
     -H 'Content-Type: application/json' -d "${payload}" > /dev/null; then
  log "POST to ${OTLP_ENDPOINT} failed" >&2
  exit 7
fi

# ---- persist this tick's counters for the next delta -----------------------------
mkdir -p "${STATE_DIR}" 2>/dev/null || true
{

  printf 'prev_requests=%s\n' "$(awk -F= '$1=="registry_requests_total"{print $2}' "${readings}")"
  printf 'prev_hits=%s\n' "$(awk -F= '$1=="sccache_keyspace_hits"{print $2}' "${readings}")"
  printf 'prev_misses=%s\n' "$(awk -F= '$1=="sccache_keyspace_misses"{print $2}' "${readings}")"
} > "${STATE_FILE}.tmp" && mv -f "${STATE_FILE}.tmp" "${STATE_FILE}"

log "$(tr '\n' ' ' < "${readings}")-> ${OTLP_ENDPOINT}"
exit "${failed}"
