#!/usr/bin/env bash
# apply-boards.sh — converge the CI runner-pool BOARDS in the `livespec`
# Honeycomb environment from every *.json definition beside this script:
# create a board whose name is absent, update one whose name exists.
# Idempotent by NAME, exactly as ../triggers/apply-triggers.sh is, so a
# re-run after editing a definition updates in place and the board id (what
# the plan store records, and what the board's URL embeds) is stable.
#
# WHY A BOARD NEEDS MORE STEPS THAN A TRIGGER. A trigger carries its query
# INLINE, so applying one is a single POST or PUT. A Honeycomb board panel
# does not: `query_panel` references a saved query by `query_id` and a saved
# Query Annotation by `query_annotation_id` (both REQUIRED; `dataset` on the
# panel is read-only and follows the query). So each panel is a three-step
# convergence — resolve or create the query, resolve or create its
# annotation, then reference both from the board. That is more logic than
# the trigger applier's `python3 -c` one-liners carry comfortably, so the
# convergence is ONE embedded python3 program below rather than a chain of
# them; the bash around it is argument, credential and file handling.
#
# HOW A RE-RUN IS A NO-OP. Queries are immutable and an annotation's
# `query_id` cannot be changed, so a naive applier would mint a fresh query
# and annotation on every run and the board would churn ids forever. Instead
# each panel is matched to the LIVE board's existing panel by its annotation
# NAME; the stored query behind it is fetched and compared against the
# definition's spec key by key (a SUBSET comparison, because the API fills
# in defaults such as filter_combination and granularity that the definition
# does not state). A match reuses both ids and the applied board is
# byte-identical to the live one. Only a genuine definition edit mints a new
# query; the superseded annotation is left in place rather than deleted,
# which is how Honeycomb's own board-created annotations behave.
#
# THE DEFINITIONS SPAN TWO DATASETS, AND THAT IS THE POINT. The `livespec`
# environment is a Honeycomb "Metrics 2.0" environment, so EVERY OTLP metric
# lands in its single `metrics` dataset and an x-honeycomb-dataset header is
# ignored there (measured 2026-08-23). Gauge panels therefore name
# `"dataset": "metrics"` and are told apart by metric name plus host.name.
# The running-jobs panel reads WIDE EVENTS, which auto-route by
# `service.name`, so it names `"dataset": "ci-runner-pool"`. Each panel
# carries its own `dataset` key for this reason; there is no board-wide
# default to inherit.
#
# A PANEL WHOSE COLUMNS DO NOT EXIST YET IS SKIPPED, NOT FATAL. Honeycomb
# creates a dataset on its first datapoint and a column on its first value,
# so a panel can name a column — or a whole dataset — that no emitter has
# created yet. The sibling trigger applier already meets this ("Honeycomb
# refusing a column that no datapoint has created yet"). This script applies
# the same discipline PER PANEL: a query or annotation the API refuses is
# reported, its panel is dropped from this apply, the remaining panels are
# applied, and the script exits non-zero at the END so the incompleteness is
# visible. Re-running after the emitter's host apply completes the board
# with no edit to the definition.
#
# Requires: HONEYCOMB_CONFIG_KEY_LIVESPEC (a Configuration key for the
# livespec environment). It needs exactly TWO UI permissions, and which two is
# easy to get wrong: "Public Boards" (the `boards` field) and "Queries and
# columns" (the `columns` field). MEASURED 2026-09-08 at /1/auth, after the key
# was widened: boards true, columns true, queries FALSE — and the board applies
# anyway.
#
# THAT LAST PART IS THE NON-OBVIOUS BIT, so it is recorded rather than
# rediscovered. This script POSTs to /1/queries/<dataset> and
# /1/query_annotations/<dataset> before it ever touches /1/boards, which makes
# it look gated on a `queries` permission. It is not. CREATING a saved query
# object is covered by "Queries and columns"; the separate `queries` field is
# the query-EXECUTION API, whose UI control ("Run queries") is greyed out as
# enterprise-only on this account. So a board applies on a plan that can never
# run a query through the API.
#
# THE CONSEQUENCE FOR ACCEPTANCE, since it outlives this script: nothing in the
# fleet can execute a Honeycomb query over the API with this key. A claim that
# needs query RESULTS has to be read off the rendered board in a browser, or
# emitted as a series by a collector — it cannot be curl'd. See ../README.md.
# Projected by the fleet's credential wrapper:
#   /usr/local/bin/with-livespec-env.sh -- ./apply-boards.sh
# plus python3. Prints one `created|updated <id> <name>` line per board,
# preceded by one line per panel.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HONEYCOMB_API="${HONEYCOMB_API:-https://api.honeycomb.io}"
: "${HONEYCOMB_CONFIG_KEY_LIVESPEC:?run through /usr/local/bin/with-livespec-env.sh -- (projects the livespec configuration key)}"

