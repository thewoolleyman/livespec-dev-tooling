#!/usr/bin/env bash
# READ-ONLY fleet utilization read for the coordinator seat. Usage: fleet-utilization.sh [--json] [--stranded-only]
# Shell entry point; the logic is embedded Python (stdlib only) so the repo's
# product-Python AST gates, which govern the package, do not apply to a script.
set -euo pipefail
exec python3 -I - "$@" <<'PY'
"""READ-ONLY fleet utilization read for the coordinator seat.

Run first every tick:  scripts/coordinator/fleet-utilization.sh [--json] [--stranded-only]

Reports each execution node's real utilization (PSI, idle, memory), the
k3s cluster's pods / pending / quota, and the factory's fleet-vs-cap state,
then FLAGS an idle node beside a saturated one. Saturation is judged from CPU
PSI and mpstat idle, never from load average (see
.ai/ci-node-capacity-reads.md). Every ssh has a ConnectTimeout and an overall
timeout; a host that fails every candidate user is reported UNREACHABLE with the
error, never skipped. Nothing here mutates: only cat / mpstat / kubectl get / bd list /
bd sql SELECT.

Launcher log lines carry a bare UTC clock (HH:MM:SS). Each is dated by walking its
log from the `=== ... at <ISO>` header of its ticket section, so a line from an
earlier day cannot read as recent after midnight or after the log is rewritten.

The UNTICKETED-READY section reads every livespec beads tenant's READY items
through the credential wrapper and flags any non-epic READY item older than
30 minutes that has no dispatcher ticket behind it (no seq-<id>.log written in
the last 30 min, no queue entry, no capture-argv in the last 6 h). A tenant whose read fails is reported
UNREADABLE, never skipped. Each flagged row then carries its cause when it has one:
`HELD spec-change <topic> <reason>` from the newest livespec-spec-change-tier comment
(the same three reasons as the orchestrator's _spec_change_tier_hold, ratification read
from this host's checkout of the tenant's SPECIFICATION/history), or `BLOCKED by <id>`
for a `blocks` dependency that is not closed. Causes share the section's time budget;
rows the budget did not reach are counted as skipped, never shown as having no cause.

The STRANDED-CAPACITY section, printed right after the node table, reads every cap and
quota this script can reach: the launcher fleet-cap and per-host cap files, the
dispatcher's per-tenant wip_cap (wip-act.*), the factory namespace ResourceQuota, each
Kueue ClusterQueue flavor quota, and each ARC scale set's maxRunners. For each it prints
the limit, the use, the waiting work and the idle % of the nodes it covers. A line is
prefixed FLAGGED when the limit is reached while work waits AND a covered node reads idle
above STRANDED_IDLE_PCT: a stall of the "cap too low" kind (.ai/coordinator-duties.md
section 10). A cap or quota that cannot be read prints `UNREAD <name>: <reason>`, never
silence. `--stranded-only` prints just that section; scripts/coordinator/top5 calls it.

A FACTORY line (fleet-cap, the per-host cap files, the dispatcher wip_cap lines and the
factory ResourceQuota) covers only the nodes a factory sandbox pod can be placed on: Ready,
not cordoned, no NoSchedule/NoExecute taint the pods do not tolerate
(FACTORY_PRESSURE_TOLERATED_TAINTS, default node-role/ci=factory), and every label the pods'
nodeSelector requires (FACTORY_PRESSURE_REQUIRED_LABELS, `key=value`, comma-separated, default
ci-runner.io/factory-admit=true) - the same scope the factory pressure reconciler uses. Any
other factory node is printed with its reason, e.g. `hp-xubuntu 55% idle (not-admitting)`,
and never makes a line FLAGGED. When the node labels cannot be read the scoping prints
UNREAD and no node counts as covered. CI lines (Kueue flavors, ARC scale sets) keep their
own node scoping.

An ARC line counts a pending runner as waiting only when its EphemeralRunner is older than
STRANDED_ARC_STARTUP_S (default 90 s, overridable by environment). A younger one is in
ARC's normal startup window (the set reads "current N, pending N, running 0" for 15-30 s
while the pods register) and is printed as `starting`; it never makes the line FLAGGED.
When the EphemeralRunners cannot be read the line says their ages are UNREAD and every
pending runner counts as waiting.
"""

import argparse
import collections
import concurrent.futures
import datetime
import glob
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

# A covered node idle above this % beside a binding cap or quota is stranded capacity.
# A value-only constant: tune it here, never pin it in a test.
STRANDED_IDLE_PCT = 40

# An ARC EphemeralRunner pending for no longer than this many seconds is starting, not
# stranded: ARC's normal runner-startup window (measured 2026-11-12, a listener burst
# drained in under a minute). Overridable by environment; a value that does not parse is ignored.
try:
    STRANDED_ARC_STARTUP_S = int(os.environ.get("STRANDED_ARC_STARTUP_S", "90"))
except ValueError:
    STRANDED_ARC_STARTUP_S = 90

# Candidate ssh targets, in order. First that answers wins. `cwoolley` is the
# account that holds the authorized key on every execution node (verified
# 2026-11-03: default `ubuntu` fails on hp-xubuntu with "failed to look up
# local user"); the bare host is tried too so ~/.ssh/config stanzas still work.
HOSTS = {
    "gmktec-xubuntu": ["gmktec-xubuntu", "cwoolley@gmktec-xubuntu"],
    "poweredge-xubuntu": ["poweredge-xubuntu", "cwoolley@poweredge-xubuntu"],
    "hp-xubuntu": ["cwoolley@hp-xubuntu", "hp-xubuntu"],
}
K3S_SERVER = "poweredge-xubuntu"
CANARY = pathlib.Path("/data/projects/livespec-orchestrator-beads-fabro/tmp/petri-canary")
QUEUE_DIR = pathlib.Path("/run/user/1000/gmktec-launch-queue.d")
SSH_CONNECT_TIMEOUT = 5
SSH_OVERALL_TIMEOUT = 25
PSI_IDLE_MAX = 10.0
IDLE_PCT_MIN = 40.0
PSI_SATURATED_MIN = 30.0
FLEET_WINDOW_S = 20 * 60
LAUNCH_WINDOW_S = 30 * 60
DAY_S = 24 * 3600
# A launcher log can interleave slightly out of order; a larger backward step is midnight.
CLOCK_BACKSTEP_S = 5 * 60
# Launchers log a fleet= line about every 20 s, so a family this far behind is not current.
FLEET_STALE_AFTER_S = 2 * 60
MIN_POD_COLS = 8
QUOTA_COLS = 3
SSH_BIN = shutil.which("ssh") or "ssh"
PROJECTS = pathlib.Path("/data/projects")
ENV_WRAPPER = "/usr/local/bin/with-livespec-env.sh"
READY_SECTION_TIMEOUT_S = 60
READY_STALE_S = 30 * 60
CAPTURE_WINDOW_S = 6 * 3600
TITLE_MAX = 80
CAUSE_CHUNK = 100
CAUSE_WORKERS = 4
TIER_HEAD_CHARS = 4000
SPEC_TIER_MARKER = "livespec-spec-change-tier"
SPEC_CHANGE_TIER = "spec-change"
RATIFYING_DECISIONS = ("accept", "modify")
UNNAMED_TOPIC = "(none linked)"
ABSENT_VALUE = "(none)"
SAFE_NAME_RE = re.compile(r"[\w.-]+")


def out(text=""):
    sys.stdout.write(text + "\n")


