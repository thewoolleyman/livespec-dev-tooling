#!/usr/bin/env bash
# apply-disruption-columns.sh — converge the throughput board's CONFOUND
# columns in the `livespec` Honeycomb environment from the committed quiet
# record, disruption-windows.json, beside this script.
#
# WHY THIS EXISTS. On 2026-11-15 Honeycomb's Canvas agent, shown only the
# "livespec throughput" board, read lead time as getting worse and PR CI as
# "roughly doubled across the fleet". Both readings came from confounds the
# terminal headline prints and the board did not show: pull requests HELD
# through merge-quiet windows (and slowed by the 2026-11-13/14 CI pool stall)
# carry the hold inside their stage and lead-time figures, and M2's start rule
# changed on 2026-11-14. The maintainer: "if an LLM cannot understand this
# board and it is in Honeycomb itself, then that indicates a problem with the
# board." So the confounds are made part of the DATA the board's queries
# return, not prose a reader must remember:
#
#   pr.disruption  "clean", or which window held or slowed this pull request:
#                  its life (opened_at to merged_at) overlaps a window for its
#                  repository. A merge-quiet window outranks the fleet stall.
#   pr.lead_rule   "new start rule" when the event carries pr.start_rule, else
#                  "old start rule (not comparable)".
#
# The board's M2 and M3 charts FILTER to clean (and M2 to the new rule), and one
# table counts what they leave out. They never break down by these columns: a held
# line is orders of magnitude above the clean one and flattens it
# (.ai/honeycomb-board-charts.md).
#
# WHY DERIVED COLUMNS AND NOT MARKERS. A derived column is computed at query
# time, so a window added to the record relabels every past event with no
# re-emission, whichever emitter wrote it (the stopgap or the reconciler,
# livespec-dev-tooling-gaetnq). The configuration key can manage columns but
# NOT markers (measured 2026-11-15 at /1/auth: markers false).
#
# Modes:
#   (none)      converge: create a missing column, update one whose expression
#               or description differs, leave a matching one untouched.
#   --drift     READ-ONLY: print `differs <alias>` / `missing <alias>` and exit
#               non-zero when the live columns are not what the record makes.
#   --markdown  print the record as the Markdown the board's confound panel
#               carries (apply-boards.sh substitutes it for {{disruption-windows}}).
#   --expressions  print the generated columns as JSON; no network.
#
# Requires HONEYCOMB_CONFIG_KEY_LIVESPEC for converge and drift:
#   /usr/local/bin/with-livespec-env.sh -- ./apply-disruption-columns.sh
set -euo pipefail

MODE=apply
case "${1:-}" in
  "") ;;
  --drift) MODE=drift ;;
  --markdown) MODE=markdown ;;
  --expressions) MODE=expressions ;;
  *) echo "usage: apply-disruption-columns.sh [--drift|--markdown|--expressions]" >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECORD="${DISRUPTION_RECORD:-${SCRIPT_DIR}/disruption-windows.json}"
export HONEYCOMB_API="${HONEYCOMB_API:-https://api.honeycomb.io}"
if [ "${MODE}" = apply ] || [ "${MODE}" = drift ]; then
  : "${HONEYCOMB_CONFIG_KEY_LIVESPEC:?run through /usr/local/bin/with-livespec-env.sh -- (projects the livespec configuration key)}"
fi

exec python3 - "${RECORD}" "${MODE}" <<'PY'
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

RECORD, MODE = sys.argv[1], sys.argv[2]
CLEAN = "clean"
KINDS = {"merge-quiet": "held", "ci-pool-stall": "slowed"}


def epoch(stamp):
    return int(datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp())


def load():
    with open(RECORD, encoding="utf-8") as handle:
        record = json.load(handle)
    problems, seen = [], set()
    for window in record.get("windows", []):
        wid = window.get("id", "<no id>")
        if wid in seen:
            problems.append("window id %s is used twice" % wid)
        seen.add(wid)
        if window.get("kind") not in KINDS:
            problems.append("window %s kind must be one of %s" % (wid, ", ".join(KINDS)))
        if not window.get("repos"):
            problems.append("window %s names no repos" % wid)
        try:
            if epoch(window["start"]) >= epoch(window["end"]):
                problems.append("window %s ends before it starts" % wid)
        except (KeyError, ValueError):
            problems.append("window %s needs start and end as YYYY-MM-DDTHH:MM:SSZ" % wid)
        if '"' in window.get("label", '"'):
            problems.append("window %s needs a label without double quotes" % wid)
    if problems:
        for problem in problems:
            print("REFUSED %s: %s" % (RECORD, problem), file=sys.stderr)
        sys.exit(1)
    return record


def window_value(window):
    return "%s: %s" % (KINDS[window["kind"]], window["label"])


