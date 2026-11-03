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
error, never skipped. Nothing here mutates: only cat / mpstat / kubectl get.
"""

import argparse
import collections
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
    }
    try:
        fac["fleet_cap_file"] = int((CANARY / "fleet-cap").read_text().strip())
    except (OSError, ValueError):
        fac["fleet_cap_file"] = None
    best = newest_fleet_line(now)
    if best:
        fac["fleet_line_age_s"], fac["fleet"], fac["cap"] = best
    try:
        fac["queue_depth"] = sum(1 for p in QUEUE_DIR.iterdir() if p.is_file())
    except OSError:
        fac["queue_depth"] = None
    fac["launches_30m"] = recent_launches(now)
    return fac


def newest_fleet_line(now):
    best = None
    for path in recent_files("seq-*.log", FLEET_WINDOW_S):
        for line in path.read_text(errors="replace").splitlines():
            m = re.match(r"(\d\d:\d\d:\d\d) .*fleet=(\d+) cap=(\d+)", line)
            if not m:
                continue
            age = seconds_ago(m.group(1), now)
            if age <= FLEET_WINDOW_S and (best is None or age < best[0]):
                best = (age, int(m.group(2)), int(m.group(3)))
    return best


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


def build_flags(nodes, cluster, factory):
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
    elif c is not None and f < c and q:
        flags.append(f"BELOW-CAP fleet={f} cap={c} with {q} ticket(s) queued")
    return flags


def render(nodes, cluster, factory, flags):
    ns_all = sorted({ns for v in cluster["pods"].values() for ns in v})
    out(f"FLEET UTILIZATION {datetime.datetime.now(datetime.UTC):%Y-%m-%dT%H:%M:%SZ}")
    out(
        f"{'node':20}{'cores':>6}{"load(1/5/15)":>22}{'PSI10':>7}{'PSI60':>7}"
        f"{'idle%':>7}{'memGiB':>8}{'swapGiB':>8}  pods(by ns)"
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
        f"(line age {factory['fleet_line_age_s']}s) fleet-cap-file={factory['fleet_cap_file']} "
        f"queue-depth={factory['queue_depth']}"
    )
    out(f"LAUNCH lines, last 30 min: {len(factory['launches_30m'])}")
    for line in factory["launches_30m"][-5:]:
        out(f"  {line}")
    out("\nFLAGS")
    for flag in flags or ["none"]:
        out(f"  {flag}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="emit one JSON document")
    args = ap.parse_args()
    nodes = [probe_node(h) for h in HOSTS] + [probe_vps()]
    cluster, factory = read_cluster(), read_factory()
    flags = build_flags(nodes, cluster, factory)
    if args.json:
        out(
            json.dumps(
                {"nodes": nodes, "cluster": cluster, "factory": factory, "flags": flags}, indent=2
            )
        )
    else:
        render(nodes, cluster, factory, flags)
    return 0


if __name__ == "__main__":
    sys.exit(main())
PY