# Read-only probe, identical on every node (POSIX sh, stdin to `sh -s`).
PROBE = r"""
echo "nproc=$(nproc)"
echo "load=$(cut -d' ' -f1-3 /proc/loadavg)"
echo "psi=$(grep '^some' /proc/pressure/cpu)"
echo "idle=$(LC_ALL=C mpstat 1 1 2>/dev/null | awk '/^Average/ {print $NF}')"
awk '/^MemAvailable:/ {print "memavail_kb=" $2} /^SwapTotal:/ {print "swaptotal_kb=" $2} \
/^SwapFree:/ {print "swapfree_kb=" $2}' /proc/meminfo
"""


def ssh(target, remote_cmd, stdin=None):
    """Run a read-only command over ssh; return (ok, stdout_or_error)."""
    argv = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={SSH_CONNECT_TIMEOUT}",
        target,
        remote_cmd,
    ]
    try:
        proc = subprocess.run(  # noqa: S603
            argv,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=SSH_OVERALL_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"timeout after {SSH_OVERALL_TIMEOUT}s"
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        return False, err.replace("\n", " | ")[:200]
    return True, proc.stdout


def local(script):
    proc = subprocess.run(  # noqa: S603
        ["/bin/sh", "-s"],
        input=script,
        capture_output=True,
        text=True,
        timeout=SSH_OVERALL_TIMEOUT,
        check=False,
    )
    return proc.stdout


def parse_probe(text):
    kv = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    psi = re.search(r"avg10=([\d.]+) avg60=([\d.]+) avg300=([\d.]+)", kv.get("psi", ""))
    swap_used = int(kv.get("swaptotal_kb", 0)) - int(kv.get("swapfree_kb", 0))
    idle = kv.get("idle", "")
    return {
        "cores": int(kv.get("nproc", 0)),
        "load": kv.get("load", "?"),
        "psi_some_avg10": float(psi.group(1)) if psi else None,
        "psi_some_avg60": float(psi.group(2)) if psi else None,
        "idle_pct": float(idle) if idle else None,
        "mem_avail_gib": round(int(kv.get("memavail_kb", 0)) / 1048576, 1),
        "swap_used_gib": round(swap_used / 1048576, 1),
    }


def probe_node(name):
    errors = []
    for target in HOSTS.get(name, []):
        if name == "vps":
            break
        ok, out = ssh(target, "sh -s", stdin=PROBE)
        if ok:
            node = parse_probe(out)
            node.update(name=name, target=target, reachable=True)
            return node
        errors.append(f"{target}: {out}")
    return {"name": name, "reachable": False, "errors": errors}


def probe_vps():
    node = parse_probe(local(PROBE))
    node.update(name="vps", target="local", reachable=True)
    return node


def read_cluster():
    out = {"reachable": False, "pods": {}, "pending": {}, "quota": [], "error": None}
    kc = "sudo -n k3s kubectl"
    ok, pods = ssh(K3S_SERVER, f"{kc} get pods -A -o wide --no-headers")
    if not ok:
        out["error"] = pods
        return out
    out["reachable"] = True
    pods_by = collections.defaultdict(lambda: collections.defaultdict(int))
    pending = collections.defaultdict(int)
    for line in pods.splitlines():
        cols = line.split()
        if len(cols) < MIN_POD_COLS:
            continue
        ns, status, node = cols[0], cols[3], cols[7]
        if status in ("Running", "Pending"):
            pods_by[node][ns] += 1
        if status == "Pending":
            pending[ns] += 1
    out["pods"] = {n: dict(v) for n, v in pods_by.items()}
    out["pending"] = dict(pending)
    ok, quota = ssh(K3S_SERVER, f"{kc} get resourcequota -A --no-headers")
    if ok:
        for line in quota.splitlines():
            cols = line.split(None, 2)
            if len(cols) == QUOTA_COLS:
                out["quota"].append({"namespace": cols[0], "name": cols[1], "usage": cols[2]})
    else:
        out["quota_error"] = quota
    return out


CLOCK_RE = re.compile(r"(\d\d):(\d\d):(\d\d) ")
SECTION_HEADER_RE = re.compile(r"=== .*?(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)Z")


def header_epoch(line):
    """Epoch of a dated `=== ...` ticket-section header, or None for any other line."""
    m = SECTION_HEADER_RE.match(line)
    if not m:
        return None
    try:
        stamp = datetime.datetime.fromisoformat(m.group(1))
    except ValueError:
        return None
    return stamp.replace(tzinfo=datetime.UTC).timestamp()


def clock_of(epoch):
    return int(epoch) % DAY_S


def walk_forward(anchor, clock):
    """(line epoch, next anchor) for a clock read forward from anchor, across midnight."""
    delta = (clock - clock_of(anchor)) % DAY_S
    if delta > DAY_S - CLOCK_BACKSTEP_S:
        return anchor - (DAY_S - delta), anchor
    return anchor + delta, anchor + delta


def walk_backward(anchor, clock):
    """(line epoch, next anchor) for a clock read backward from anchor, across midnight."""
    delta = (clock_of(anchor) - clock) % DAY_S
    if delta > DAY_S - CLOCK_BACKSTEP_S:
        return anchor + (DAY_S - delta), anchor
    return anchor - delta, anchor - delta


def dated_lines(text, mtime):
    """Every clock-stamped line of one launcher log as (epoch, line), in file order.

    A line after a dated section header is walked forward from that header. A line
    before the first header is walked backward from it, or from the file's mtime when
    the log has no header at all. The header is what survives a rewrite: a rewrite
    moves the mtime but not the date a section started.
    """
    lines = text.splitlines()
    first_header = next((i for i, ln in enumerate(lines) if header_epoch(ln) is not None), None)
    dated = {}
    anchor = mtime if first_header is None else header_epoch(lines[first_header])
    stop = len(lines) if first_header is None else first_header
    for i in range(stop - 1, -1, -1):
        m = CLOCK_RE.match(lines[i])
        if m:
            h, mi, s = (int(x) for x in m.groups())
            dated[i], anchor = walk_backward(anchor, h * 3600 + mi * 60 + s)
    anchor = None
    for i in range(stop, len(lines)):
        stamp = header_epoch(lines[i])
        if stamp is not None:
            anchor = stamp
            continue
        m = CLOCK_RE.match(lines[i])
        if m:
            h, mi, s = (int(x) for x in m.groups())
            dated[i], anchor = walk_forward(anchor, h * 3600 + mi * 60 + s)
    return [(dated[i], lines[i]) for i in sorted(dated)]


def mtime_or_none(path):
    """st_mtime, or None when the path vanished after glob (e.g. a .qstamp-<pid>)."""
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


def read_or_empty(path):
    """File text, or "" when the path vanished after glob."""
    try:
        return path.read_text(errors="replace")
    except FileNotFoundError:
        return ""


def recent_files(pattern, window_s):
    cutoff = time.time() - window_s
    return [p for p in CANARY.glob(pattern) if (mtime_or_none(p) or 0) >= cutoff]


def read_factory():
    now = time.time()
    fac = {
        "fleet": None,
        "cap": None,
        "fleet_line_age_s": None,
        "fleet_cap_file": None,
        "queue_depth": None,
        "launches_30m": [],
        "fleet_log": None,
        "cap_mismatch": False,
        "other_families": {},
    }
    try:
        fac["fleet_cap_file"] = int((CANARY / "fleet-cap").read_text().strip())
    except (OSError, ValueError):
        fac["fleet_cap_file"] = None
    rows = fleet_lines(now)
    chosen, fac["cap_mismatch"], fac["other_families"] = pick_fleet(rows, fac["fleet_cap_file"])
    if chosen:
        fac["fleet_line_age_s"], fac["fleet"], cap, fac["fleet_log"] = chosen
        fac["cap"] = cap if fac["cap_mismatch"] else fac["fleet_cap_file"]
    try:
        fac["queue_depth"] = sum(1 for p in QUEUE_DIR.iterdir() if p.is_file())
    except OSError:
        fac["queue_depth"] = None
    fac["launches_30m"] = recent_launches(now)
    return fac


FLEET_RE = re.compile(r"\d\d:\d\d:\d\d .*?fleet=(\d+)(?: cap=(\d+))?")


def fleet_lines(now):
    """Every fleet=N [cap=M] line in the window as (age, fleet, cap_or_None, log), freshest first."""
    rows = []
    for path in recent_files("seq-*.log", FLEET_WINDOW_S):
        for epoch, line in dated_lines(read_or_empty(path), mtime_or_none(path) or now):
            m = FLEET_RE.match(line)
            if not m:
                continue
            age = int(now - epoch)
            if age <= FLEET_WINDOW_S:
                cap = int(m.group(2)) if m.group(2) else None
                rows.append((max(age, 0), int(m.group(1)), cap, path.name))
    return sorted(rows, key=lambda r: r[0])


def pick_fleet(rows, cap_file):
    """The fleet line to report, whether it disagrees with the fleet-cap file, and the rest.

    A line whose cap equals the fleet-cap file (or a green line with no cap) is the petri
    gmktec family, and any other cap is a different family. The petri family is reported
    only while it is current beside the freshest line; otherwise the freshest line is
    reported and the mismatch flagged, so an old family's value can never stand in for
    what launchers are logging now. Every other family is listed with its age, and marked
    stale once it is that far behind the reported line.
    """
    if not rows:
        return None, False, {}

    def family(row):
        return None if row[2] == cap_file else row[2]

    petri = [r for r in rows if family(r) is None]
    current = bool(petri) and petri[0][0] - rows[0][0] <= FLEET_STALE_AFTER_S
    chosen = petri[0] if current else rows[0]
    others = {}
    for r in rows:
        if family(r) != family(chosen) and r[3] not in others:
            stale = r[0] - chosen[0] > FLEET_STALE_AFTER_S
            others[r[3]] = {"age_s": r[0], "fleet": r[1], "cap": r[2], "stale": stale}
    return chosen, not current, others


def recent_launches(now):
    """LAUNCH lines truly inside the trailing window, oldest first."""
    launches = set()
    for path in recent_files("*", LAUNCH_WINDOW_S):
        if not path.is_file():
            continue
        for epoch, line in dated_lines(read_or_empty(path), mtime_or_none(path) or now):
            if line[9:16] == "LAUNCH " and now - epoch <= LAUNCH_WINDOW_S:
                launches.add((epoch, line[:160]))
    return [line for _epoch, line in sorted(launches)]


def ready_tenants():
    """Every livespec repo under /data/projects that carries a beads tenant pointer."""
    repos = [PROJECTS / "livespec", *sorted(PROJECTS.glob("livespec-*"))]
    return [r for r in repos if (r / ".beads" / "config.yaml").is_file()]


def first_error_line(text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    real = [ln for ln in lines if not ln.lower().startswith("warning")]
    return ((real or lines or ["no output"])[0])[:200]


def bd_json(repo, bd_args, timeout_s):
    """A bd read through the wrapper, as (list_of_records, None) or (None, error)."""
    argv = [ENV_WRAPPER, "--", "bd", *bd_args]
    try:
        proc = subprocess.run(  # noqa: S603
            argv, cwd=repo, capture_output=True, text=True, timeout=timeout_s, check=False
        )
    except subprocess.TimeoutExpired:
        return None, f"timeout after {timeout_s}s"
    except OSError as exc:
        return None, str(exc)
    if proc.returncode != 0:
        return None, first_error_line(proc.stderr or proc.stdout or f"exit {proc.returncode}")
    try:
        items = json.loads(proc.stdout or "[]")
    except ValueError as exc:
        return None, f"unparseable JSON: {exc}"
    if items is None:
        return [], None
    if not isinstance(items, list):
        return None, "unexpected JSON shape (not a list)"
    return items, None


def read_ready(repo, timeout_s):
    """READY items of one tenant via the wrapper (`bd ready` is dead here; see CLAUDE.md)."""
    return bd_json(repo, ["list", "--status", "ready", "--limit", "0", "--json"], timeout_s)


def queue_texts():
    texts = []
    try:
        for p in QUEUE_DIR.iterdir():
            if p.is_file():
                try:
                    texts.append(p.read_text(errors="replace"))
                except OSError:
                    continue
    except OSError:
        pass
    return texts


def is_ticketed(item_id, queued):
    seq = CANARY / f"seq-{item_id}.log"
    if (mtime_or_none(seq) or 0) >= time.time() - READY_STALE_S:
        return True
    pat = re.compile(r"(?<![\w.-])" + re.escape(item_id) + r"(?![\w.-])")
    if any(pat.search(t) for t in queued):
        return True
    cutoff = time.time() - CAPTURE_WINDOW_S
    return any(
        (mtime_or_none(p) or 0) >= cutoff for p in CANARY.glob(f"{item_id}-r*.capture-argv")
    )


def fmt_age(seconds):
    m = int(seconds // 60)
    if m < 60:
        return f"{m}m"
    h, m = divmod(m, 60)
    if h < 48:
        return f"{h}h{m:02d}m"
    return f"{h // 24}d{h % 24:02d}h"


def sql_id_list(ids):
    return ", ".join(f"'{i}'" for i in ids)


def open_blockers(item):
    """Ids of the item's `blocks` dependencies (`bd list` spells these depends_on_id + type)."""
    return [
        d["depends_on_id"]
        for d in item.get("dependencies") or []
        if d.get("type") == "blocks" and SAFE_NAME_RE.fullmatch(d.get("depends_on_id") or "")
    ]


def newest_tier_fields(rows):
    """item id -> `key: value` fields of its newest tier record, marker checked exactly."""
    newest = {}
    for row in sorted(rows, key=lambda r: (r.get("created_at") or "", r.get("id") or "")):
        body = (row.get("head") or "").strip()
        if body.splitlines()[:1] == [SPEC_TIER_MARKER]:
            newest[row.get("issue_id")] = body
    fields = {}
    for item_id, body in newest.items():
        parts = (raw.strip().partition(": ") for raw in body.splitlines())
        fields[item_id] = {key: value for key, sep, value in parts if sep}
    return fields


def topic_is_ratified(repo, topic):
    """Whether this host's checkout of the tenant's spec history ratified the topic."""
    if not SAFE_NAME_RE.fullmatch(topic):
        return False
    history = repo / "SPECIFICATION" / "history"
    pattern = f"v*/proposed_changes/{glob.escape(topic)}-revision.md"
    for path in history.glob(pattern):
        lines = read_or_empty(path).splitlines()
        front = lines[1:lines.index("---", 1)] if lines[:1] == ["---"] and "---" in lines[1:] else []
        for line in front:
            if line.startswith("decision:") and line[9:].strip() in RATIFYING_DECISIONS:
                return True
    return False


def hold_cause(fields, repo, ratified):
    """`HELD ...` for a recorded spec-change tier, or None when the record admits the item."""
    required = ("tier", "spec-version", "behaviour-digest")
    if fields is None or any(k not in fields for k in required):
        return None
    if fields["tier"] != SPEC_CHANGE_TIER:
        return None
    topic = fields.get("linked-proposal-topic", ABSENT_VALUE)
    if topic == ABSENT_VALUE:
        return f"HELD spec-change {UNNAMED_TOPIC} no-linked-topic"
    if (repo, topic) not in ratified:
        ratified[(repo, topic)] = topic_is_ratified(repo, topic)
    reason = "awaiting-rejudgement" if ratified[(repo, topic)] else "unratified-topic"
    return f"HELD spec-change {topic} {reason}"


def read_cause_chunk(repo, rows, blockers_of, deadline):
    """Tier records and blocker statuses of one chunk, as (tier_rows, statuses, error)."""
    ids = [r["id"] for r in rows if SAFE_NAME_RE.fullmatch(r["id"])]
    query = (
        f"SELECT issue_id, id, created_at, LEFT(text, {TIER_HEAD_CHARS}) AS head FROM comments"
        f" WHERE issue_id IN ({sql_id_list(ids)}) AND text LIKE '{SPEC_TIER_MARKER}%'"
    )
    remaining = deadline - time.monotonic()
    if remaining < 1:
        return None, None, f"section budget {READY_SECTION_TIMEOUT_S}s spent"
    tier_rows, err = bd_json(repo, ["sql", "--json", query], remaining)
    if err is not None:
        return None, None, err
    wanted = sorted({b for r in rows for b in blockers_of.get(r["id"], [])})
    if not wanted:
        return tier_rows, {}, None
    query = f"SELECT id, status FROM issues WHERE id IN ({sql_id_list(wanted)})"
    remaining = deadline - time.monotonic()
    if remaining < 1:
        return None, None, f"section budget {READY_SECTION_TIMEOUT_S}s spent"
    status_rows, err = bd_json(repo, ["sql", "--json", query], remaining)
    if err is not None:
        return None, None, err
    return tier_rows, {r.get("id"): r.get("status") for r in status_rows}, None


def apply_chunk_causes(rows, repo, outcome, blockers_of, ratified):
    tier_rows, statuses, _err = outcome
    tiers = newest_tier_fields(tier_rows)
    for row in rows:
        causes = []
        hold = hold_cause(tiers.get(row["id"]), repo, ratified)
        if hold:
            causes.append(hold)
        for blocker in blockers_of.get(row["id"], []):
            if blocker not in statuses:
                causes.append(f"BLOCKED by {blocker} (not in this tenant)")
            elif statuses[blocker] != "closed":
                causes.append(f"BLOCKED by {blocker}")
        row["cause"] = "; ".join(causes) or None
        row["cause_read"] = True


def read_causes(result, repos, blockers_of, deadline):
    """Fill the cause of as many flagged rows as the section budget reaches, newest first."""
    by_repo = collections.defaultdict(list)
    for row in sorted(result["items"], key=lambda r: r["age_s"]):
        row["cause"], row["cause_read"] = None, False
        by_repo[row["repo"]].append(row)
    chunks = [
        (name, rows[i : i + CAUSE_CHUNK])
        for name, rows in by_repo.items()
        for i in range(0, len(rows), CAUSE_CHUNK)
    ]
    errors, ratified = [], {}
    if chunks:
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=CAUSE_WORKERS)
        futures = {
            pool.submit(read_cause_chunk, repos[name], rows, blockers_of.get(name, {}), deadline): (
                name,
                rows,
            )
            for name, rows in chunks
        }
        done, _pending = concurrent.futures.wait(futures, timeout=max(0.1, deadline - time.monotonic()))
        pool.shutdown(wait=False, cancel_futures=True)
        for fut in done:
            name, rows = futures[fut]
            outcome = fut.result()
            if outcome[2] is not None:
                errors.append(f"{name}: {outcome[2]}")
                continue
            apply_chunk_causes(rows, repos[name], outcome, blockers_of.get(name, {}), ratified)
    items = result["items"]
    read = [r for r in items if r.get("cause_read")]
    result["causes"] = {
        "flagged": len(items),
        "read": len(read),
        "held": sum(1 for r in read if "HELD " in (r["cause"] or "")),
        "blocked": sum(1 for r in read if "BLOCKED " in (r["cause"] or "")),
        "no_recorded_cause": sum(1 for r in read if not r["cause"]),
        "skipped": len(items) - len(read),
        "errors": errors,
    }


def read_unticketed_ready():
    """Flag non-epic READY items >30m old with no ticket, across every tenant, in ~60s total."""
    result = {"tenants": [], "unreadable": [], "items": []}
    now = datetime.datetime.now(datetime.UTC)
    deadline = time.monotonic() + READY_SECTION_TIMEOUT_S
    tenants = ready_tenants()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(tenants)))
    futures = {pool.submit(read_ready, r, READY_SECTION_TIMEOUT_S - 5): r for r in tenants}
    reads = {}
    for fut, repo in futures.items():
        remaining = max(0.1, deadline - time.monotonic())
        try:
            reads[repo] = fut.result(timeout=remaining)
        except concurrent.futures.TimeoutError:
            reads[repo] = (None, f"section timeout after {READY_SECTION_TIMEOUT_S}s")
    pool.shutdown(wait=False, cancel_futures=True)
    queued = queue_texts()
    blockers_of = collections.defaultdict(dict)
    for repo in tenants:
        items, err = reads[repo]
        if err is not None:
            result["unreadable"].append({"repo": repo.name, "error": err})
            continue
        result["tenants"].append({"repo": repo.name, "ready": len(items)})
        for it in items:
            if it.get("issue_type") == "epic" or not it.get("id"):
                continue
            try:
                stamp = (it.get("updated_at") or "").replace("Z", "+00:00")
                updated = datetime.datetime.fromisoformat(stamp)
            except ValueError:
                continue
            age = (now - updated).total_seconds()
            if age <= READY_STALE_S or is_ticketed(it["id"], queued):
                continue
            blockers_of[repo.name][it["id"]] = open_blockers(it)
            result["items"].append(
                {
                    "repo": repo.name,
                    "id": it["id"],
                    "age_s": int(age),
                    "age": fmt_age(age),
                    "priority": it.get("priority"),
                    "title": (it.get("title") or "")[:TITLE_MAX],
                }
            )
    read_causes(result, {r.name: r for r in tenants}, blockers_of, deadline)
    result["items"].sort(key=lambda r: (r["repo"], -r["age_s"]))
    return result


