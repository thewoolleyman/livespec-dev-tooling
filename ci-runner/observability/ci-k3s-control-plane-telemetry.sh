#!/usr/bin/env bash
# ci-k3s-control-plane-telemetry.sh — emit k3s API and kine datastore facts.
set -uo pipefail

KUBECTL_BIN="${CI_K3S_CONTROL_PLANE_KUBECTL:-kubectl}"
OTLP_ENDPOINT="${CI_K3S_CONTROL_PLANE_OTLP_ENDPOINT:-http://127.0.0.1:4319/v1/metrics}"
DATASTORE_PATH="${CI_K3S_CONTROL_PLANE_DATASTORE_PATH:-/var/lib/rancher/k3s/server/db}"
HOST_NAME="${CI_K3S_CONTROL_PLANE_HOST_NAME:-$(hostname)}"
REQUEST_TIMEOUT="${CI_K3S_CONTROL_PLANE_REQUEST_TIMEOUT:-15s}"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
readyz_raw="$work_dir/readyz"
metrics_raw="$work_dir/metrics"
payload="$work_dir/payload.json"

started_ns="$(date +%s%N)"
"$KUBECTL_BIN" --request-timeout="$REQUEST_TIMEOUT" get --raw='/readyz?verbose' >"$readyz_raw" 2>/dev/null
readyz_rc=$?
finished_ns="$(date +%s%N)"
latency_ns=$((finished_ns - started_ns))
"$KUBECTL_BIN" --request-timeout="$REQUEST_TIMEOUT" get --raw=/metrics >"$metrics_raw" 2>/dev/null
metrics_rc=$?
filesystem="$(df -B1 --output=used,size "$DATASTORE_PATH" 2>/dev/null | awk 'NR == 2 { print $1 " " $2 }')"
[ -n "$filesystem" ] || filesystem="0 0"

python3 - "$readyz_raw" "$metrics_raw" "$payload" "$HOST_NAME" "$readyz_rc" "$metrics_rc" "$latency_ns" "$filesystem" <<'PY'
import json
import re
import sys
import time
from collections import defaultdict

readyz_path, metrics_path, output_path, host, readyz_rc, metrics_rc, latency_ns, filesystem = sys.argv[1:]
now_ns = str(int(time.time() * 1_000_000_000))
def attrs(values): return [{"key": key, "value": {"stringValue": value}} for key, value in values.items()]
def gauge(name, unit, points): return {"name": name, "unit": unit, "gauge": {"dataPoints": points}}
def integer(value, labels=None):
    point = {"timeUnixNano": now_ns, "asInt": str(value)}
    if labels: point["attributes"] = attrs(labels)
    return point
def decimal(value, labels=None):
    point = {"timeUnixNano": now_ns, "asDouble": float(value)}
    if labels: point["attributes"] = attrs(labels)
    return point

readiness = []
if int(readyz_rc):
    readiness.append(integer(0, {"k8s.readiness_check": "api-server"}))
else:
    for line in open(readyz_path, encoding="utf-8"):
        match = re.match(r"^\[([+-])\]([^\s]+)", line)
        if match: readiness.append(integer(1 if match.group(1) == "+" else 0, {"k8s.readiness_check": match.group(2)}))
if not readiness: readiness.append(integer(0, {"k8s.readiness_check": "api-server"}))
metrics = [gauge("livespec.ci_k3s.readiness_check", "1", readiness), gauge("livespec.ci_k3s.readiness_latency_seconds", "s", [decimal(int(latency_ns) / 1_000_000_000)])]

if not int(metrics_rc):
    storage, series = [], defaultdict(lambda: {"buckets": [], "sum": None, "count": None, "labels": {}})
    pattern = re.compile(r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>[^}]*)\})?\s+(?P<value>[-+0-9.eE]+)$")
    label = re.compile(r'([^=,]+)="((?:\\\\.|[^"\\])*)"')
    for line in open(metrics_path, encoding="utf-8"):
        match = pattern.match(line.strip())
        if not match: continue
        name, raw, value = match.group("name"), match.group("labels") or "", float(match.group("value"))
        labels = {key: bytes(text, "utf-8").decode("unicode_escape") for key, text in label.findall(raw)}
        if name == "apiserver_storage_size_bytes": storage.append(decimal(value, labels)); continue
        suffix = next((item for item in ("_bucket", "_sum", "_count") if name == "etcd_request_duration_seconds" + item), None)
        if suffix is None: continue
        le = labels.pop("le", None); item = series[tuple(sorted(labels.items()))]; item["labels"] = labels
        if suffix == "_bucket" and le is not None: item["buckets"].append((le, int(value)))
        elif suffix == "_sum": item["sum"] = value
        elif suffix == "_count": item["count"] = int(value)
    if storage: metrics.append(gauge("apiserver_storage_size_bytes", "By", storage))
    points = []
    for item in series.values():
        if item["count"] is None: continue
        ordered = sorted(item["buckets"], key=lambda pair: float("inf") if pair[0] == "+Inf" else float(pair[0]))
        counts = [count for _bound, count in ordered]
        point = {"timeUnixNano": now_ns, "count": str(item["count"]), "sum": item["sum"] or 0.0, "bucketCounts": [str(value - (counts[index - 1] if index else 0)) for index, value in enumerate(counts)], "explicitBounds": [float(bound) for bound, _value in ordered if bound != "+Inf"]}
        if item["labels"]: point["attributes"] = attrs(item["labels"])
        points.append(point)
    if points: metrics.append({"name": "etcd_request_duration_seconds", "unit": "s", "histogram": {"aggregationTemporality": 2, "dataPoints": points}})

used, total = filesystem.split()
metrics.extend([gauge("livespec.ci_k3s.datastore_used_bytes", "By", [integer(used)]), gauge("livespec.ci_k3s.datastore_total_bytes", "By", [integer(total)])])
document = {"resourceMetrics": [{"resource": {"attributes": attrs({"service.name": "ci-k3s-control-plane", "host.name": host})}, "scopeMetrics": [{"scope": {"name": "ci-k3s-control-plane-telemetry"}, "metrics": metrics}]}]}
json.dump(document, open(output_path, "w", encoding="utf-8"))
PY

curl --silent --show-error --fail --max-time 5 -X POST "$OTLP_ENDPOINT" -H 'Content-Type: application/json' --data-binary "@$payload"
