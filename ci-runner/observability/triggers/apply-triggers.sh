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
#
# DRIFT MODE. `apply-triggers.sh --drift` is READ-ONLY: for every definition
# beside this script it GETs the live trigger of the same name and prints the
# name and each field that differs (`differs <name>` then one `  <field>:
# committed … live …` line per field), or `missing <name>` when no live trigger
# carries the name. It sends no create or update request — every call it makes
# is a GET — and exits non-zero when it reports any difference or missing
# definition, zero when every definition matches. The comparison is a SUBSET
# one: only what the committed definition states is compared, so what the
# service assigns (id, timestamps, defaults it fills in, a recipient's type and
# target) is left out by construction. A definition edited by hand is thereby
# reported BEFORE the next apply overwrites it.
set -euo pipefail

MODE=apply
case "${1:-}" in
  "") ;;
  --drift) MODE=drift ;;
  *) echo "usage: apply-triggers.sh [--drift]" >&2; exit 2 ;;
esac

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
  # Honeycomb caps a trigger name at 120 characters and its description at
  # 1023; the API answers 400 with a one-line error and this loop then
  # reports the definition as FAILED at the end. Refuse here, by name,
  # before the call (both caps were hit on 2026-09-06).
  if ! python3 - "${def}" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
bad = []
if len(d.get("name", "")) > 120:
    bad.append(f"name is {len(d['name'])} chars (max 120)")
if len(d.get("description", "")) > 1023:
    bad.append(f"description is {len(d['description'])} chars (max 1023)")
if bad:
    print(f"REFUSED {sys.argv[1]}: " + "; ".join(bad), file=sys.stderr)
    sys.exit(1)
PY
  then
    rc=1
    continue
  fi
  dataset="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("dataset") or sys.argv[2])' "${def}" "${DATASET}")"
  if [ "${MODE}" = drift ]; then
    # Read-only: the list and the one live trigger are fetched with GET, and no
    # branch of this arm reaches the POST/PUT calls below.
    existing="$(hc -X GET "${API}/1/triggers/${dataset}")"
    id="$(printf '%s' "${existing}" | python3 -c 'import json,sys; n=sys.argv[1]; print(next((t["id"] for t in json.load(sys.stdin) if t["name"]==n), ""))' "${name}")"
    if [ -z "${id}" ]; then
      echo "missing [${dataset}] ${name}"
      rc=1
      continue
    fi
    if ! live="$(hc -X GET "${API}/1/triggers/${dataset}/${id}")"; then
      echo "FAILED read ${name}: ${live}" >&2; rc=1
      continue
    fi
    printf '%s' "${live}" > "${body}"
    if ! python3 - "${def}" "${name}" "${body}" <<'PY'
import json, sys

ABSENT = "<absent>"


def identity(items):
    """Per-element identity (id, else key) when every element has a distinct one."""
    keys = []
    for item in items:
        if not isinstance(item, dict) or not (item.get("id") or item.get("key")):
            return None
        keys.append(item.get("id") or item.get("key"))
    return keys if len(set(keys)) == len(keys) else None


def diff(path, want, have, out):
    """Append one line per field where the committed `want` is not what `have` holds."""
    if isinstance(want, dict):
        if not isinstance(have, dict):
            out.append("  %s: committed %s live %s" % (path, json.dumps(want), json.dumps(have)))
            return
        for key, value in want.items():
            diff("%s.%s" % (path, key) if path else key, value, have.get(key, ABSENT), out)
    elif isinstance(want, list):
        if not isinstance(have, list):
            out.append("  %s: committed %s live %s" % (path, json.dumps(want), json.dumps(have)))
            return
        want_ids, have_ids = identity(want), identity(have)
        if want_ids is not None and have_ids is not None:
            by_id = dict(zip(have_ids, have))
            for key, item in zip(want_ids, want):
                diff("%s[%s]" % (path, key), item, by_id.get(key, ABSENT), out)
            for key in have_ids:
                if key not in want_ids:
                    out.append("  %s[%s]: committed %s live %s" % (path, key, ABSENT, json.dumps(by_id[key])))
        elif len(want) != len(have):
            out.append("  %s: committed %s live %s" % (path, json.dumps(want), json.dumps(have)))
        else:
            for index, (item, held) in enumerate(zip(want, have)):
                diff("%s[%d]" % (path, index), item, held, out)
    elif want != have:
        out.append("  %s: committed %s live %s" % (path, json.dumps(want), json.dumps(have)))


committed = json.load(open(sys.argv[1]))
committed.pop("dataset", None)
lines = []
diff("", committed, json.load(open(sys.argv[3])), lines)
if lines:
    print("differs %s" % sys.argv[2])
    print("\n".join(lines))
    sys.exit(1)
PY
    then
      rc=1
    fi
    continue
  fi
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
