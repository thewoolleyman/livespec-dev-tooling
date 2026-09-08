#!/bin/sh
# ci-cache-span — the pool-provided emitter of a job's cache spans (plan
# ci-runner-cache-tiers, research/003 "Per-job spans"; SPECIFICATION
# non-functional-requirements.md §"Runner-pool cache telemetry", v054).
#
# Installed by ./install-cache-telemetry.sh at /usr/local/lib/ci-runner-k3s/
# bin/ci-cache-span, the directory ../arc/hook-pod-template.yaml mounts
# READ-ONLY into every job container at /opt/ci-runner/bin, and called from
# that template's lifecycle hooks — never from a workflow: the pool emits, the
# repositories change nothing (the transparency requirement).
#
#   ci-cache-span warm-copy <tier> <hit> <generation> <copy_ms> <copy_bytes> <copy_method> <error>
#       one span per tier from postStart: `cache.warm-copy` with
#       build.cache.{tier,hit,generation,generation_age_s,copy_ms,copy_bytes,
#       copy_method,error}.
#   ci-cache-span job-summary
#       one span per job from preStop: `cache.job-summary` with
#       build.cache.sccache.{enabled,hits,misses,errors,hit_ratio,backend,
#       rw_mode}, read from the job's own sccache server if one is listening.
#   ci-cache-span job-end
#       what preStop actually calls: REPLAYS every warm-copy line postStart
#       recorded in $CI_CACHE_STATE_DIR/warm-copy.tsv (at_ns<TAB>tier<TAB>hit
#       <TAB>generation<TAB>copy_ms<TAB>copy_bytes<TAB>copy_method<TAB>error)
#       with its recorded timestamps, plus the job-summary, in ONE POST.
#       Measured 2026-09-04: the runner writes event.json ~10 s after the pod
#       is created, while postStart runs at ~2 s — so a span emitted at start
#       has no repo/sha/branch, and waiting for the file would delay the job.
#       Recording at start and emitting at end keeps the per-tier timing AND
#       the identity, and costs the job nothing.
#   ci-cache-span publish-endpoint
#       what postStart calls FIRST: DERIVES this pod's collector address and
#       publishes it for both consumers. See "Deriving the endpoint" below.
#
# Every span carries repo, git.commit.sha, git.branch and ci.event (from the
# runner's event.json), build.env=ci, host.name (CI_RUNNER_NODE_NAME, a
# fieldRef the template sets) and build.cache.kill_switch ("" | operator |
# canary, the value postStart decided and wrote to the state dir), and posts
# as service.name=github-ci to the KEYLESS `otlp/pods` listener (otel-collector
# config.ci-runner-host.yaml) of the collector on THIS pod's OWN node, port
# 4319. No ingest key enters a job.
#
# DERIVING THE ENDPOINT (`publish-endpoint`, called from postStart; see
# README.md "Why the default gateway"). The pod-facing receiver binds the
# node's cni0 bridge address and NOTHING ELSE, deliberately: that bind IS the
# access control for a keyless receiver. The pod's OWN DEFAULT GATEWAY is that
# same cni0 address — a different one on every node, since flannel gives each
# node its own /24 — so reading the pod's default route yields the right
# collector on ANY node from ONE cluster-wide template.
# `publish-endpoint` publishes the derived `http://<gateway>:4319` two ways:
#
#   * $CI_CACHE_STATE_DIR/otlp_endpoint — read back below, and the reason this
#     script needs no endpoint in its environment at all;
#   * an /etc/hosts alias, $CI_CACHE_OTLP_ALIAS -> <gateway>, for the OTHER
#     consumer of the same listener: the sandbox image's baked cargo shim,
#     which reads $LIVESPEC_SANDBOX_OTEL_ENDPOINT and nothing else. An env
#     value cannot be computed per node, but a NAME in it can resolve per node,
#     which is what lets the pod template carry one literal for every node.
#
# NO DEFAULT ROUTE => NOTHING IS PUBLISHED, and every consumer then SKIPS
# emission rather than posting into a refused address: this script exits before
# python3 because neither the state file nor the env var names an endpoint, and
# the alias resolves nowhere. Skipping is the point — the previous derivation
# (`status.hostIP`, PR #1903) named the node's LAN address, where no collector
# listens, and every POST was refused SILENTLY for a month because the emitter
# fails soft. A silent skip is the same non-event; a silent refusal is a bug
# that looks like one.
#
# FAIL-SOFT IS THE CONTRACT: this script ALWAYS exits 0, emits nothing when
# the endpoint env is empty or python3 is absent, bounds its whole life with
# `timeout` (CI_CACHE_SPAN_TIMEOUT_S, default 4) and its POST with 2 s, and
# never touches the job's outcome. A hook that fails or delays a job beyond
# the copy itself would violate the v054 clause this serves.
#
# Env (the hook pod template sets CI_CACHE_STATE_DIR's default location, the
# node name and the sccache pair; the rest are defaults or test overrides):
#   CI_CACHE_STATE_DIR       default /__w/_temp/_ci_cache (postStart writes
#                            otlp_endpoint + kill_switch + started_at_ns;
#                            preStop reads them)
#   CI_CACHE_OTLP_ENDPOINT   FALLBACK base URL, used only when postStart
#                            published no endpoint; empty = emit nothing
#   CI_CACHE_OTLP_PORT       default 4319 (the otlp/pods listener's port)
#   CI_CACHE_OTLP_ALIAS      default otlp-collector.ci-runner.internal — the
#                            name the hosts alias publishes for the cargo shim
#   CI_CACHE_HOSTS_FILE      default /etc/hosts (test override)
#   CI_CACHE_PROC_NET_ROUTE  default /proc/net/route (test override)
#   CI_CACHE_SPAN_TIMEOUT_S  default 4
#   CI_RUNNER_NODE_NAME      host.name
#   SCCACHE_BIN              default /opt/ci-runner/bin/sccache
#   SCCACHE_SERVER_PORT      default 4226 (sccache's own default)
#   SCCACHE_REDIS_RW_MODE    reported as build.cache.sccache.rw_mode
#   CI_CACHE_EVENT_JSON      test override of the event.json path
set -u
kind="${1:-}"
[ -n "${kind}" ] || exit 0
shift

