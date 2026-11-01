# Idle-slot audit — the driver's queue measurement

Recorded 2026-10-16 after the maintainer's ruling (~15:5xZ) that the driver had
failed its one job: nine hp slots sat idle for five hours while four priority-set
items were dispatchable, because three successive driver sessions repeated a
handoff's "nothing can use the slots" instead of measuring the queue.

## What it does

Reads full `bd list --status all --json` dumps of the three ledger tenants
(dev-tooling, orchestrator, livespec) and the live board of both hp Fabro
servers, enumerates every non-closed child of every priority epic (union of the
`parent` field, the dotted-id hierarchy and the `parent-child` edge, or an
explicit id list where an epic's children live in another tenant), and
classifies each as: RUNNING, DISPATCHABLE NOW, STALE EDGE (blocked only on items
already in acceptance/active, i.e. merged and landed but not closed), NEEDS
CAPTURE/ACCEPT, NEEDS APPROVAL, UNADMITTED (backlog), HOST-ONLY (labelled
`factory-safety:*` or `acceptance:human-only`), POST-RUN or BLOCKED. The last
line is the finding: idle slots against dispatchable-or-stale-edge items.

It never dispatches. The driver reads it, issues GOs to owners by name, or
records each hold with a reason and a reconsider time.

## How to run it

```bash
S=<scratch dir>
cd /data/projects/livespec-dev-tooling && /usr/local/bin/with-livespec-env.sh -- bd list --status all --limit 0 --json > $S/dt.json
(cd /data/projects/livespec-orchestrator-beads-fabro && /usr/local/bin/with-livespec-env.sh -- bd list --status all --limit 0 --json) > $S/orch.json
(cd /data/projects/livespec && /usr/local/bin/with-livespec-env.sh -- bd list --status all --limit 0 --json) > $S/ls.json
PF=/home/ubuntu/.local/state/fabro-currency/carrier-petri-v0.382-adeefec4c/fabro
{ fabro ps -a --server https://hp-xubuntu.perch-rudd.ts.net:32276 | awk 'NR>1 && $1 ~ /^01M/ {print 32276, $1, $3, $NF}';
  $PF   ps -a --server https://hp-xubuntu.perch-rudd.ts.net:32278 | awk 'NR>1 && $1 ~ /^01M/ {print 32278, $1, $3, $NF}'; } > $S/board.txt
python3 -I $S/idle_slot_audit.py --board $S/board.txt \
  --tenant dev-tooling=$S/dt.json --tenant orchestrator=$S/orch.json --tenant livespec=$S/ls.json \
  --epic "dev-tooling:petri=<comma-separated dev-tooling child ids of bd-ib-fyozyd>" \
  --epic "orchestrator:fabro-currency=bd-ib-6tcjfx" --epic "orchestrator:k8s-sandbox-backend=bd-ib-nmuyjc" \
  --epic "orchestrator:k3s-on-gmktec-vps=bd-ib-izthji,bd-ib-izthji" \
  --epic "livespec:factory-worker-nodes=livespec-sqvj7p" --epic "livespec:k3s-on-gmktec=livespec-sab5gn" \
  --epic "dev-tooling:factory-worker-nodes(dev-tooling)=<its dev-tooling child ids>"
```

Save the script below to `$S/idle_slot_audit.py` first. It is journaled here
rather than committed as `.py` because a first-party Python file in this repo
is subject to the full lint and semantic-role regime, which a driver-side
measurement script does not need to satisfy to be reproducible.

First run, 2026-10-16 15:56Z: idle slots 9; dispatchable 3 (m4cspa, pe2dxk,
izthji); stale edge 1 (jtl5ir on xi63mq); needs approval 2 (p4clqz, 4on5pg);
unadmitted 5; needs capture 16; host-only 13; idle slot-hours since 11:00Z ~45.

## The script

```python
#!/usr/bin/env python3
"""Idle-slot audit for the gitops-fleet-capacity-monitoring driver.

Reads full `bd list --status all --json` dumps of the three tenants plus the
live board and classifies every non-closed child of every priority epic so
the driver can see what is dispatchable while slots sit idle. Rule: a
resume or tick entry written while two or more slots are free MUST carry
this output. The classification is mechanical; it never dispatches.

Usage:
  idle_slot_audit.py --board live.txt \
      --tenant dev-tooling=dt.json --tenant orchestrator=orch.json \
      --tenant livespec=ls.json \
      --epic dev-tooling:petri=livespec-dev-tooling-{p4clqz,...} ...

Epics whose children live in another tenant (petri's bd-ib-fyozyd has
dev-tooling children) are passed as explicit child-id lists.
"""
from __future__ import annotations

import argparse
import json
import sys

HOST_LABELS = (
    "factory-safety:mutates-host-machinery",
    "factory-safety:needs-privileged-host",
    "acceptance:human-only",
)
LIVE = {"running", "starting", "pending", "queued", "runnable"}


def load(path: str) -> dict[str, dict]:
    with open(path) as fh:
        return {d["id"]: d for d in json.load(fh)}


def blockers(item: dict, by: dict[str, dict]) -> list[tuple[str, str]]:
    out = []
    for dep in item.get("dependencies") or []:
        kind = dep.get("type") or dep.get("dependency_type")
        other = dep.get("depends_on_id") or dep.get("id")
        if kind == "blocks" and other:
            out.append((other, by.get(other, {}).get("status", "?")))
    return [(o, s) for o, s in out if s != "closed"]


def children(epic: str, by: dict[str, dict]) -> set[str]:
    kids = set()
    for d in by.values():
        if d.get("parent") == epic or d["id"].startswith(epic + "."):
            kids.add(d["id"])
        for dep in d.get("dependencies") or []:
            kind = dep.get("type") or dep.get("dependency_type")
            other = dep.get("depends_on_id") or dep.get("id")
            if kind == "parent-child" and other == epic:
                kids.add(d["id"])
    return kids


def classify(item: dict, by: dict[str, dict], live_items: set[str]) -> tuple[str, str]:
    status = item["status"]
    labels = item.get("labels") or []
    host = any(l in labels for l in HOST_LABELS)
    blk = blockers(item, by)
    blk_s = ", ".join(f"{o[-6:]}:{s}" for o, s in blk) or "-"
    if item["id"] in live_items:
        return "RUNNING", blk_s
    if status == "closed":
        return "CLOSED", blk_s
    if status in ("active", "acceptance") and not blk:
        return ("POST-RUN (merge/close/capture owed)" if status == "active" else "NEEDS CAPTURE/ACCEPT"), blk_s
    if host:
        return "HOST-ONLY", blk_s
    if status == "ready" and not blk:
        return "DISPATCHABLE NOW", blk_s
    if status == "pending-approval":
        return ("NEEDS APPROVAL" if not blk else "NEEDS APPROVAL + blocked"), blk_s
    if status == "backlog":
        return "UNADMITTED (backlog)", blk_s
    if blk and all(s in ("acceptance", "active") for _, s in blk):
        return "STALE EDGE? (blockers merged/landed, not closed)", blk_s
    if blk:
        return "BLOCKED", blk_s
    return status.upper(), blk_s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, help="file: lines '<port> <run-id> <status> <goal>'")
    ap.add_argument("--tenant", action="append", required=True, help="name=path.json")
    ap.add_argument("--epic", action="append", required=True,
                    help="tenant:label=epic-id  OR  tenant:label=id1,id2,... (explicit children)")
    ap.add_argument("--cap", type=int, default=10, help="slots on :32276")
    args = ap.parse_args()

    tenants = {n: load(p) for n, p in (t.split("=", 1) for t in args.tenant)}
    live_items: set[str] = set()
    live_count = 0
    with open(args.board) as fh:
        for line in fh:
            parts = line.split()
            if len(parts) >= 4 and parts[2] in LIVE:
                live_count += 1
                live_items.add(parts[-1])
    free = max(args.cap - live_count, 0)
    print(f"BOARD live={live_count} free_slots(:32276 cap {args.cap})={free}")

    counts: dict[str, int] = {}
    for spec in args.epic:
        tenant_label, target = spec.split("=", 1)
        tenant, label = tenant_label.split(":", 1)
        by = tenants[tenant]
        ids = set(target.split(",")) if "," in target or target not in by else children(target, by)
        if target in by and "," not in target:
            ids = children(target, by)
        print(f"=== {label} ({tenant}) children={len(ids)}")
        for cid in sorted(ids):
            d = by.get(cid)
            if d is None:
                print(f"  {cid}: NOT IN TENANT")
                continue
            if d["status"] == "closed":
                continue
            cls, blk = classify(d, by, live_items)
            counts[cls] = counts.get(cls, 0) + 1
            print(f"  {cid[-7:]:8} {d['status']:16} {cls:44} blockers={blk} | {d['title'][:60]}")
    print("=== SUMMARY")
    for k in sorted(counts):
        print(f"  {counts[k]:3} {k}")
    disp = counts.get("DISPATCHABLE NOW", 0) + counts.get("STALE EDGE? (blockers merged/landed, not closed)", 0)
    print(f"IDLE SLOTS={free} DISPATCHABLE-OR-STALE-EDGE={disp} "
          f"{'<<< FINDING: idle slots with dispatchable work' if free and disp else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```
