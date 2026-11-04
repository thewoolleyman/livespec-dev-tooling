#!/usr/bin/env bash
# READ-ONLY fleet utilization read for the coordinator seat. Usage: fleet-utilization.sh [--json]
# Shell entry point; the logic is embedded Python (stdlib only) so the repo's
# product-Python AST gates, which govern the package, do not apply to a script.
set -euo pipefail
exec python3 -I - "$@" <<'PY'
"""READ-ONLY fleet utilization read for the coordinator seat.

Run first every tick:  scripts/coordinator/fleet-utilization.sh [--json]

Reports each execution node's real utilization (PSI, idle, memory), the
k3s cluster's pods / pending / quota, and the factory's fleet-vs-cap state,
then FLAGS an idle node beside a saturated one. Saturation is judged from CPU
PSI and mpstat idle, never from load average (see
.ai/ci-node-capacity-reads.md). Every ssh has a ConnectTimeout and an overall
timeout; a host that fails every candidate user is reported UNREACHABLE with the
error, never skipped. Nothing here mutates: only cat / mpstat / kubectl get / bd list.

The UNTICKETED-READY section reads every livespec beads tenant's READY items
through the credential wrapper and flags any non-epic READY item older than
30 minutes that has no dispatcher ticket behind it (no seq-<id>.log, no queue
entry, no capture-argv in the last 6 h). A tenant whose read fails is reported
UNREADABLE, never skipped.
"""

import argparse
import collections
import concurrent.futures
import datetime
import json
import pathlib
import re
import shutil
import subprocess
import sys
import time

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
MIN_POD_COLS = 8
QUOTA_COLS = 3
SSH_BIN = shutil.which("ssh") or "ssh"
PROJECTS = pathlib.Path("/data/projects")
ENV_WRAPPER = "/usr/local/bin/with-livespec-env.sh"
READY_SECTION_TIMEOUT_S = 60
READY_STALE_S = 30 * 60
CAPTURE_WINDOW_S = 6 * 3600
TITLE_MAX = 80


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


def seconds_ago(hhmmss, now):
    """Seconds between a bare HH:MM:SS (UTC) stamp and now, midnight-safe."""
    h, m, s = (int(x) for x in hhmmss.split(":"))
    stamp = h * 3600 + m * 60 + s
    cur = now.hour * 3600 + now.minute * 60 + now.second
    return (cur - stamp) % 86400


def recent_files(pattern, window_s):
    cutoff = time.time() - window_s
    return [p for p in CANARY.glob(pattern) if p.stat().st_mtime >= cutoff]


def read_factory():
    now = datetime.datetime.now(datetime.UTC)
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
    petri, fac["other_families"] = split_families(rows, fac["fleet_cap_file"])
    if petri:
        fac["fleet_line_age_s"], fac["fleet"], _cap, fac["fleet_log"] = petri[0]
        fac["cap"] = fac["fleet_cap_file"]
    elif rows:
        fac["fleet_line_age_s"], fac["fleet"], fac["cap"], fac["fleet_log"] = rows[0]
        fac["cap_mismatch"] = True
    try:
        fac["queue_depth"] = sum(1 for p in QUEUE_DIR.iterdir() if p.is_file())
    except OSError:
        fac["queue_depth"] = None
    fac["launches_30m"] = recent_launches(now)
    return fac


FLEET_RE = re.compile(r"(\d\d:\d\d:\d\d) .*?fleet=(\d+)(?: cap=(\d+))?")


def fleet_lines(now):
    """Every fleet=N [cap=M] line in the window as (age, fleet, cap_or_None, log, kind)."""
    rows = []
    for path in recent_files("seq-*.log", FLEET_WINDOW_S):
        for line in path.read_text(errors="replace").splitlines():
            m = FLEET_RE.match(line)
            if not m:
                continue
            age = seconds_ago(m.group(1), now)
            if age <= FLEET_WINDOW_S:
                cap = int(m.group(3)) if m.group(3) else None
                rows.append((age, int(m.group(2)), cap, path.name))
    return sorted(rows, key=lambda r: r[0])