rc=0
for def in "${SCRIPT_DIR}"/*.json; do
  if ! python3 - "${def}" <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ["HONEYCOMB_API"]
KEY = os.environ["HONEYCOMB_CONFIG_KEY_LIVESPEC"]
STYLES = ("graph", "table", "combo")


def call(method, path, body=None):
    """Return (ok, payload). payload is parsed JSON on success, else a message."""
    req = urllib.request.Request(API + path, method=method)
    req.add_header("X-Honeycomb-Team", KEY)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        return True, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as exc:
        return False, "HTTP %d %s" % (exc.code, exc.read().decode("utf-8", "replace")[:400])
    except OSError as exc:
        return False, str(exc)


def cap(problems, label, value, low, high):
    n = len(value or "")
    if n < low or n > high:
        problems.append("%s is %d chars (allowed %d-%d)" % (label, n, low, high))


def validate(defn):
    """Refuse locally what the API would refuse, before any call is made."""
    problems = []
    cap(problems, "board name", defn.get("name"), 1, 255)
    cap(problems, "board description", defn.get("description"), 0, 1024)
    if defn.get("type") != "flexible":
        problems.append('board type must be "flexible"')
    if defn.get("layout_generation", "manual") not in ("auto", "manual"):
        problems.append('layout_generation must be "auto" or "manual"')
    tags = defn.get("tags", [])
    if len(tags) > 10:
        problems.append("%d tags (max 10)" % len(tags))
    for tag in tags:
        key, value = tag.get("key", ""), tag.get("value", "")
        if not key.isalpha() or not key.islower() or len(key) > 32:
            problems.append("tag key %r must be 1-32 lowercase letters" % key)
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789/-")
        if not value or value[0] not in "abcdefghijklmnopqrstuvwxyz":
            problems.append("tag value %r must start with a lowercase letter" % value)
        elif set(value) - allowed or len(value) > 128:
            problems.append("tag value %r must be <=128 of [a-z0-9/-]" % value)
    seen = set()
    for panel in defn.get("panels", []):
        kind = panel.get("type")
        if kind == "text":
            cap(problems, "text panel content", panel.get("text_panel", {}).get("content"), 1, 10000)
            continue
        if kind != "query":
            problems.append("panel type %r is not supported here (query or text)" % kind)
            continue
        key = panel.get("key") or "<unkeyed>"
        if not panel.get("dataset"):
            problems.append("panel %s has no dataset" % key)
        if panel.get("query_style", "graph") not in STYLES:
            problems.append("panel %s query_style must be one of %s" % (key, ", ".join(STYLES)))
        if not isinstance(panel.get("query"), dict) or not panel["query"]:
            problems.append("panel %s has no query specification" % key)
        annotation = panel.get("annotation", {})
        cap(problems, "panel %s annotation name" % key, annotation.get("name"), 1, 320)
        cap(problems, "panel %s annotation description" % key, annotation.get("description"), 0, 1023)
        name = annotation.get("name")
        if name in seen:
            problems.append("annotation name %r is used by two panels; names key the reuse" % name)
        seen.add(name)
    return problems


def canon(value):
    return json.dumps(value, sort_keys=True)


def stored_matches(desired, stored):
    """True when every key the definition states matches what the API stored."""
    if not isinstance(stored, dict):
        return False
    return all(canon(stored.get(k)) == canon(v) for k, v in desired.items())


def live_panels_by_annotation_name(board):
    """Map annotation name -> (query_id, annotation_id, dataset) for a live board."""
    index = {}
    for panel in board.get("panels") or []:
        if panel.get("type") != "query":
            continue
        query_panel = panel.get("query_panel") or {}
        dataset = query_panel.get("dataset")
        query_id = query_panel.get("query_id")
        annotation_id = query_panel.get("query_annotation_id")
        if not (dataset and query_id and annotation_id):
            continue
        ok, annotation = call("GET", "/1/query_annotations/%s/%s" % (dataset, annotation_id))
        if ok and isinstance(annotation, dict) and annotation.get("name"):
            index[annotation["name"]] = (query_id, annotation_id, dataset)
    return index


def resolve_panel(panel, prior):
    """Return (verb, query_id, annotation_id) or (None, reason, None) on refusal."""
    dataset = panel["dataset"]
    annotation = panel["annotation"]
    spec = panel["query"]
    if prior and prior[2] == dataset:
        ok, stored = call("GET", "/1/queries/%s/%s" % (dataset, prior[0]))
        if ok and stored_matches(spec, stored):
            return "reused", prior[0], prior[1]
    ok, query = call("POST", "/1/queries/%s" % dataset, spec)
    if not ok:
        return None, query, None
    ok, created = call(
        "POST",
        "/1/query_annotations/%s" % dataset,
        {
            "name": annotation["name"],
            "description": annotation.get("description", ""),
            "query_id": query["id"],
        },
    )
    if not ok:
        return None, created, None
    return "created", query["id"], created["id"]


def main(path):
    with open(path, encoding="utf-8") as handle:
        defn = json.load(handle)
    problems = validate(defn)
    if problems:
        for problem in problems:
            print("REFUSED %s: %s" % (path, problem), file=sys.stderr)
        return 1

    ok, boards = call("GET", "/1/boards")
    if not ok:
        print("FAILED list boards: %s" % boards, file=sys.stderr)
        return 1
    board = next((b for b in boards if b.get("name") == defn["name"]), None)
    prior_panels = live_panels_by_annotation_name(board) if board else {}

    rc = 0
    panels = []
    for panel in defn.get("panels", []):
        if panel["type"] == "text":
            panels.append(
                {"type": "text", "text_panel": panel["text_panel"], "position": panel["position"]}
            )
            print("  panel text")
            continue
        key, dataset = panel.get("key", "<unkeyed>"), panel["dataset"]
        verb, query_id, annotation_id = resolve_panel(
            panel, prior_panels.get(panel["annotation"]["name"])
        )
        if verb is None:
            print(
                "  SKIPPED panel %s [%s]: %s"
                "\n    (a column or dataset no datapoint has created yet is the expected cause;"
                " re-run after the emitter's host apply)" % (key, dataset, query_id),
                file=sys.stderr,
            )
            rc = 1
            continue
        panels.append(
            {
                "type": "query",
                "position": panel["position"],
                "query_panel": {
                    "query_id": query_id,
                    "query_annotation_id": annotation_id,
                    "query_style": panel.get("query_style", "graph"),
                },
            }
        )
        print("  panel %s %s [%s] query=%s" % (verb, key, dataset, query_id))

    body = {
        "name": defn["name"],
        "description": defn.get("description", ""),
        "type": "flexible",
        "layout_generation": defn.get("layout_generation", "manual"),
        "tags": defn.get("tags", []),
        "panels": panels,
    }
    if board:
        ok, out = call("PUT", "/1/boards/%s" % board["id"], body)
        verb, board_id = "updated", board["id"]
    else:
        ok, out = call("POST", "/1/boards", body)
        verb, board_id = "created", (out or {}).get("id", "") if ok else ""
    if not ok:
        print("FAILED %s %s: %s" % (verb, defn["name"], out), file=sys.stderr)
        return 1
    print("%s %s %s" % (verb, board_id, defn["name"]))
    url = ((out or {}).get("links") or {}).get("board_url")
    if url:
        print("  url %s" % url)
    return rc


sys.exit(main(sys.argv[1]))
PY
  then
    rc=1
  fi
done
exit "${rc}"