state_dir="${CI_CACHE_STATE_DIR:-/__w/_temp/_ci_cache}"
endpoint_file="${state_dir}/otlp_endpoint"
otlp_port="${CI_CACHE_OTLP_PORT:-4319}"
otlp_alias="${CI_CACHE_OTLP_ALIAS:-otlp-collector.ci-runner.internal}"
hosts_file="${CI_CACHE_HOSTS_FILE:-/etc/hosts}"
proc_net_route="${CI_CACHE_PROC_NET_ROUTE:-/proc/net/route}"

# The default route's gateway from the kernel's own table, for a job image
# that carries no iproute2 — `ip` is NOT guaranteed in a routed repository's
# `container:` image, and a derivation that needs it would fail exactly as
# silently as the address it replaces. Field 2 is the destination and field 3
# the gateway, both as LITTLE-ENDIAN hex words, so the dotted quad reads the
# byte pairs back to front.
gateway_from_proc_route() {
  [ -r "${proc_net_route}" ] || return 1
  gw_hex=$(awk 'NR > 1 && $2 == "00000000" && $3 != "00000000" { print $3; exit }' \
    "${proc_net_route}" 2>/dev/null || true)
  [ "${#gw_hex}" -eq 8 ] || return 1
  printf '%d.%d.%d.%d' \
    "0x$(printf '%s' "${gw_hex}" | cut -c7-8)" \
    "0x$(printf '%s' "${gw_hex}" | cut -c5-6)" \
    "0x$(printf '%s' "${gw_hex}" | cut -c3-4)" \
    "0x$(printf '%s' "${gw_hex}" | cut -c1-2)" 2>/dev/null
}

# `via` is required: a default route with no gateway (`default dev eth0 scope
# link`) has no address to post to, and its third field is an interface name.
default_gateway() {
  gw=$(ip -4 route show default 2>/dev/null | awk '$1 == "default" && $2 == "via" { print $3; exit }')
  [ -n "${gw}" ] || gw=$(ip route 2>/dev/null | awk '$1 == "default" && $2 == "via" { print $3; exit }')
  [ -n "${gw}" ] || gw=$(gateway_from_proc_route || true)
  # Dotted quad or nothing: a partial parse of the /proc fallback above would
  # otherwise publish a plausible, WRONG address, which is the failure shape
  # this whole derivation exists to end.
  case "${gw}" in
    0.0.0.0 | *[!0-9.]*) return 1 ;;
    *.*.*.*) ;;
    *) return 1 ;;
  esac
  printf '%s' "${gw}"
}