def split_families(rows, cap_file):
    """Petri gmktec fleet = lines whose cap equals the fleet-cap file (or a green line
    with no cap); every other cap is a different launcher family."""
    petri = [r for r in rows if r[2] is None or r[2] == cap_file]
    others = {}
    for r in rows:
        if r not in petri and r[3] not in others:
            others[r[3]] = {"age_s": r[0], "fleet": r[1], "cap": r[2]}
    return petri, others


def recent_launches(now):
    launches = []
    for path in recent_files("*", LAUNCH_WINDOW_S):
        if not path.is_file():
            continue
        for line in path.read_text(errors="replace").splitlines():
            m = re.match(r"(\d\d:\d\d:\d\d) LAUNCH ", line)
            if m and seconds_ago(m.group(1), now) <= LAUNCH_WINDOW_S:
                launches.append(line[:160])
    return sorted(set(launches), key=lambda ln: -seconds_ago(ln[:8], now))


def ready_tenants():
    """Every livespec repo under /data/projects that carries a beads tenant pointer."""
    repos = [PROJECTS / "livespec", *sorted(PROJECTS.glob("livespec-*"))]
    return [r for r in repos if (r / ".beads" / "config.yaml").is_file()]


def first_error_line(text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    real = [ln for ln in lines if not ln.lower().startswith("warning")]
    return ((real or lines or ["no output"])[0])[:200]


def read_ready(repo, timeout_s):
    """READY items of one tenant via the wrapper (`bd ready` is dead here; see CLAUDE.md)."""
    argv = [ENV_WRAPPER, "--", "bd", "list", "--status", "ready", "--limit", "0", "--json"]
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
    if not isinstance(items, list):
        return None, "unexpected JSON shape (not a list)"
    return items, None


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
    if (CANARY / f"seq-{item_id}.log").exists():
        return True
    pat = re.compile(r"(?<![\w.-])" + re.escape(item_id) + r"(?![\w.-])")
    if any(pat.search(t) for t in queued):
        return True
    cutoff = time.time() - CAPTURE_WINDOW_S
    return any(p.stat().st_mtime >= cutoff for p in CANARY.glob(f"{item_id}-r*.capture-argv"))


def fmt_age(seconds):
    m = int(seconds // 60)
    if m < 60:
        return f"{m}m"
    h, m = divmod(m, 60)
    if h < 48:
        return f"{h}h{m:02d}m"
    return f"{h // 24}d{h % 24:02d}h"


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
    result["items"].sort(key=lambda r: (r["repo"], -r["age_s"]))
    return result


def build_flags(nodes, cluster, factory, unticketed):
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
    return flags


def render(nodes, cluster, factory, unticketed, flags):
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
        out(f"  other launcher family {log}: fleet={o['fleet']} cap={o['cap']} (age {o['age_s']}s)")
    out(f"LAUNCH lines, last 30 min: {len(factory['launches_30m'])}")
    for line in factory["launches_30m"][-5:]:
        out(f"  {line}")
    tenants = ", ".join(f"{t['repo']}={t['ready']}" for t in unticketed["tenants"]) or "-"
    out("\nUNTICKETED-READY (non-epic READY >30m, no seq log / queue entry / 6h capture-argv)")
    out(f"  tenants read (ready count): {tenants}")
    for u in unticketed["unreadable"]:
        out(f"  UNREADABLE {u['repo']}: {u['error']}")
    for it in unticketed["items"]:
        out(f"  {it['repo']:34} {it['id']:40} {it['age']:>8}  {it['title']}")
    if not unticketed["items"]:
        out("  none")
    out("\nFLAGS")
    for flag in flags or ["none"]:
        out(f"  {flag}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="emit one JSON document")
    args = ap.parse_args()
    nodes = [probe_node(h) for h in HOSTS] + [probe_vps()]
    cluster, factory = read_cluster(), read_factory()
    unticketed = read_unticketed_ready()
    flags = build_flags(nodes, cluster, factory, unticketed)
    if args.json:
        out(
            json.dumps(
                {
                    "nodes": nodes,
                    "cluster": cluster,
                    "factory": factory,
                    "unticketed_ready": unticketed,
                    "flags": flags,
                },
                indent=2,
            )
        )
    else:
        render(nodes, cluster, factory, unticketed, flags)
    return 0


if __name__ == "__main__":
    sys.exit(main())
PY
