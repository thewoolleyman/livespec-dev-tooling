#!/usr/bin/env bash
# ci-k3s-control-plane-gauges.sh — report k3s API readiness and the kine
# datastore's host filesystem through the local OTLP collector.
#
# The API-server calls intentionally use the collector ServiceAccount's
# read-only kubeconfig.  `etcd_request_duration_seconds` is an API-server
# `/metrics` series whose historical name reflects the API protocol; this host
# runs kine over SQLite and this emitter never contacts an etcd process, leader,
# WAL, or endpoint.
set -uo pipefail

OTLP_ENDPOINT="${CI_CONTROL_PLANE_OTLP:-http://127.0.0.1:4319/v1/metrics}"
KUBECONFIG_PATH="${CI_CONTROL_PLANE_KUBECONFIG:-${KUBECONFIG:-/etc/otel-collector/kubeconfig}}"
KUBECTL_BIN="${CI_CONTROL_PLANE_KUBECTL:-kubectl}"
CURL_BIN="${CI_CONTROL_PLANE_CURL:-curl}"
DF_BIN="${CI_CONTROL_PLANE_DF:-df}"
DB_PATH="${CI_CONTROL_PLANE_DB_PATH:-/var/lib/rancher/k3s/server/db}"
HOST_NAME="${CI_CONTROL_PLANE_HOST_NAME:-$(hostname)}"
REQUEST_TIMEOUT="${CI_CONTROL_PLANE_REQUEST_TIMEOUT:-15s}"

now_ns() {
  if [ -n "${CI_CONTROL_PLANE_NOW_NANO:-}" ]; then
    printf '%s\n' "${CI_CONTROL_PLANE_NOW_NANO}"
  else
    date +%s%N
  fi
}

readyz_file="$(mktemp)"
metrics_file="$(mktemp)"
trap 'rm -f "${readyz_file}" "${metrics_file}"' EXIT

started_ns="$(now_ns)"
readyz_ok=1
if ! "${KUBECTL_BIN}" --kubeconfig "${KUBECONFIG_PATH}" \
    --request-timeout="${REQUEST_TIMEOUT}" get --raw='/readyz?verbose' >"${readyz_file}" 2>&1; then
  readyz_ok=0
fi
finished_ns="$(now_ns)"

metrics_ok=1
if [ "${readyz_ok}" -eq 1 ]; then
  if ! "${KUBECTL_BIN}" --kubeconfig "${KUBECONFIG_PATH}" \
      --request-timeout="${REQUEST_TIMEOUT}" get --raw=/metrics >"${metrics_file}" 2>&1; then
    metrics_ok=0
  fi
else
  metrics_ok=0
fi

datastore_total=""
datastore_used=""
if df_row="$("${DF_BIN}" -B1 --output=size,used,target "${DB_PATH}" 2>/dev/null | awk 'NR == 2 { if ($1 ~ /^[0-9]+$/) print $1, $2; else print $2, $3 }')"; then
  read -r datastore_total datastore_used <<< "${df_row}"
fi

payload="$(python3 - "${readyz_file}" "${metrics_file}" "${readyz_ok}" "${started_ns}" "${finished_ns}" "${HOST_NAME}" "${DB_PATH}" "${datastore_used}" "${datastore_total}" <<'PY'
import json
import re
import sys

(
    readyz_path,
    metrics_path,
    readyz_ok,
    started_ns,
    finished_ns,
    host_name,
    db_path,
    datastore_used,
    datastore_total,
) = sys.argv[1:]

READY_CHECK = re.compile(r"^\[([+-])\]([^\s]+)")
SAMPLE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*)\})?\s+([^\s]+)")
LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')


def attributes(values):
    return [
        {"key": key, "value": {"stringValue": value}}
        for key, value in sorted(values.items())
    ]


def point(*, integer=None, floating=None, labels=None):
    result = {"timeUnixNano": finished_ns}
    if integer is not None:
        result["asInt"] = str(integer)
    if floating is not None:
        result["asDouble"] = floating
    if labels:
        result["attributes"] = attributes(labels)
    return result


with open(readyz_path, encoding="utf-8", errors="replace") as handle:
    checks = [(match.group(2), match.group(1) == "+") for line in handle if (match := READY_CHECK.match(line))]
if not checks:
    checks = [("apiserver", readyz_ok == "1")]

