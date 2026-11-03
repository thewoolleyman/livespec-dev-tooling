#!/usr/bin/env bash
# Emit the kernel's complete host PSI surface to Honeycomb's OTLP Metrics API.
#
# The OTLP endpoint is direct by design.  Every target already receives
# HONEYCOMB_INGEST_KEY_LIVESPEC through the otel_collector role, whereas adding
# a receiver to the separately owned collector repository would make this
# emitter depend on a second repository's deploy cycle.
set -euo pipefail

OTLP_ENDPOINT="${PRESSURE_TELEMETRY_OTLP_ENDPOINT:-https://api.honeycomb.io/v1/metrics}"
: "${HONEYCOMB_INGEST_KEY_LIVESPEC:?pressure telemetry requires HONEYCOMB_INGEST_KEY_LIVESPEC}"

host_name="$(hostname -s)"
if [[ ! "${host_name}" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]]; then
  echo "pressure telemetry: hostname '${host_name}' cannot be represented safely in OTLP JSON" >&2
  exit 1
fi

read_psi_line() {
  # $1 is a readable PSI file and $2 is either `some` or `full`.  Do not turn
  # an absent field into zero: a false zero is indistinguishable from a healthy
  # host and silently erases the reason the telemetry exists.
  local pressure_file="$1" line="$2" values
  if ! values="$(awk -v expected_line="${line}" '
    $1 == expected_line {
      found = 1
      for (i = 2; i <= NF; i++) {
        split($i, pair, "=")
        value[pair[1]] = pair[2]
      }
      for (field in required) {
        if (!(field in value) || value[field] !~ /^[0-9]+([.][0-9]+)?$/) {
          invalid = 1
        }
      }
      if (!invalid) {
        print value["avg10"], value["avg60"], value["avg300"]
      }
    }
    BEGIN {
      required["avg10"] = 1
      required["avg60"] = 1
      required["avg300"] = 1
    }
    END { exit (!found || invalid) }
  ' "${pressure_file}")"; then
    echo "pressure telemetry: no usable '${line}' avg10/avg60/avg300 line in ${pressure_file}" >&2
    return 1
  fi
  printf '%s\n' "${values}"
}

metrics=""
append_metric() {
  local resource="$1" line="$2" field="$3" value="$4" separator=""
  if [[ -n "${metrics}" ]]; then
    separator=","
  fi
  metrics+="${separator}
            {
              \"name\": \"livespec.host.pressure.${resource}.${line}.${field}\",
              \"description\": \"Host PSI ${resource} ${line} ${field} percentage\",
              \"unit\": \"%\",
              \"gauge\": {
                \"dataPoints\": [
                  { \"asDouble\": ${value}, \"timeUnixNano\": \"${now_ns}\" }
                ]
              }
            }"
}

now_ns="$(date +%s%N)"
declare -Ar PRESSURE_FILES=(
  [cpu]=/proc/pressure/cpu
  [memory]=/proc/pressure/memory
  [io]=/proc/pressure/io
)
for resource in cpu memory io; do
  pressure_file="${PRESSURE_FILES[${resource}]}"
  if [[ ! -r "${pressure_file}" ]]; then
    # Build and send one request only after ALL resources pass validation.  A
    # missing file therefore sends no datapoint for this resource (or a partial
    # batch that could look like a complete sampling pass).
    echo "pressure telemetry: missing pressure file ${pressure_file}; refusing to emit ${resource}" >&2
    exit 1
  fi
  for line in some full; do
    read -r avg10 avg60 avg300 <<< "$(read_psi_line "${pressure_file}" "${line}")"
    append_metric "${resource}" "${line}" avg10 "${avg10}"
    append_metric "${resource}" "${line}" avg60 "${avg60}"
    append_metric "${resource}" "${line}" avg300 "${avg300}"
  done
done

payload="$(cat <<JSON
{
  "resourceMetrics": [
    {
      "resource": {
        "attributes": [
          { "key": "service.name", "value": { "stringValue": "livespec-pressure-telemetry" } },
          { "key": "host.name", "value": { "stringValue": "${host_name}" } }
        ]
      },
      "scopeMetrics": [
        {
          "scope": { "name": "livespec-pressure-telemetry" },
          "metrics": [${metrics}
          ]
        }
      ]
    }
  ]
}
JSON
)"

curl --silent --show-error --fail --max-time 10 \
  -X POST "${OTLP_ENDPOINT}" \
  -H 'Content-Type: application/json' \
  -H "X-Honeycomb-Team: ${HONEYCOMB_INGEST_KEY_LIVESPEC}" \
  -d "${payload}" > /dev/null

echo "pressure telemetry: emitted cpu, memory, and io PSI some/full avg10/avg60/avg300 for host.name=${host_name}" >&2
