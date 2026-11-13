# Measurement scripts (reference copies)

These are the throwaway scripts the notes' numbers came from, kept as text so the method can be re-run. Each needs `gh` (GraphQL only) or the credential wrapper. They are not product code.

## merged-green-baseline.py

```python
import collections
import datetime
import json
import subprocess
import sys

hours = int(sys.argv[1])
out = sys.argv[2]
now = datetime.datetime.now(datetime.timezone.utc)
since = (now - datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
Q = """query($o:String!,$n:String!,$since:GitTimestamp!,$c:String){rateLimit{cost remaining} repository(owner:$o,name:$n){defaultBranchRef{name target{... on Commit{history(since:$since,first:100,after:$c){pageInfo{hasNextPage endCursor} nodes{oid committedDate associatedPullRequests(first:2){nodes{number mergedAt}} checkSuites(first:20){nodes{conclusion status workflowRun{event workflow{name}}}}}}}}}}}"""
res = {"since": since, "until": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "hours": hours, "repos": {}}
for repo in sys.argv[3:]:
    nodes = []
    c = None
    cost = 0
    while True:
        a = [
            "gh",
            "api",
            "graphql",
            "-f",
            "query=" + Q,
            "-f",
            "o=thewoolleyman",
            "-f",
            "n=" + repo,
            "-f",
            "since=" + since,
        ]
        if c:
            a += ["-f", "c=" + c]
        p = subprocess.run(a, capture_output=True, text=True, check=False)
        if p.returncode:
            print(repo, "ERR", p.stderr[:200])
            break
        d = json.loads(p.stdout)
        cost += d["data"]["rateLimit"]["cost"]
        h = d["data"]["repository"]["defaultBranchRef"]["target"]["history"]
        nodes += h["nodes"]
        if not h["pageInfo"]["hasNextPage"]:
            break
        c = h["pageInfo"]["endCursor"]
    nodes.reverse()  # oldest first

    def run(n):
        s = [
            x
            for x in n["checkSuites"]["nodes"]
            if x["workflowRun"]
            and x["workflowRun"]["event"] == "push"
            and x["workflowRun"]["workflow"]["name"] == "CI"
        ]
        return (s[0]["conclusion"] or s[0]["status"]) if s else None

    head = {}  # pr -> index of its last commit
    for i, n in enumerate(nodes):
        for p in n["associatedPullRequests"]["nodes"]:
            if p["mergedAt"] and p["mergedAt"] >= since:
                head[p["number"]] = i
    strict = collections.Counter()
    cov = collections.Counter()
    for num, i in head.items():
        r = run(nodes[i])
        strict[r or "NO_RUN"] += 1
        v = "UNVERIFIED_YET"
        for j in range(i, len(nodes)):
            rj = run(nodes[j])
            if rj in ("SUCCESS", "FAILURE", "TIMED_OUT", "STARTUP_FAILURE"):
                v = rj
                break
        cov[v] += 1
    n = len(head)
    res["repos"][repo] = {
        "master_commits": len(nodes),
        "merged_prs": n,
        "strict": dict(strict),
        "covered": dict(cov),
        "merged_per_h": round(n / hours, 3),
        "strict_green_per_h": round(strict["SUCCESS"] / hours, 3),
        "covered_green_per_h": round(cov["SUCCESS"] / hours, 3),
        "gql_cost": cost,
    }
    print(repo, json.dumps(res["repos"][repo]))
json.dump(res, open(out, "w"), indent=1)
```

## merged-pr-sources.py

```python
import collections
import datetime
import json
import re
import subprocess
import sys

since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=168)).strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)
Q = """query($o:String!,$n:String!,$c:String){repository(owner:$o,name:$n){pullRequests(states:MERGED,orderBy:{field:UPDATED_AT,direction:DESC},first:100,after:$c){pageInfo{hasNextPage endCursor} nodes{number mergedAt updatedAt createdAt headRefName author{login} labels(first:10){nodes{name}}}}}}"""
out = {}
for repo in sys.argv[1:]:
    prs = []
    c = None
    while True:
        a = ["gh", "api", "graphql", "-f", "query=" + Q, "-f", "o=thewoolleyman", "-f", "n=" + repo]
        if c:
            a += ["-f", "c=" + c]
        d = json.loads(subprocess.run(a, capture_output=True, text=True, check=True).stdout)[
            "data"
        ]["repository"]["pullRequests"]
        prs += d["nodes"]
        if not d["pageInfo"]["hasNextPage"] or d["nodes"][-1]["updatedAt"] < since:
            break
        c = d["pageInfo"]["endCursor"]
    prs = [p for p in prs if p["mergedAt"] >= since]
    pref = collections.Counter(re.split(r"[/_-]", p["headRefName"])[0] for p in prs)
    auth = collections.Counter((p["author"] or {}).get("login") for p in prs)
    import statistics

    lead = [
        (
            datetime.datetime.fromisoformat(p["mergedAt"].replace("Z", "+00:00"))
            - datetime.datetime.fromisoformat(p["createdAt"].replace("Z", "+00:00"))
        ).total_seconds()
        / 60
        for p in prs
    ]
    out[repo] = {
        "n": len(prs),
        "prefix": pref.most_common(12),
        "author": auth.most_common(6),
        "open_to_merge_min_p50": round(statistics.median(lead), 1),
        "p90": round(sorted(lead)[int(len(lead) * 0.9)], 1),
    }
    print(repo, json.dumps(out[repo]))
    json.dump(prs, open(sys.argv[0].replace("prsrc.py", f"prs7d-{repo}.json"), "w"))
```