# ---- STRANDED-CAPACITY (coordinator rule STRANDED-CAPACITY, scope event 2026-11-10T23:33:39Z) ----
KC = "sudo -n k3s kubectl"
HP_QUEUE_DIR = pathlib.Path("/run/user/1000/hp-launch-queue.d")
FACTORY_NS = "factory"
FACTORY_NODE_LABEL = "ci-runner.io/factory"
# Labels the factory sandbox pods' nodeSelector requires, and the taints they tolerate. The
# env names and defaults are the factory pressure reconciler's (reconcile-factory-pressure-taint.sh).
FACTORY_REQUIRED_LABELS = [
    r.strip()
    for r in os.environ.get("FACTORY_PRESSURE_REQUIRED_LABELS", "ci-runner.io/factory-admit=true").split(",")
    if r.strip()
]
FACTORY_TOLERATED_TAINTS = [
    t.strip()
    for t in os.environ.get("FACTORY_PRESSURE_TOLERATED_TAINTS", "node-role/ci=factory").split(",")
    if t.strip()
]
ARC_NS = "arc-runners"
# A ticket log quieter than this is not a live waiting ticket.
TICKET_FRESH_S = 10 * 60
# Per-host cap file -> the launcher counters that log its use, and the node its servers run on.
HOST_CAPS = {
    "gmk-cap": (("gmktec", "petri"), ["gmktec-xubuntu"]),
    "candidate-cap": (("candidate",), ["gmktec-xubuntu"]),
    "hl-cap": (("hl",), ["gmktec-xubuntu"]),
}
COUNTER_RE = re.compile(r"\b(gmktec|petri|candidate|hl)=(\d+)")
HL_LIVE_RE = re.compile(r"mi-homelab not green: live=(\d+)")
WIP_TENANT_RE = re.compile(r"active in ([\w.-]+)")
SIZE_GATE_RE = re.compile(r"SIZE-SCREEN (HOLD|GATE)")
QTY_RE = re.compile(r"([\d.]+)([a-zA-Z]*)")
QTY_SUFFIX = {
    "m": 1e-3,
    "k": 1e3,
    "M": 1e6,
    "G": 1e9,
    "T": 1e12,
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
}


