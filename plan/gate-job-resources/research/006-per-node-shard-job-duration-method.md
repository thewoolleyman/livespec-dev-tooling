# 006 - Per-node shard-job duration: the method, and the 2026-11-18 read

Owner: plan gate-job-resources (epic livespec-dev-tooling-ukoeah). Written because the hp weight-40 revert trigger
("hp median > 1.5x poweredge after 5 samples, or hp p90 > poweredge p90 after 20") had no recorded method, and the
11-14 baselines (gamingpc 12.0 n=3, gmktec 15.8 n=8, poweredge 26.0 n=10) are VOID since mxjbmi sharded per-file
coverage (50220c1db).

## Method

1. GitHub: for every non-release-please run since the window start, list jobs and take the WORK step: a name that
   starts with `just coverage-shard` (the orchestrator's four shard jobs run `just coverage-shard N 4`) or equals
   `just check-per-file-coverage` (this repository's full step). Matching on `per-file-coverage` alone is WRONG: it
   also hits the few-second "Publish this shard's coverage data" step of each orchestrator shard job. Keep
   `runner_name`, step start and end, and the job name.
2. Honeycomb (`metrics` dataset, MCP key, see `.ai/honeycomb-query-credential.md`): MAX of `k8s.pod.cpu.usage`
   broken down by `k8s.pod.name`, `k8s.node.name`, filtered to pods ending `-workflow`, in ONE-HOUR windows. A
   single wide window overflows the ~100-group cap. This maps runner pod name (minus `-workflow`) to node.
3. Join on runner pod. Keep only steps that started after the 15:03Z shard weight change, with conclusion `success`.
   Drop steps shorter than one minute (a skipped or instantly failing step is not a sample). Compare nodes only
   WITHIN one job family (orchestrator shard job, or this repository's full step): the two families do different
   work, so a pooled median compares unlike things. Print n, median, p90, min, max per node and family, and the
   unmapped count.

About 8 Honeycomb queries per read, against a budget near 100 per hour.

### Step 1 (gh.py)

```python
import json,subprocess,sys
out=[]
def g(p):
    return json.loads(subprocess.run(["gh","api","--cache","5m",p],capture_output=True,text=True,check=True).stdout)
for repo in ["livespec-dev-tooling","livespec-orchestrator-beads-fabro"]:
    for page in range(1,8):
        d=g(f"repos/livespec-ai/{repo}/actions/runs?created=%3E2026-11-18T13:00:00Z&per_page=100&page={page}")
        rs=d["workflow_runs"]
        for r in rs:
            if r["head_branch"].startswith("release-please"): continue
            out.append((repo,r["id"],r["head_branch"],r["event"]))
        if len(rs)<100: break
print(len(out))
res=[]
for repo,rid,br,ev in out:
    try: d=g(f"repos/livespec-ai/{repo}/actions/runs/{rid}/jobs?per_page=100&filter=all")
    except Exception as e: continue
    for j in d["jobs"]:
        for s in j.get("steps",[]):
            if (s["name"].startswith("just coverage-shard") or s["name"]=="just check-per-file-coverage") and s.get("started_at") and s.get("completed_at"):
                res.append(dict(repo=repo,run=rid,br=br,job=j["name"],runner=j.get("runner_name"),st=s["started_at"],en=s["completed_at"],concl=s["conclusion"],step=s["name"],jst=j["started_at"]))
json.dump(res,open("jobs.json","w"))
print(len(res))
```

### Step 2 (mcp.py and q3.py)

```python
import os,json,urllib.request,sys
def call(tool,args):
    b=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":tool,"arguments":args}}).encode()
    r=urllib.request.Request("https://mcp.honeycomb.io/mcp",b,{"Authorization":"Bearer "+os.environ["HONEYCOMB_MCP_API_KEY_LIVESPEC"],"Content-Type":"application/json","Accept":"application/json, text/event-stream"})
    t=urllib.request.urlopen(r,timeout=120).read().decode()
    for l in t.splitlines():
        if l.startswith("data: "): return json.loads(l[6:])
    return json.loads(t)
if __name__=="__main__":
    tool=sys.argv[1];args=json.loads(sys.argv[2]);out=sys.argv[3]
    res=call(tool,args)
    json.dump(res,open(out,"w"))
    print(len(json.dumps(res)))
```

```python
import json,mcp
W=["2026-11-18T15:00:00Z","2026-11-18T16:00:00Z","2026-11-18T17:00:00Z","2026-11-18T18:00:00Z","2026-11-18T19:00:00Z","2026-11-18T20:00:00Z"]
out=[]
for a,b in zip(W,W[1:]):
    r=mcp.call("run_query",{"environment_slug":"livespec","dataset_slug":"metrics","query_spec":{"calculations":[{"op":"MAX","column":"k8s.pod.cpu.usage"}],"breakdowns":["k8s.pod.name","k8s.node.name"],"filters":[{"column":"k8s.pod.name","op":"ends-with","value":"-workflow"}],"from":a,"to":b if b<"2026-11-18T20" else "now","limit":1000},"output_format":"json"})
    t=r["result"]["content"][0]["text"].split("# Time")[0]
    out.append(t); print(a,len(t.splitlines()))
json.dump(out,open("q3.json","w"))
```

### Step 3 (join.py)

```python
import json,statistics as st,collections,glob
from datetime import datetime as D
m={}
def add(t):
    for l in t.splitlines():
        c=[x.strip() for x in l.strip('|').split('|')]
        if len(c)==3 and c[1] and c[2].startswith('livespec') : m[c[2].removesuffix('-workflow')]=c[1]
add(json.load(open('q2.json'))["result"]["content"][0]["text"].split("# Time")[0])
for t in json.load(open('q3.json')): add(t)
for f in glob.glob('q4_*.json'):
    for t in json.load(open(f)): add(t)
jobs=json.load(open('sel.json'))
d=collections.defaultdict(list);un=0
f=lambda s:D.strptime(s,"%Y-%m-%dT%H:%M:%SZ")
for j in jobs:
    n=m.get(j['runner'])
    if not n: un+=1;continue
    x=(f(j["en"])-f(j["st"])).total_seconds()/60
    if x>=1: d[n].append(x)
for n,v in sorted(d.items()):
    v.sort();p=v[min(len(v)-1,max(0,round(0.9*len(v))-1))]
    print(n,len(v),round(st.median(v),1),round(p,1),round(v[0],1),round(v[-1],1))
print("unmapped",un,"total",len(jobs))
```

## Read taken 2026-11-18 (corrected ~22:05Z)

The first version of this note (livespec-dev-tooling#5045) joined the wrong step for the orchestrator shard jobs, so
it showed hp with no real samples and concluded the trigger could not be read. That was wrong. With the step names
above, per job family (min, median / p90, n):

| node | orchestrator shard job | dev-tooling full step |
|---|---|---|
| gamingpc-xubuntu | 3.9 / 6.1, n=27 | 15.7, n=3 |
| gmktec-xubuntu | 4.9 / 7.5, n=61 | 16.2 / 19.0, n=14 |
| hp-xubuntu | 7.7 / 9.5, n=23 | 21.8, n=1 |
| poweredge-xubuntu | 8.8 / 11.7, n=55 | 30.8 / 32.0, n=7 |

**The hp weight-40 revert trigger did not fire.** hp's median is 0.88x poweredge's, and hp's p90 (9.5) is below
poweredge's (11.7) at n=23. hp runs shards, and runs them faster than poweredge. Whether hp receives them by design
is not established.

**poweredge is the slow node**, about 1.8x gmktec on both job families. Speed order matches single-thread speed
(poweredge Xeon E5-2696 v3 3.8 GHz max; hp Ryzen 4700G 3.6; gmktec Ryzen AI MAX+ 395 5.2; gamingpc 9800X3D 5.3).
That is a correlation: no controlled single-thread benchmark has run.