## master-red-causes.py

```python
import collections
import datetime
import json
import subprocess
import sys

since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=168)).strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)
Q = """query($o:String!,$n:String!,$since:GitTimestamp!,$c:String){repository(owner:$o,name:$n){defaultBranchRef{target{... on Commit{history(since:$since,first:50,after:$c){pageInfo{hasNextPage endCursor} nodes{oid committedDate checkSuites(first:20){nodes{conclusion workflowRun{event workflow{name}} checkRuns(first:30,filterBy:{conclusions:[FAILURE,TIMED_OUT]}){nodes{name}}}}}}}}}}}"""
for repo in sys.argv[1:]:
    c = None
    jobs = collections.Counter()
    n = 0
    days = collections.Counter()
    while True:
        a = [
            "gh",
            "api",
            "graphql",
            "-f",
            "query=" + Q,
            "-f",
            "o=thewoolleyman",
            "-f",
            "n=" + repo,
            "-f",
            "since=" + since,
        ]
        if c:
            a += ["-f", "c=" + c]
        p = subprocess.run(a, capture_output=True, text=True, check=False)
        if p.returncode:
            print("ERR", p.stderr[:300])
            break
        h = json.loads(p.stdout)["data"]["repository"]["defaultBranchRef"]["target"]["history"]
        for x in h["nodes"]:
            for s in x["checkSuites"]["nodes"]:
                if (
                    s["workflowRun"]
                    and s["workflowRun"]["event"] == "push"
                    and s["workflowRun"]["workflow"]["name"] == "CI"
                    and s["conclusion"] == "FAILURE"
                ):
                    n += 1
                    days[x["committedDate"][:10]] += 1
                    names = sorted({r["name"] for r in s["checkRuns"]["nodes"]})
                    jobs[" + ".join(names) or "(no failed job listed)"] += 1
        if not h["pageInfo"]["hasNextPage"]:
            break
        c = h["pageInfo"]["endCursor"]
    print(repo, "failed master CI runs 7d:", n, "by day", sorted(days.items()))
    for k, v in jobs.most_common(12):
        print("  ", v, k[:200])
```

## inventory-dump.py

```python
import json
import subprocess
import sys
from pathlib import Path

W = Path.home() / "workspace"
out = {}
for repo in sorted(p.name for p in W.iterdir() if (p / ".beads").is_dir()):
    r = W / repo
    subprocess.run(
        ["git", "-C", str(r), "pull", "-q", "--ff-only"], capture_output=True, check=False
    )
    p = subprocess.run(
        [
            "/usr/local/bin/with-livespec-env.sh",
            "--",
            "bd",
            "list",
            "--status",
            "all",
            "--limit",
            "0",
            "--json",
        ],
        cwd=r,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        items = json.loads(p.stdout)
    except Exception:
        out[repo] = {"error": (p.stderr or p.stdout)[:300]}
        continue
    byid = {i["id"]: i for i in items}
    plans = {}
    pd = r / "plan"
    slugs = (
        sorted(d.name for d in pd.iterdir() if d.is_dir() and d.name != "archive")
        if pd.is_dir()
        else []
    )
    for s in slugs:
        a = pd / s / "associated_work_item_id"
        eid = a.read_text().strip() if a.exists() else None
        e = byid.get(eid)
        kids = []
        if eid:
            for i in items:
                if i["id"] == eid:
                    continue
                par = i.get("parent") == eid or any(
                    d.get("depends_on_id") == eid and d.get("type") == "parent-child"
                    for d in i.get("dependencies", []) or []
                )
                if par or i["id"].startswith(eid + "."):
                    kids.append(
                        {
                            "id": i["id"],
                            "status": i.get("status"),
                            "title": i.get("title"),
                            "type": i.get("issue_type"),
                        }
                    )
        md = (e or {}).get("metadata") or {}
        na = md.get("next_action")
        plans[s] = {
            "epic": eid,
            "found": bool(e),
            "status": (e or {}).get("status"),
            "title": (e or {}).get("title"),
            "next_action": na,
            "last_session": md.get("last_session"),
            "updated": (e or {}).get("updated_at"),
            "children_total": len(kids),
            "open_children": [k for k in kids if k["status"] != "closed"],
            "research": sorted(x.name for x in (pd / s / "research").glob("*"))
            if (pd / s / "research").is_dir()
            else [],
        }
    out[repo] = {"n_items": len(items), "plans": plans}
json.dump(out, open(sys.argv[1], "w"), indent=1)
for repo, v in out.items():
    if "error" in v:
        print(repo, "ERROR", v["error"])
        continue
    print(f"== {repo} items={v['n_items']} plans={len(v['plans'])}")
    for s, p in v["plans"].items():
        na = p["next_action"]
        k = (na or {}).get("kind") if isinstance(na, dict) else str(na)[:20]
        print(
            f"  {s} | {p['epic']} | {p['status']} | kids {len(p['open_children'])}/{p['children_total']} open | na={k} | upd={str(p['updated'])[:10]}"
        )
```