def qty(text):
    """A Kubernetes quantity as a float, or None when it does not parse."""
    m = QTY_RE.fullmatch(str(text).strip())
    if not m or (m.group(2) and m.group(2) not in QTY_SUFFIX):
        return None
    return float(m.group(1)) * QTY_SUFFIX.get(m.group(2), 1)


def kube_json(args):
    """(document, None) for a read-only `kubectl get ... -o json`, or (None, reason)."""
    ok, text = ssh(K3S_SERVER, f"{KC} get {args} -o json")
    if not ok:
        return None, text
    try:
        return json.loads(text), None
    except ValueError as exc:
        return None, f"unparseable JSON: {exc}"


def expr_ok(labels, expr):
    op, key, values = expr.get("operator"), expr.get("key"), expr.get("values") or []
    if op == "In":
        return labels.get(key) in values
    if op == "NotIn":
        return labels.get(key) not in values
    if op == "Exists":
        return key in labels
    if op == "DoesNotExist":
        return key not in labels
    return True


def nodes_matching(node_labels, selector=None, terms=None):
    """Node names whose labels satisfy a selector and any one of the affinity terms."""
    hits = []
    for name, labels in sorted(node_labels.items()):
        if any(labels.get(k) != v for k, v in (selector or {}).items()):
            continue
        if terms and not any(
            all(expr_ok(labels, e) for e in t.get("matchExpressions") or []) for t in terms
        ):
            continue
        hits.append(name)
    return hits