readiness_points = [
    point(integer=1 if passed else 0, labels={"k8s.readiness_check": name})
    for name, passed in checks
]
latency = max(0, int(finished_ns) - int(started_ns)) / 1_000_000_000
metrics = [
    {
        "name": "livespec.k3s.apiserver_readiness",
        "description": "One pass-or-fail datapoint for each API server /readyz check",
        "unit": "{check}",
        "gauge": {"dataPoints": readiness_points},
    },
    {
        "name": "livespec.k3s.apiserver_readyz_latency_seconds",
        "description": "Latency of the API server /readyz?verbose probe",
        "unit": "s",
        "gauge": {"dataPoints": [point(floating=latency)]},
    },
]

storage_points = []
histograms = {}
with open(metrics_path, encoding="utf-8", errors="replace") as handle:
    for raw in handle:
        match = SAMPLE.match(raw)
        if match is None:
            continue
        name, raw_labels, raw_value = match.groups()
        try:
            value = float(raw_value)
        except ValueError:
            continue
        labels = {key: json.loads(f'"{value}"') for key, value in LABEL.findall(raw_labels or "")}
        if name == "apiserver_storage_size_bytes":
            storage_points.append(point(floating=value, labels=labels))
            continue
        if not name.startswith("etcd_request_duration_seconds_"):
            continue
        metric_labels = {key: value for key, value in labels.items() if key != "le"}
        key = tuple(sorted(metric_labels.items()))
        state = histograms.setdefault(key, {"labels": metric_labels, "buckets": {}, "sum": None, "count": None})
        if name.endswith("_bucket"):
            state["buckets"][labels.get("le", "+Inf")] = value
        elif name.endswith("_sum"):
            state["sum"] = value
        elif name.endswith("_count"):
            state["count"] = int(value)

if storage_points:
    metrics.append(
        {
            "name": "apiserver_storage_size_bytes",
            "description": "API server storage size as served by /metrics",
            "unit": "By",
            "gauge": {"dataPoints": storage_points},
        }
    )

histogram_points = []
for state in histograms.values():
    if state["sum"] is None or state["count"] is None or "+Inf" not in state["buckets"]:
        continue
    finite = sorted((float(bound), count) for bound, count in state["buckets"].items() if bound != "+Inf")
    previous = 0
    bucket_counts = []
    bounds = []
    for bound, count in finite:
        bucket_counts.append(str(max(0, int(count) - previous)))
        previous = int(count)
        bounds.append(bound)
    bucket_counts.append(str(max(0, int(state["buckets"]["+Inf"]) - previous)))
    histogram_points.append(
        {
            "timeUnixNano": finished_ns,
            "count": str(state["count"]),
            "sum": state["sum"],
            "explicitBounds": bounds,
            "bucketCounts": bucket_counts,
            "attributes": attributes(state["labels"]),
        }
    )
if histogram_points:
    metrics.append(
        {
            "name": "etcd_request_duration_seconds",
            "description": "API-server /metrics histogram; kine does not add an etcd process probe",
            "unit": "s",
            "histogram": {"aggregationTemporality": 2, "dataPoints": histogram_points},
        }
    )

for name, value in (
    ("livespec.k3s.kine_datastore_filesystem_used_bytes", datastore_used),
    ("livespec.k3s.kine_datastore_filesystem_total_bytes", datastore_total),
):
    if value.isdigit():
        metrics.append(
            {
                "name": name,
                "description": "Bytes on the filesystem holding the kine SQLite datastore",
                "unit": "By",
                "gauge": {
                    "dataPoints": [
                        point(integer=int(value), labels={"filesystem.mount": db_path, "k8s.datastore": "kine"})
                    ]
                },
            }
        )

print(
    json.dumps(
        {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": attributes({"host.name": host_name, "service.name": "ci-k3s-control-plane"})
                    },
                    "scopeMetrics": [{"scope": {"name": "ci-k3s-control-plane-gauges"}, "metrics": metrics}],
                }
            ]
        }
    )
)
PY
)" || exit 1

"${CURL_BIN}" --silent --show-error --fail --max-time 10 \
  -X POST "${OTLP_ENDPOINT}" -H 'Content-Type: application/json' -d "${payload}" > /dev/null || exit 1

if [ "${readyz_ok}" -ne 1 ] || [ "${metrics_ok}" -ne 1 ]; then
  echo "ci-k3s-control-plane-gauges: API server read failed; emitted readiness failure and probe latency" >&2
  exit 1
fi

echo "ci-k3s-control-plane-gauges: emitted API readiness, API metrics, and kine datastore filesystem metrics"