publish_endpoint() {
  gw=$(default_gateway) || {
    echo "ci-cache-span: no default route; telemetry endpoint unset for this pod" >&2
    return 0
  }
  published="http://${gw}:${otlp_port}"
  mkdir -p "${state_dir}" 2>/dev/null || true
  printf '%s' "${published}" > "${endpoint_file}" 2>/dev/null || true
  # Fail-soft, and REPORTED: a job image whose /etc/hosts is not writable keeps
  # its cache spans (they read the state file) and loses only the cargo shim's
  # build spans, which is worth a line in the pod's postStart log.
  if ! grep -qF " ${otlp_alias}" "${hosts_file}" 2>/dev/null; then
    printf '%s %s\n' "${gw}" "${otlp_alias}" >> "${hosts_file}" 2>/dev/null \
      || echo "ci-cache-span: cannot publish ${otlp_alias} in ${hosts_file}" >&2
  fi
  printf '%s\n' "${published}"
}

if [ "${kind}" = "publish-endpoint" ]; then
  publish_endpoint
  exit 0
fi

endpoint=""
[ -r "${endpoint_file}" ] && endpoint=$(cat "${endpoint_file}" 2>/dev/null || true)
[ -n "${endpoint}" ] || endpoint="${CI_CACHE_OTLP_ENDPOINT:-}"
[ -n "${endpoint}" ] || exit 0
CI_CACHE_OTLP_ENDPOINT="${endpoint}"
export CI_CACHE_OTLP_ENDPOINT
command -v python3 >/dev/null 2>&1 || exit 0
run() {
  if command -v timeout >/dev/null 2>&1; then
    timeout "${CI_CACHE_SPAN_TIMEOUT_S:-4}" python3 - "${kind}" "$@"
  else
    python3 - "${kind}" "$@"
  fi
}
run "$@" <<'PY' 2>/dev/null || true
import json, os, socket, subprocess, sys, time, urllib.request

KIND = sys.argv[1]
ARGS = sys.argv[2:]
ENDPOINT = os.environ["CI_CACHE_OTLP_ENDPOINT"].strip().rstrip("/")
STATE = os.environ.get("CI_CACHE_STATE_DIR") or "/__w/_temp/_ci_cache"
NOW_NS = time.time_ns()