def node_idle_text(name, nodes_by_name):
    """(text, idle % or None) for one node from the probe table."""
    node = nodes_by_name.get(name)
    if node is None:
        return f"{name} unprobed", None
    if not node["reachable"]:
        return f"{name} UNREACHABLE", None
    if node["idle_pct"] is None:
        return f"{name} idle ?", None
    return f"{name} {node['idle_pct']:.0f}% idle", node["idle_pct"]


def covered_idle(covered, nodes_by_name):
    """(text, any covered node idle above STRANDED_IDLE_PCT).

    `covered` is a list of node names, or a factory scope dict (see factory_scope): its
    excluded nodes are printed with their reason and never count toward the idle hit.
    """
    scope = covered if isinstance(covered, dict) else {"covered": covered, "excluded": {}, "unread": None}
    if scope["unread"]:
        return f"covered-node scoping UNREAD ({scope['unread']})"[:200], False
    parts, idle_hit = [], False
    for name in scope["covered"]:
        text, idle = node_idle_text(name, nodes_by_name)
        parts.append(text)
        idle_hit = idle_hit or (idle is not None and idle > STRANDED_IDLE_PCT)
    for name, reason in sorted(scope["excluded"].items()):
        parts.append(f"{node_idle_text(name, nodes_by_name)[0]} ({reason})")
    if not scope["covered"]:
        parts.insert(0, "no covered node found")
    return ", ".join(parts), idle_hit


def tolerates(taint):
    key, value = taint.get("key", ""), taint.get("value")
    return any(t == key or (value is not None and t == f"{key}={value}") for t in FACTORY_TOLERATED_TAINTS)


def factory_exclusion(node):
    """Why a factory sandbox pod can never be placed on this node now, or None."""
    labels = node["metadata"].get("labels") or {}
    for req in FACTORY_REQUIRED_LABELS:
        key, _, value = req.partition("=")
        if labels.get(key) != value:
            return "not-admitting" if key == "ci-runner.io/factory-admit" else f"label {key}!={value}"
    ready = [c.get("status") for c in (node.get("status") or {}).get("conditions") or [] if c.get("type") == "Ready"]
    if ready != ["True"]:
        return "not-ready"
    spec = node.get("spec") or {}
    if spec.get("unschedulable"):
        return "cordoned"
    for taint in spec.get("taints") or []:
        if taint.get("effect") in ("NoSchedule", "NoExecute") and not tolerates(taint):
            return f"untolerated-taint {taint.get('key', '')}"
    return None


def factory_scope(nodes_doc, err):
    """{covered, excluded: {name: reason}, unread} over the nodes labelled FACTORY_NODE_LABEL=true."""
    if nodes_doc is None:
        return {"covered": [], "excluded": {}, "unread": f"node labels: {err}"}
    covered, excluded = [], {}
    for node in sorted(nodes_doc.get("items", []), key=lambda n: n["metadata"]["name"]):
        if (node["metadata"].get("labels") or {}).get(FACTORY_NODE_LABEL) != "true":
            continue
        why = factory_exclusion(node)
        if why is None:
            covered.append(node["metadata"]["name"])
        else:
            excluded[node["metadata"]["name"]] = why
    return {"covered": covered, "excluded": excluded, "unread": None}


def host_scope(scope, names):
    """A per-host cap's fixed node list, narrowed to the factory scope."""
    if scope["unread"]:
        return scope
    return {
        "covered": [n for n in names if n in scope["covered"]],
        "excluded": {n: scope["excluded"].get(n, "not a factory node") for n in names if n not in scope["covered"]},
        "unread": None,
    }


def stranded_row(name, limit, use, binds, waiting, waiting_text, covered, nodes_by_name):
    idle_text, idle_hit = covered_idle(covered, nodes_by_name)
    flagged = bool(binds and waiting > 0 and idle_hit)
    at = " AT LIMIT" if binds else ""
    text = f"{name}: use {use} / limit {limit}{at}; waiting {waiting_text}; nodes {idle_text}"
    return {"name": name, "flagged": flagged, "text": ("FLAGGED " if flagged else "") + text}


def unread_row(name, reason):
    return {"name": name, "flagged": False, "text": f"UNREAD {name}: {reason}"[:300]}


def tenant_index():
    """item id -> tenant, from the dispatcher's wip-claimed-cache.<tenant>.json files."""
    index = {}
    for path in CANARY.glob("wip-claimed-cache.*.json"):
        tenant = path.name.removeprefix("wip-claimed-cache.").removesuffix(".json")
        try:
            items = json.loads(read_or_empty(path) or "{}").get("st") or {}
        except ValueError:
            continue
        index.update(dict.fromkeys(items, tenant))
    return index


