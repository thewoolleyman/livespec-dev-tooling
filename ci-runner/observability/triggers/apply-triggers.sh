#!/usr/bin/env bash
# apply-triggers.sh — converge the CI cache triggers in the `livespec`
# Honeycomb environment from every *.json definition beside this
# script: create a trigger whose name is absent, update one whose name exists.
# Idempotent by NAME, so a re-run after editing a definition updates in
# place and the trigger id (what the plan store records) is stable.
#
# The definitions are the fleet's trigger shape (see the eleven existing
# livespec triggers): ungrouped, filtered to one host, a runbook plus the
# emitter path, receiver path and work item in the description, tags
# host/service/kind/component. The dataset defaults to `metrics` (Honeycomb's
# environment-level Metrics dataset, where the host collector lands every
# livespec.ci_*.* gauge); a definition may name another with a top-level
# "dataset" key (the negative-tests trigger reads `github-ci`), which this
# script strips before the API call.
#
# Requires: HONEYCOMB_CONFIG_KEY_LIVESPEC (a configuration key for the
# livespec environment) — projected by the fleet's credential wrapper:
#   /usr/local/bin/with-livespec-env.sh -- ./apply-triggers.sh
# plus curl and python3. Prints one line per trigger: created|updated id name.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API="${HONEYCOMB_API:-https://api.honeycomb.io}"
DATASET="${HONEYCOMB_TRIGGER_DATASET:-metrics}"
: "${HONEYCOMB_CONFIG_KEY_LIVESPEC:?run through /usr/local/bin/with-livespec-env.sh -- (projects the livespec configuration key)}"

hc() { curl --silent --show-error --fail-with-body --max-time 30 -H "X-Honeycomb-Team: ${HONEYCOMB_CONFIG_KEY_LIVESPEC}" -H 'Content-Type: application/json' "$@"; }

# Every definition is attempted; a failure (typically Honeycomb refusing a
# column that no datapoint has created yet — a gauge emitted only under
# traffic) is reported and the script exits non-zero at the END, so one bad
# definition never blocks the others.
rc=0
body="$(mktemp)"
trap 'rm -f "${body}"' EXIT
for def in "${SCRIPT_DIR}"/*.json; do
  name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "${def}")"
  dataset="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("dataset") or sys.argv[2])' "${def}" "${DATASET}")"
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d.pop("dataset", None); json.dump(d, open(sys.argv[2], "w"))' "${def}" "${body}"
  existing="$(hc "${API}/1/triggers/${dataset}")"
  id="$(printf '%s' "${existing}" | python3 -c 'import json,sys; n=sys.argv[1]; print(next((t["id"] for t in json.load(sys.stdin) if t["name"]==n), ""))' "${name}")"
  if [ -n "${id}" ]; then
    if out="$(hc -X PUT "${API}/1/triggers/${dataset}/${id}" --data-binary "@${body}")"; then
      echo "updated ${id} [${dataset}] ${name}"
    else
      echo "FAILED update ${name}: ${out}" >&2; rc=1
    fi
  else
    if out="$(hc -X POST "${API}/1/triggers/${dataset}" --data-binary "@${body}")"; then
      echo "created $(printf '%s' "${out}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])') [${dataset}] ${name}"
    else
      echo "FAILED create ${name}: ${out}" >&2; rc=1
    fi
  fi
done
exit "${rc}"
