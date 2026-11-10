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
#
# DRIFT MODE. `apply-boards.sh --drift` is READ-ONLY: for every definition
# beside this script it reads the live board of the same name and prints the
# name and each differing field or panel (`differs <name>` then one line per
# difference, a query panel named by its annotation), or `missing <name>` when
# no live board carries the name. It sends no create or update request — the
# program's HTTP helper refuses any method but GET in this mode — and exits
# non-zero when it reports any difference or missing definition, zero when
# every definition matches. What the service assigns is left out: board and
# annotation ids, the query ids a panel references (the stored query behind
# each is fetched and compared by its specification instead), timestamps and
# links, and the defaults the API fills in (the comparison is a SUBSET of what
# the live side holds, the same rule `stored_matches` applies when applying).
# A definition edited by hand is thereby reported BEFORE the next apply
# overwrites it.
set -euo pipefail

MODE=apply
case "${1:-}" in
  "") ;;
  --drift) MODE=drift ;;
  *) echo "usage: apply-boards.sh [--drift]" >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HONEYCOMB_API="${HONEYCOMB_API:-https://api.honeycomb.io}"
: "${HONEYCOMB_CONFIG_KEY_LIVESPEC:?run through /usr/local/bin/with-livespec-env.sh -- (projects the livespec configuration key)}"

rc=0
for def in "${SCRIPT_DIR}"/*.json; do
  if ! python3 - "${def}" "${MODE}" <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ["HONEYCOMB_API"]
KEY = os.environ["HONEYCOMB_CONFIG_KEY_LIVESPEC"]
STYLES = ("graph", "table", "combo")
DRIFT = sys.argv[2] == "drift"
ABSENT = "<absent>"


def call(method, path, body=None):
    """Return (ok, payload). payload is parsed JSON on success, else a message."""
    if DRIFT and method != "GET":
        raise RuntimeError("drift mode is read-only; refusing %s %s" % (method, path))
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


def read_live_panel(panel):
    """A live query panel as {name, dataset, style, position, annotation, query}."""
    query_panel = panel.get("query_panel") or {}
    dataset = query_panel.get("dataset")
    ok, annotation = call(
        "GET", "/1/query_annotations/%s/%s" % (dataset, query_panel.get("query_annotation_id"))
    )
    if not (ok and isinstance(annotation, dict)):
        return {"name": "<unreadable annotation: %s>" % annotation}
    ok, query = call("GET", "/1/queries/%s/%s" % (dataset, query_panel.get("query_id")))
    return {
        "name": annotation.get("name"),
        "dataset": dataset,
        "query_style": query_panel.get("query_style"),
        "position": panel.get("position"),
        "annotation": {"description": annotation.get("description", "")},
        "query": query if ok else None,
    }


def drift_panels(defn, board):
    """Lines naming every committed panel the live board does not hold as committed."""
    lines = []
    live_text = [p for p in board.get("panels") or [] if p.get("type") == "text"]
    live_query = {}
    for panel in board.get("panels") or []:
        if panel.get("type") == "query":
            held = read_live_panel(panel)
            live_query[held["name"]] = held
    texts = [p for p in defn.get("panels", []) if p["type"] == "text"]
    for index, panel in enumerate(texts):
        label = "text panel #%d" % (index + 1)
        if index >= len(live_text):
            lines.append("  %s: committed, missing from the live board" % label)
            continue
        want = {"position": panel["position"], "text_panel": panel["text_panel"]}
        diff(label, want, live_text[index], lines)
    for extra in range(len(texts), len(live_text)):
        lines.append("  text panel #%d: live only, not committed" % (extra + 1))
    wanted = set()
    for panel in defn.get("panels", []):
        if panel["type"] != "query":
            continue
        name = panel["annotation"]["name"]
        wanted.add(name)
        label = "panel %s" % name
        held = live_query.get(name)
        if held is None:
            lines.append("  %s: committed, missing from the live board" % label)
            continue
        want = {
            "dataset": panel["dataset"],
            "query_style": panel.get("query_style", "graph"),
            "position": panel["position"],
            "annotation": {"description": panel["annotation"].get("description", "")},
            "query": panel["query"],
        }
        diff(label, want, held, lines)
    for name in live_query:
        if name not in wanted:
            lines.append("  panel %s: live only, not committed" % name)
    return lines


def drift(path, defn):
    """Print the drift of the live board named by `defn`; 0 matches, 1 differs or missing."""
    ok, boards = call("GET", "/1/boards")
    if not ok:
        print("FAILED list boards: %s" % boards, file=sys.stderr)
        return 1
    board = next((b for b in boards if b.get("name") == defn["name"]), None)
    if board is None:
        print("missing %s" % defn["name"])
        return 1
    lines = []
    want = {
        "description": defn.get("description", ""),
        "type": "flexible",
        "layout_generation": defn.get("layout_generation", "manual"),
        "tags": defn.get("tags", []),
    }
    diff("", want, board, lines)
    lines.extend(drift_panels(defn, board))
    if lines:
        print("differs %s" % defn["name"])
        print("\n".join(lines))
        return 1
    return 0


def main(path):
    with open(path, encoding="utf-8") as handle:
        defn = json.load(handle)
    problems = validate(defn)
    if problems:
        for problem in problems:
            print("REFUSED %s: %s" % (path, problem), file=sys.stderr)
        return 1
    if DRIFT:
        return drift(path, defn)

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