def size_gated(item_id):
    """Whether the item's newest seq-log section ends size-gated (a HOLD/GATE verdict, no LAUNCH)."""
    lines = read_or_empty(CANARY / f"seq-{item_id}.log").splitlines()
    heads = [i for i, ln in enumerate(lines) if header_epoch(ln) is not None]
    section = lines[heads[-1] :] if heads else lines
    gated = any(SIZE_GATE_RE.search(ln) and "repo WIP full" not in ln for ln in section)
    return gated and not any("SIZE-SCREEN LAUNCH" in ln or ln[9:16] == "LAUNCH " for ln in section)


def read_launcher_tickets(now):
    """Classify the live queued launcher tickets and take the newest per-host use counters.

    Each queue entry names its launcher pid, its item and wip-wait. A dead pid is stale
    litter and is counted apart. wip-wait=1 is a ticket held by its repo's WIP limit; any
    other live ticket is size-gated when its seq log says so, and launchable otherwise.
    """
    res = {
        "queued": 0,
        "stale": 0,
        "launchable": 0,
        "size_gated": 0,
        "wip_held": collections.Counter(),
        "wip_reason": {},
        "counters": {},
        "queues": {},
    }
    index = tenant_index()
    for qname, qdir in (("gmktec", QUEUE_DIR), ("hp", HP_QUEUE_DIR)):
        try:
            entries = [p for p in qdir.iterdir() if p.is_file()]
        except OSError as exc:
            res["queues"][qname] = f"UNREAD ({exc})"
            continue
        res["queues"][qname] = len(entries)
        for entry in entries:
            kv = dict(re.findall(r"([\w-]+)=(\S+)", read_or_empty(entry)))
            if not kv.get("pid", "").isdigit() or not pathlib.Path(f"/proc/{kv['pid']}").exists():
                res["stale"] += 1
                continue
            res["queued"] += 1
            item = kv.get("item", "")
            if kv.get("wip-wait") == "1":
                res["wip_held"][index.get(item, "?")] += 1
            elif item and SAFE_NAME_RE.fullmatch(item) and size_gated(item):
                res["size_gated"] += 1
            else:
                res["launchable"] += 1
    newest = {}
    for path in recent_files("seq-*.log", TICKET_FRESH_S):
        for epoch, line in dated_lines(read_or_empty(path), mtime_or_none(path) or now):
            if now - epoch > TICKET_FRESH_S:
                continue
            found = COUNTER_RE.findall(line)
            hl = HL_LIVE_RE.search(line)
            if hl:
                found.append(("hl", hl.group(1)))
            for key, val in found:
                if key not in newest or epoch >= newest[key][0]:
                    newest[key] = (epoch, int(val))
            if "repo WIP full" in line:
                m = WIP_TENANT_RE.search(line)
                why = re.search(r"repo WIP full \(([^)]*)\)", line)
                if m and why:
                    res["wip_reason"][m.group(1)] = why.group(1)[:240]
    res["counters"] = {k: v for k, (_e, v) in newest.items()}
    return res


def read_cap_file(name):
    try:
        return int((CANARY / name).read_text().strip()), None
    except (OSError, ValueError) as exc:
        return None, str(exc)


def launcher_rows(factory, tickets, factory_nodes, nodes_by_name):
    rows = []
    held = sum(tickets["wip_held"].values())
    waiting = tickets["launchable"]
    queues = " ".join(f"{k}={v}" for k, v in tickets["queues"].items())
    waiting_text = (
        f"{waiting} launchable, {tickets['size_gated']} size-gated, {held} WIP-held "
        f"(of {tickets['queued']} live queued tickets; queue {queues}; {tickets['stale']} stale entries)"
    )
    if factory["fleet"] is None or factory["cap"] is None:
        rows.append(unread_row("fleet-cap", "no fleet=/cap= launcher line within the last 20 minutes"))
    else:
        binds = factory["fleet"] >= factory["cap"]
        rows.append(
            stranded_row(
                "fleet-cap", factory["cap"], factory["fleet"], binds, waiting, waiting_text,
                factory_nodes, nodes_by_name,
            )
        )
    for cap_name, (keys, covered) in HOST_CAPS.items():
        limit, err = read_cap_file(cap_name)
        if limit is None:
            rows.append(unread_row(cap_name, err))
            continue
        uses = [tickets["counters"][k] for k in keys if k in tickets["counters"]]
        if not uses:
            rows.append(unread_row(cap_name, f"limit {limit}; no {'/'.join(keys)}= use in launcher lines of the last 10 min"))
            continue
        use = max(uses)
        rows.append(
            stranded_row(
                cap_name, limit, use, use >= limit, waiting, waiting_text,
                host_scope(factory_nodes, covered), nodes_by_name,
            )
        )
    return rows


def wip_rows(tickets, factory_nodes, nodes_by_name, now):
    rows, quiet = [], 0
    # wip-act.<tenant>.lk is the launcher's lock DIRECTORY, not a reading.
    files = sorted(p for p in CANARY.glob("wip-act.*") if p.is_file() and p.suffix != ".lk")
    if not files:
        return [unread_row("dispatcher wip_cap", f"no wip-act.* file in {CANARY}")]
    for path in files:
        tenant = path.name.removeprefix("wip-act.")
        parts = read_or_empty(path).split()
        if len(parts) < 3 or not all(p.isdigit() for p in parts[:3]):
            rows.append(unread_row(f"wip_cap {tenant}", f"unexpected content {parts[:3]}"))
            continue
        stamp, active, cap = (int(p) for p in parts[:3])
        waiting = tickets["wip_held"].get(tenant, 0)
        if active == 0 and waiting == 0:
            quiet += 1
            continue
        age = fmt_age(max(0, now - stamp))
        text = f"{waiting} WIP-held queued ticket(s)"
        if waiting and active < cap:
            text += " while use is below the numeric cap"
        if tenant in tickets["wip_reason"]:
            text += f"; launcher says repo WIP full ({tickets['wip_reason'][tenant]})"
        # The launcher's own "repo WIP full" verdict (a HELD/canary marker can set it below
        # the numeric cap) counts as the limit reached: it is what holds the tickets.
        binds = active >= cap or tenant in tickets["wip_reason"]
        rows.append(
            stranded_row(
                f"wip_cap {tenant} (read {age} ago)", cap, active, binds, waiting,
                text, factory_nodes, nodes_by_name,
            )
        )
    if tickets["wip_held"].get("?"):
        rows.append(unread_row("wip_cap tenant", f"{tickets['wip_held']['?']} WIP-held ticket(s) whose item is in no wip-claimed cache"))
    if quiet:
        rows.append({"name": "wip_cap", "flagged": False, "text": f"wip_cap: {quiet} other tenant(s) at 0 active, none waiting"})
    return rows