def read_state(name):
    try:
        with open(os.path.join(STATE, name), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def event_facts():
    override = os.environ.get("CI_CACHE_EVENT_JSON")
    paths = (override,) if override else ("/github/workflow/event.json", "/__w/_temp/_github_workflow/event.json")
    ev = None
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                ev = json.load(f)
            break
        except (OSError, ValueError):
            ev = None
    if not isinstance(ev, dict):
        return "", "", "", "unknown"
    repo = str((ev.get("repository") or {}).get("full_name") or "")
    pr = ev.get("pull_request") or {}
    if pr:
        return repo, str((pr.get("head") or {}).get("sha") or ""), str((pr.get("head") or {}).get("ref") or ""), "pull_request"
    if "workflow_run" in ev:
        wr = ev["workflow_run"] or {}
        return repo, str(wr.get("head_sha") or ""), str(wr.get("head_branch") or ""), "workflow_run"
    ref = str(ev.get("ref") or "")
    branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
    sha = str(ev.get("after") or (ev.get("head_commit") or {}).get("id") or "")
    name = "push" if "after" in ev else ("schedule" if "schedule" in ev else ("workflow_dispatch" if "inputs" in ev else "unknown"))
    return repo, sha, branch, name


def attr(key, value):
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": str(value)}}


def generation_age_s(generation):
    # Generations are named %Y%m%dT%H%M%SZ by the populator; the name is the stamp.
    try:
        t = time.strptime(generation, "%Y%m%dT%H%M%SZ")
        import calendar
        return max(0, int(NOW_NS // 1_000_000_000) - calendar.timegm(t))
    except (TypeError, ValueError):
        return -1


def counter_total(value):
    if isinstance(value, int):
        return value
    if isinstance(value, dict) and isinstance(value.get("counts"), dict):
        return sum(int(n) for n in value["counts"].values())
    return 0


def sccache_summary():
    port = int(os.environ.get("SCCACHE_SERVER_PORT") or 4226)
    rw_mode = os.environ.get("SCCACHE_REDIS_RW_MODE") or ""
    off = [attr("build.cache.sccache.enabled", False), attr("build.cache.sccache.hits", 0),
           attr("build.cache.sccache.misses", 0), attr("build.cache.sccache.errors", 0),
           attr("build.cache.sccache.hit_ratio", 0.0), attr("build.cache.sccache.backend", "none"),
           attr("build.cache.sccache.rw_mode", rw_mode)]
    try:
        # Only ASK a server that is already running: `--show-stats` would START
        # one (and against a dead backend, sccache 0.17 fails to), and a job
        # that never ran cargo has no server and no cache to report.
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            pass
        out = subprocess.run([os.environ.get("SCCACHE_BIN") or "/opt/ci-runner/bin/sccache",
                              "--show-stats", "--stats-format=json"],
                             capture_output=True, text=True, timeout=3, check=False).stdout
        stats = json.loads(out)["stats"]
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return off
    hits = counter_total(stats.get("cache_hits"))
    misses = counter_total(stats.get("cache_misses"))
    errors = counter_total(stats.get("cache_errors"))
    total = hits + misses
    loc = str(stats.get("cache_location") or "")
    backend = "redis" if "redis" in loc.lower() else ("local" if "local" in loc.lower() else ("none" if not loc else "other"))
    return [attr("build.cache.sccache.enabled", True), attr("build.cache.sccache.hits", hits),
            attr("build.cache.sccache.misses", misses), attr("build.cache.sccache.errors", errors),
            attr("build.cache.sccache.hit_ratio", (hits / total) if total else 0.0),
            attr("build.cache.sccache.backend", backend), attr("build.cache.sccache.rw_mode", rw_mode)]


def span(name, attrs, start_ns, end_ns):
    return {"traceId": os.urandom(16).hex(), "spanId": os.urandom(8).hex(), "name": name, "kind": 1,
            "startTimeUnixNano": str(min(start_ns, end_ns)), "endTimeUnixNano": str(end_ns), "attributes": attrs}


def warm_copy_span(common, at_ns, tier, hit, generation, copy_ms, copy_bytes, copy_method, error):
    ms = int(copy_ms) if copy_ms.isdigit() else 0
    attrs = common + [attr("build.cache.tier", tier), attr("build.cache.hit", hit == "true"),
                      attr("build.cache.generation", generation),
                      attr("build.cache.generation_age_s", generation_age_s(generation)),
                      attr("build.cache.copy_ms", ms),
                      attr("build.cache.copy_bytes", int(copy_bytes) if copy_bytes.isdigit() else 0),
                      attr("build.cache.copy_method", copy_method), attr("build.cache.error", error)]
    # The tier's cost at start: from the hook's own start to the moment it was recorded.
    return span("cache.warm-copy", attrs, at_ns - ms * 1_000_000, at_ns)


def recorded_warm_copies(common):
    spans = []
    try:
        with open(os.path.join(STATE, "warm-copy.tsv"), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return spans
    for line in lines:
        cols = (line.split("\t") + [""] * 8)[:8]
        at = int(cols[0]) if cols[0].isdigit() else NOW_NS
        spans.append(warm_copy_span(common, at, *cols[1:8]))
    return spans


repo, sha, branch, event = event_facts()
common = [attr("repo", repo), attr("git.commit.sha", sha), attr("git.branch", branch), attr("ci.event", event),
          attr("build.env", "ci"), attr("build.cache.kill_switch", read_state("kill_switch")),
          attr("k8s.pod.name", os.environ.get("HOSTNAME") or "")]
started = read_state("started_at_ns")
start_ns = int(started) if started.isdigit() and int(started) > 0 else NOW_NS

if KIND == "warm-copy":
    spans = [warm_copy_span(common, NOW_NS, *(ARGS + [""] * 7)[:7])]
elif KIND == "job-summary":
    spans = [span("cache.job-summary", common + sccache_summary(), start_ns, NOW_NS)]
elif KIND == "job-end":
    spans = recorded_warm_copies(common) + [span("cache.job-summary", common + sccache_summary(), start_ns, NOW_NS)]
else:
    sys.exit(0)

payload = {"resourceSpans": [{
    "resource": {"attributes": [attr("service.name", "github-ci"),
                                attr("host.name", os.environ.get("CI_RUNNER_NODE_NAME") or "")]},
    "scopeSpans": [{"scope": {"name": "ci-cache-span"}, "spans": spans}]}]}
req = urllib.request.Request(ENDPOINT + "/v1/traces", data=json.dumps(payload).encode(),
                             headers={"content-type": "application/json"}, method="POST")
try:
    urllib.request.urlopen(req, timeout=2).read()
except Exception as exc:  # noqa: BLE001 — best-effort by contract; the job must never notice
    print(f"ci-cache-span: emit failed: {exc}", file=sys.stderr)
PY
exit 0