def window_condition(window):
    overlap = "LT(UNIX_TIMESTAMP($pr.opened_at), %d), GT(UNIX_TIMESTAMP($pr.merged_at), %d)" % (
        epoch(window["end"]),
        epoch(window["start"]),
    )
    if window["repos"] == ["*"]:
        return "AND(%s)" % overlap
    repos = ", ".join('"%s"' % repo for repo in window["repos"])
    return "AND(IN($repo, %s), %s)" % (repos, overlap)


def columns(record):
    """The derived columns the record makes: [{alias, expression, description}]."""
    windows = record.get("windows", [])
    # A merge-quiet window outranks the fleet stall; within a kind, the latest first.
    ordered = sorted(windows, key=lambda w: (w["kind"] != "merge-quiet", -epoch(w["start"])))
    expression = '"%s"' % CLEAN
    for window in reversed(ordered):
        expression = 'IF(%s, "%s", %s)' % (window_condition(window), window_value(window), expression)
    rule = record["start_rule_change"]
    return [
        {
            "alias": "pr.disruption",
            "expression": expression,
            "description": "clean, or the merge-quiet window (held) or CI pool stall (slowed) this PR's open-to-merge life overlaps. Generated from ci-runner/observability/throughput/disruption-windows.json by apply-disruption-columns.sh; never edit by hand.",
        },
        {
            "alias": "pr.lead_rule",
            "expression": 'IF(EXISTS($%s), "%s", "%s")' % (rule["field"], rule["new_label"], rule["old_label"]),
            "description": "new start rule when the event carries %s (start = first-commit author time or factory run marker, from %s), else old start rule: lead times across the two are not comparable. Generated by apply-disruption-columns.sh." % (rule["field"], rule["at"]),
        },
    ]


def markdown(record):
    lines = [
        "**These windows are left out of every M2 and M3 chart** (the charts filter to `pr.disruption` = clean) and are "
        "counted in the EXCLUDED table instead. A pull request whose life (opened to merged) overlaps one of them carries "
        "the hold inside its stage and lead-time minutes, so its minutes measure the window, not CI speed:",
        "",
    ]
    for window in sorted(record.get("windows", []), key=lambda w: w["start"]):
        scope = "every repository" if window["repos"] == ["*"] else ", ".join(window["repos"])
        lines.append(
            "- **%s** — %s to %s UTC, %s." % (window_value(window), window["start"][5:16].replace("T", " "),
                                            window["end"][5:16].replace("T", " "), scope)
        )
    rule = record["start_rule_change"]
    lines += [
        "",
        "**Lead-time start rule changed %s.** The M2 charts show only **%s** events; **%s** events are counted in the "
        "EXCLUDED table. %s" % (rule["at"], rule["new_label"], rule["old_label"], rule["text"]),
    ]
    return "\n".join(lines)


def call(method, path, body=None):
    if MODE == "drift" and method != "GET":
        raise RuntimeError("drift mode is read-only; refusing %s %s" % (method, path))
    req = urllib.request.Request(os.environ["HONEYCOMB_API"] + path, method=method)
    req.add_header("X-Honeycomb-Team", os.environ["HONEYCOMB_CONFIG_KEY_LIVESPEC"])
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        return resp.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")[:400]
    except OSError as exc:
        return 0, str(exc)


def converge(record):
    dataset = record["dataset"]
    rc = 0
    for column in columns(record):
        status, live = call("GET", "/1/derived_columns/%s?alias=%s" % (dataset, urllib.parse.quote(column["alias"])))
        if status == 404:
            live = None
        elif status != 200:
            print("FAILED read %s: %s %s" % (column["alias"], status, live), file=sys.stderr)
            rc = 1
            continue
        same = live and live.get("expression") == column["expression"] and live.get("description") == column["description"]
        if MODE == "drift":
            if not live:
                print("missing %s" % column["alias"])
                rc = 1
            elif not same:
                print("differs %s" % column["alias"])
                rc = 1
            continue
        if same:
            print("unchanged %s %s" % (live["id"], column["alias"]))
            continue
        if live:
            status, out = call("PUT", "/1/derived_columns/%s/%s" % (dataset, live["id"]), column)
            verb = "updated"
        else:
            status, out = call("POST", "/1/derived_columns/%s" % dataset, column)
            verb = "created"
        if status not in (200, 201):
            print("FAILED %s %s: %s %s" % (verb, column["alias"], status, out), file=sys.stderr)
            rc = 1
            continue
        print("%s %s %s" % (verb, (out or {}).get("id", ""), column["alias"]))
    return rc


record = load()
if MODE == "markdown":
    print(markdown(record))
    sys.exit(0)
if MODE == "expressions":
    print(json.dumps(columns(record), indent=2))
    sys.exit(0)
sys.exit(converge(record))
PY