def kueue_rows(node_labels, nodes_by_name):
    cqs, err = kube_json("clusterqueues.kueue.x-k8s.io")
    if cqs is None:
        return [unread_row("kueue ClusterQueues", err)]
    flavors, err = kube_json("resourceflavors.kueue.x-k8s.io")
    if flavors is None:
        return [unread_row("kueue ResourceFlavors", err)]
    flavor_nodes = {
        f["metadata"]["name"]: nodes_matching(node_labels, f["spec"].get("nodeLabels") or {})
        for f in flavors.get("items", [])
    }
    rows, quiet = [], 0
    for cq in cqs.get("items", []):
        name, status = cq["metadata"]["name"], cq.get("status") or {}
        pending = int(status.get("pendingWorkloads") or 0)
        if not pending and not int(status.get("admittedWorkloads") or 0):
            quiet += 1
            continue
        usage = {
            f["name"]: {r["name"]: r for r in f.get("resources") or []}
            for f in status.get("flavorsUsage") or []
        }
        for group in cq["spec"].get("resourceGroups") or []:
            for flavor in group.get("flavors") or []:
                fname, parts, binds = flavor["name"], [], False
                for res in flavor.get("resources") or []:
                    used = usage.get(fname, {}).get(res["name"], {})
                    total, borrowed = used.get("total", "0"), used.get("borrowed", "0")
                    quota = res.get("nominalQuota")
                    parts.append(f"{res['name']} {total}/{quota}" + (f" (+{borrowed} borrowed)" if borrowed not in ("0", 0) else ""))
                    if qty(total) is not None and qty(quota) is not None and qty(total) >= qty(quota):
                        binds = True
                rows.append(
                    stranded_row(
                        f"kueue {name}/{fname}", "nominal", ", ".join(parts), binds, pending,
                        f"{pending} pending workload(s) in the ClusterQueue",
                        flavor_nodes.get(fname, []), nodes_by_name,
                    )
                )
    if quiet:
        rows.append({"name": "kueue", "flagged": False, "text": f"kueue: {quiet} other ClusterQueue(s) with no admitted or pending workload"})
    return rows


def arc_runner_ages(now):
    """({scale set: [age_s of each pending EphemeralRunner]}, None), or (None, reason).

    Pending is ARC's own reading: phase Pending or not yet set. An unparseable
    creationTimestamp counts as older than the startup window.
    """
    doc, err = kube_json(f"ephemeralrunners.actions.github.com -n {ARC_NS} --request-timeout=20s")
    if doc is None:
        return None, err
    ages = collections.defaultdict(list)
    for r in doc.get("items", []):
        meta = r.get("metadata") or {}
        if (r.get("status") or {}).get("phase") not in (None, "", "Pending"):
            continue
        owner = (meta.get("labels") or {}).get("actions.github.com/scale-set-name")
        try:
            born = datetime.datetime.strptime(meta.get("creationTimestamp", ""), "%Y-%m-%dT%H:%M:%SZ")
            age = now - born.replace(tzinfo=datetime.UTC).timestamp()
        except ValueError:
            age = float("inf")
        ages[owner].append(age)
    return ages, None


def arc_rows(node_labels, nodes_by_name):
    sets, err = kube_json(f"autoscalingrunnersets.actions.github.com -n {ARC_NS}")
    if sets is None:
        return [unread_row("ARC scale sets", err)]
    runner_ages, ages_err = arc_runner_ages(time.time())
    lqs, err = kube_json(f"localqueues.kueue.x-k8s.io -n {ARC_NS}")
    lq_pending = {}
    if lqs is None:
        lq_err = err
    else:
        lq_err = None
        lq_pending = {q["metadata"]["name"]: int((q.get("status") or {}).get("pendingWorkloads") or 0) for q in lqs.get("items", [])}
    rows, quiet = [], 0
    for s in sets.get("items", []):
        name, spec, st = s["metadata"]["name"], s.get("spec") or {}, s.get("status") or {}
        tmpl = spec.get("template") or {}
        tspec = tmpl.get("spec") or {}
        lq = ((tmpl.get("metadata") or {}).get("labels") or {}).get("kueue.x-k8s.io/queue-name")
        current, pend_r = int(st.get("currentRunners") or 0), int(st.get("pendingEphemeralRunners") or 0)
        q_pend = lq_pending.get(lq, 0) if lq else 0
        if not current and not pend_r and not q_pend:
            quiet += 1
            continue
        terms = (
            ((tspec.get("affinity") or {}).get("nodeAffinity") or {}).get("requiredDuringSchedulingIgnoredDuringExecution") or {}
        ).get("nodeSelectorTerms")
        covered = nodes_matching(node_labels, tspec.get("nodeSelector") or {}, terms)
        maxr = spec.get("maxRunners")
        binds = maxr is not None and current >= int(maxr)
        lq_text = f"queue {lq} pending UNREAD ({lq_err})" if lq and lq_err else f"{q_pend} pending in {lq or 'no queue'}"
        if runner_ages is None:
            stuck = pend_r
            pend_text = f"{pend_r} pending runner(s) (runner ages UNREAD: {str(ages_err)[:120]})"
        else:
            ages = runner_ages.get(name, [])
            stuck = sum(1 for a in ages if a > STRANDED_ARC_STARTUP_S)
            starting = len(ages) - stuck
            pend_text = f"{stuck} pending runner(s) older than {STRANDED_ARC_STARTUP_S}s"
            if starting:
                pend_text += f", {starting} starting"
        rows.append(
            stranded_row(
                f"arc {name}", maxr, f"{current} runners ({st.get('runningEphemeralRunners', 0)} running)", binds,
                stuck + q_pend, f"{pend_text}, {lq_text}; GitHub-side queue not visible",
                covered, nodes_by_name,
            )
        )
    if quiet:
        rows.append({"name": "arc", "flagged": False, "text": f"arc: {quiet} other scale set(s) with no runner and nothing pending"})
    return rows


def quota_rows(tickets, factory_nodes, nodes_by_name):
    doc, err = kube_json(f"resourcequota -n {FACTORY_NS}")
    if doc is None:
        return [unread_row(f"ResourceQuota {FACTORY_NS}", err)]
    if not doc.get("items"):
        return [unread_row(f"ResourceQuota {FACTORY_NS}", "no ResourceQuota object in the namespace")]
    rows = []
    for q in doc["items"]:
        st = q.get("status") or {}
        hard, used = st.get("hard") or {}, st.get("used") or {}
        parts, binds = [], False
        for res in sorted(hard):
            parts.append(f"{res} {used.get(res, '?')}/{hard[res]}")
            u, h = qty(used.get(res, "")), qty(hard[res])
            if u is not None and h is not None and u >= h:
                binds = True
        waiting = tickets["launchable"]
        rows.append(
            stranded_row(
                f"ResourceQuota {FACTORY_NS}/{q['metadata']['name']}", "hard", ", ".join(parts), binds, waiting,
                f"{waiting} launchable launcher ticket(s)", factory_nodes, nodes_by_name,
            )
        )
    return rows


def read_stranded(nodes, factory):
    """Every cap and quota: limit, use, waiting work, covered nodes' idle; FLAGGED when stranded."""
    now = time.time()
    nodes_by_name = {n["name"]: n for n in nodes}
    tickets = read_launcher_tickets(now)
    nodes_doc, err = kube_json("nodes")
    if nodes_doc is None:
        node_labels = {}
        rows = [unread_row("k3s node labels", f"{err}; no node counts as covered")]
    else:
        node_labels = {n["metadata"]["name"]: n["metadata"].get("labels") or {} for n in nodes_doc.get("items", [])}
        rows = []
    # Factory lines cover only nodes a factory sandbox pod can be placed on (see the docstring).
    factory_nodes = factory_scope(nodes_doc, err)
    rows += launcher_rows(factory, tickets, factory_nodes, nodes_by_name)
    rows += wip_rows(tickets, factory_nodes, nodes_by_name, now)
    rows += quota_rows(tickets, factory_nodes, nodes_by_name)
    rows += kueue_rows(node_labels, nodes_by_name) if node_labels else [unread_row("kueue", "node labels unread")]
    rows += arc_rows(node_labels, nodes_by_name) if node_labels else [unread_row("arc", "node labels unread")]
    return {"threshold_idle_pct": STRANDED_IDLE_PCT, "rows": rows}


