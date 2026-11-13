# Debt-register merge lab: single-file layouts measured against git's default merge (2026-11-13)

Measured for livespec-dev-tooling-mpv6bp and its proposal, topic `the-generated-heading-coverage-debt` (livespec-dev-tooling#4527). The coordinator graded that proposal's first draft PASS-WITH-TWO-FIXES. This measurement showed the first fix's premise was false: no layout of a single register file makes the conflicts that actually happen go away. legacy-coordinator-agent then ruled option (b), one file per row, on 2026-11-13.

## Method

`git merge-file -p ours base theirs` runs the same xdiff three-way merge that a rebase applies to each file. The base register held five rows, keys B D F H J. Each case gives two branches that each change the register in one way and regenerate it.

Four single-file layouts were tested:

- the current one, `json.dumps(rows, indent=2)`;
- one row per line with one separator line (`,`) between rows;
- one row per line with two separator lines (`,` and an empty line);
- one row per line with three separator lines (empty, `,`, empty).

## Results

The same result held for all four layouts.

| Case | Every layout |
|---|---|
| rewrite two adjacent rows (D, F) | clean |
| insert into different gaps (C, G) | clean |
| insert beside a row the other branch rewrites | clean |
| remove two adjacent rows (D, F) | CONFLICT |
| insert beside a row the other branch removes | CONFLICT |
| insert into the same gap (two rows between D and F) | CONFLICT |

## Reading

What a single-file layout can deliver, the current layout already delivers.

Removing two adjacent rows conflicts in every layout. The separator lines are identical, so git's diff assigns each deleted separator to the same side of both removed rows, and the two deletions always touch. An unchanged line can never sit between them: it would have to survive in the merged result between the removed rows' neighbours, where no row's line exists.

Revises insert rows and implementations remove them, so these conflict classes are the ones that hit the revise queue. The v209 revise, livespec-dev-tooling#4438, was rebased by hand twice on 2026-11-13. Only one file per row removes these conflicts, because changes to different rows then touch different files.

## Reproduce

The script below is the lab, byte for byte. Run it in an empty directory with `python3 lab.py`; it prints the table above.

```python
import json, subprocess, os, itertools
def render(rows, sep_lines):
    # JSON array: each row one line; between rows `sep_lines` lines; commas live on separator lines
    out=["["]
    for i,r in enumerate(rows):
        if i: out += sep_lines
        out.append("  "+json.dumps(r, sort_keys=True))
    out.append("]"); return "\n".join(out)+"\n"
def merge(base, a, b):
    for n,t in (("base",base),("a",a),("b",b)): open(n,"w").write(t)
    p=subprocess.run(["git","merge-file","-p","a","base","b"],capture_output=True,text=True)
    return p.returncode, p.stdout
def R(k,w="w"): return {"heading":k,"work_item":w}
base=[R(k) for k in "BDFHJ"]
cases={
 "rewrite adjacent D,F": ([R("B"),R("D","x"),R("F"),R("H"),R("J")],[R("B"),R("D"),R("F","y"),R("H"),R("J")]),
 "remove adjacent D,F": ([R(k) for k in "BFHJ"],[R(k) for k in "BDHJ"]),
 "insert beside rewritten (E after D-rewrite)": ([R("B"),R("D","x"),R("F"),R("H"),R("J")],[R(k) for k in "BD"]+[R("E")]+[R(k) for k in "FHJ"]),
 "insert beside removed (E, remove D)": ([R(k) for k in "BFHJ"],[R(k) for k in "BD"]+[R("E")]+[R(k) for k in "FHJ"]),
 "insert different gaps (C,G)": ([R(k) for k in "BC"]+[R(k) for k in "DFHJ"],[R(k) for k in "BDF"]+[R("G")]+[R(k) for k in "HJ"]),
 "insert same gap (E1,E2)": ([R(k) for k in "BD"]+[R("E1")]+[R(k) for k in "FHJ"],[R(k) for k in "BD"]+[R("E2")]+[R(k) for k in "FHJ"]),
}
layouts={
 "current json.dumps indent=2": None,
 "1 sep line ','": [","],
 "2 sep lines ',' + ''": [",",""],
 "3 sep lines '' ',' ''": ["",",",""],
}
for ln,sep in layouts.items():
    print("==",ln)
    for cn,(a,b) in cases.items():
        f=(lambda rows: json.dumps(rows,indent=2,sort_keys=True)+"\n") if sep is None else (lambda rows,s=sep: render(rows,s))
        rc,out=merge(f(base),f(a),f(b))
        ok = rc==0
        valid = ""
        if ok:
            try: json.loads(out); valid="json-ok"
            except Exception: valid="JSON-BROKEN"
        print(f"  {cn:45s} {'clean' if ok else 'CONFLICT('+str(rc)+')'} {valid}")
```

## Raw output

```text
== current json.dumps indent=2
  rewrite adjacent D,F                          clean json-ok
  remove adjacent D,F                           CONFLICT(1) 
  insert beside rewritten (E after D-rewrite)   clean json-ok
  insert beside removed (E, remove D)           CONFLICT(1) 
  insert different gaps (C,G)                   clean json-ok
  insert same gap (E1,E2)                       CONFLICT(1) 
== 1 sep line ','
  rewrite adjacent D,F                          clean json-ok
  remove adjacent D,F                           CONFLICT(1) 
  insert beside rewritten (E after D-rewrite)   clean json-ok
  insert beside removed (E, remove D)           CONFLICT(1) 
  insert different gaps (C,G)                   clean json-ok
  insert same gap (E1,E2)                       CONFLICT(1) 
== 2 sep lines ',' + ''
  rewrite adjacent D,F                          clean json-ok
  remove adjacent D,F                           CONFLICT(1) 
  insert beside rewritten (E after D-rewrite)   clean json-ok
  insert beside removed (E, remove D)           CONFLICT(1) 
  insert different gaps (C,G)                   clean json-ok
  insert same gap (E1,E2)                       CONFLICT(1) 
== 3 sep lines '' ',' ''
  rewrite adjacent D,F                          clean json-ok
  remove adjacent D,F                           CONFLICT(1) 
  insert beside rewritten (E after D-rewrite)   clean json-ok
  insert beside removed (E, remove D)           CONFLICT(1) 
  insert different gaps (C,G)                   clean json-ok
  insert same gap (E1,E2)                       CONFLICT(1) 
```