def render_stranded(stranded):
    out(
        f"\nSTRANDED-CAPACITY (FLAGGED = at its limit while work waits and a covered node "
        f"reads idle above {stranded['threshold_idle_pct']}%; see .ai/coordinator-duties.md section 10)"
    )
    for row in stranded["rows"]:
        out(f"  {row['text']}")


def build_flags(nodes, cluster, factory, unticketed, stranded):
    flags = []
    live = [n for n in nodes if n["reachable"] and n["name"] != "vps"]
    for n in nodes:
        if not n["reachable"]:
            flags.append(f"UNREACHABLE {n['name']}: " + " ; ".join(n["errors"]))
    sat = [n for n in live if (n["psi_some_avg60"] or 0) > PSI_SATURATED_MIN]
    for n in live:
        idle_low = (n["psi_some_avg60"] is not None and n["psi_some_avg60"] < PSI_IDLE_MAX) or (
            n["idle_pct"] is not None and n["idle_pct"] > IDLE_PCT_MIN
        )
        if idle_low and sat and n not in sat:
            flags.append(
                f"IDLE-WHILE-SATURATED {n['name']} (PSI60 {n['psi_some_avg60']}, idle "
                f"{n['idle_pct']}%) while "
                + ", ".join(f"{s['name']} PSI60 {s['psi_some_avg60']}" for s in sat)
            )
    if not cluster["reachable"]:
        flags.append(f"UNREACHABLE k3s API via {K3S_SERVER}: {cluster['error']}")
    for ns, count in sorted(cluster["pending"].items()):
        flags.append(f"PENDING {count} pod(s) in namespace {ns}")
    f, c, q = factory["fleet"], factory["cap"], factory["queue_depth"]
    if f is None:
        flags.append("FACTORY no fleet=/cap= line within the last 20 minutes (launcher silent?)")
    elif factory["cap_mismatch"]:
        flags.append(
            f"CAP-MISMATCH no recent petri line with cap={factory['fleet_cap_file']} "
            f"(fleet-cap file); newest line says fleet={f} cap={c} from {factory['fleet_log']}"
        )
    elif c is not None and f < c and q:
        flags.append(f"BELOW-CAP fleet={f} cap={c} with {q} ticket(s) queued")
    for u in unticketed["unreadable"]:
        flags.append(f"UNREADABLE {u['repo']}: {u['error']}")
    if unticketed["items"]:
        n = len(unticketed["items"])
        flags.append(f"UNTICKETED-READY {n} item(s) ready >30m with no ticket (see section)")
    for row in stranded["rows"]:
        if row["flagged"]:
            flags.append(f"STRANDED-CAPACITY {row['name']} (see section)")
    return flags


def render(nodes, cluster, factory, unticketed, stranded, flags):
    ns_all = sorted({ns for v in cluster["pods"].values() for ns in v})
    out(f"FLEET UTILIZATION {datetime.datetime.now(datetime.UTC):%Y-%m-%dT%H:%M:%SZ}")
    out(
        f"{'node':20}{'cores':>6}{"load(1/5/15)":>22}{'PSI10':>7}{'PSI60':>7}"
        f"{'idle%':>7}{'memGiB':>8}{'swapGiB':>8}  live pods(by ns)"
    )
    for n in nodes:
        if not n["reachable"]:
            out(f"{n['name']:20}  UNREACHABLE")
            continue
        pods = cluster["pods"].get(n["name"], {})
        pod_s = " ".join(f"{k}={v}" for k, v in sorted(pods.items())) or "-"
        out(
            f"{n['name']:20}{n['cores']:>6}{n["load"]:>22}{n['psi_some_avg10']:>7}"
            f"{n['psi_some_avg60']:>7}{n['idle_pct'] if n['idle_pct'] is not None else '?':>7}"
            f"{n['mem_avail_gib']:>8}{n['swap_used_gib']:>8}  {pod_s}"
        )
    render_stranded(stranded)
    out(f"\nCluster namespaces seen: {', '.join(ns_all) or '-'}")
    out(
        "Pending pods: "
        + (", ".join(f"{k}={v}" for k, v in sorted(cluster["pending"].items())) or "none")
    )
    out("Quota:")
    for q in cluster["quota"]:
        out(f"  {q['namespace']}/{q['name']}: {q['usage']}")
    out(
        f"\nFactory: fleet={factory['fleet']} cap={factory['cap']} "
        f"(petri gmktec, line age {factory['fleet_line_age_s']}s, {factory['fleet_log']}) fleet-cap-file={factory['fleet_cap_file']} "
        f"queue-depth={factory['queue_depth']}"
    )
    for log, o in sorted(factory["other_families"].items()):
        label = "stale, age" if o["stale"] else "age"
        out(f"  other launcher family {log}: fleet={o['fleet']} cap={o['cap']} ({label} {o['age_s']}s)")
    out(f"LAUNCH lines, last 30 min: {len(factory['launches_30m'])}")
    for line in factory["launches_30m"][-5:]:
        out(f"  {line}")
    tenants = ", ".join(f"{t['repo']}={t['ready']}" for t in unticketed["tenants"]) or "-"
    out("\nUNTICKETED-READY (non-epic READY >30m, no fresh (<30m) seq log / queue entry / 6h capture-argv)")
    out(f"  tenants read (ready count): {tenants}")
    for u in unticketed["unreadable"]:
        out(f"  UNREADABLE {u['repo']}: {u['error']}")
    for it in unticketed["items"]:
        cause = f"  | {it['cause']}" if it.get("cause") else ""
        out(f"  {it['repo']:34} {it['id']:40} {it['age']:>8}  {it['title']}{cause}")
    if not unticketed["items"]:
        out("  none")
    else:
        c = unticketed["causes"]
        out(
            f"  causes read for {c['read']} of {c['flagged']} flagged: {c['held']} HELD, "
            f"{c['blocked']} BLOCKED, {c['no_recorded_cause']} no recorded cause"
        )
        if c["skipped"]:
            why = c["errors"][0] if c["errors"] else f"section budget {READY_SECTION_TIMEOUT_S}s"
            out(f"  causes SKIPPED for {c['skipped']} flagged row(s), unread, not uncaused: {why}")
    out("\nFLAGS")
    for flag in flags or ["none"]:
        out(f"  {flag}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="emit one JSON document")
    ap.add_argument(
        "--stranded-only", action="store_true", help="read and print only the STRANDED-CAPACITY section"
    )
    args = ap.parse_args()
    nodes = [probe_node(h) for h in HOSTS] + [probe_vps()]
    factory = read_factory()
    stranded = read_stranded(nodes, factory)
    if args.stranded_only:
        if args.json:
            out(json.dumps(stranded, indent=2))
        else:
            render_stranded(stranded)
        return 0
    cluster = read_cluster()
    unticketed = read_unticketed_ready()
    flags = build_flags(nodes, cluster, factory, unticketed, stranded)
    if args.json:
        out(
            json.dumps(
                {
                    "nodes": nodes,
                    "cluster": cluster,
                    "factory": factory,
                    "unticketed_ready": unticketed,
                    "stranded_capacity": stranded,
                    "flags": flags,
                },
                indent=2,
            )
        )
    else:
        render(nodes, cluster, factory, unticketed, stranded, flags)
    return 0


if __name__ == "__main__":
    sys.exit(main())
PY
