# 006: landed-lever measurements — 2026-11-04

Measured by the ci-cache-optimization seat after levers 1 (prep step) and 5 (action archive cache) shipped. Each figure
names the query that reproduces it, so the plan-level Proof of Done capture can re-run it rather than cite it. The ledger
comments on epic livespec-dev-tooling-7zozck at 16:05Z and 18:2xZ carry the same figures.

## Lever 5 — node-local action archive cache (livespec-dev-tooling-a35sa4, closed 14:27:28Z)

Shipped by the poweredge `ci_converge_unit` from master b97f118e, 11:27:08Z-11:38:19Z (rc 0). The first action archive
generation, 20261104T120058Z, was published by the 12:00Z populator run.

Plan assertion 2 (no Set up job failure on a codeload download over any 6-hour window after it ships):

| Window (UTC, 2026-11-04) | Runs | Job attempts | of which `-k3s-` | Set up job failures | codeload / 429 |
| --- | --- | --- | --- | --- | --- |
| 11:38:19-15:55:00 (partial) | 331 | 1,768 | 1,121 | 0 | 0 |
| 11:38:19-17:38:19 (first full 6 h) | 467 | 2,472 | 1,623 | 0 | 0 |

Baseline (a35sa4 context, 2026-11-03, 6 h): 10 Set up job failures in 4,359 job attempts, all of them codeload downloads of
`actions/checkout`, 9 of them HTTP 429.

Query, per repository (livespec, livespec-dev-tooling, livespec-orchestrator-beads-fabro, livespec-driver-claude,
livespec-driver-codex, livespec-overseer, livespec-runtime, livespec-driver-pi, livespec-console-beads-fabro,
livespec-orchestrator-git-jsonl):

1. `gh api 'repos/thewoolleyman/<repo>/actions/runs?created=<SINCE>..<UNTIL>&per_page=100&page=<n>'`, paged.
2. For each run, `gh api 'repos/thewoolleyman/<repo>/actions/runs/<id>/jobs?filter=all&per_page=100'`, paged, keeping
   jobs with `SINCE <= started_at < UNTIL`.
3. Count jobs with `conclusion == failure` whose first step with `conclusion == failure` is `Set up job`.
4. For each such job, `gh api .../actions/jobs/<id>/logs`, then grep for `codeload` or `429`.
   A runner name containing `-k3s-` marks an ARC runner.

The item's three host assertions were host_recorded by this seat and host_verified by kubernetes-sandbox-backend on
PR #3371, at 12:25/12:45Z (A1, A3) and 14:14/14:26Z (A2). One wording finding is recorded on the item: a Set up job log
shows zero `codeload` lines for cold jobs as well. The discriminating observable is the runner diag log line
`Found action archive ... in cache directory`.

## Lever 1 — nonroot prep step (bd-ib-uuatg4, closed 10:19Z)

Plan assertion 1, timing clause. The orchestrator step `Prepare non-root leg (open baked toolchain to uid 1000)` ran on
every completed `(nonroot)` job that started 10:20:00Z-15:55:00Z:

| n | median | p90 | max | baseline |
| --- | --- | --- | --- | --- |
| 232 | 1.0 s | 2.0 s | 7.0 s | 120-130 s (research 002) |

Query: page `repos/thewoolleyman/livespec-orchestrator-beads-fabro/actions/runs?created=<SINCE>..<UNTIL>`. For each run,
page `jobs?filter=all` and keep completed jobs whose name contains `nonroot`. Take that step's `completed_at - started_at`.

The assertion's other two clauses are not yet met on orchestrator master:

- `chown -R 1000:1000 /home/ci "$GITHUB_WORKSPACE"` still runs in both prepare steps. Its carrier is bd-ib-vnmph2, filed
  2026-11-04 on legacy-coordinator-agent's decision and added to the 16:15Z carrier map.
- The nonroot legs still set a private `UV_CACHE_DIR=/home/ci/.cache/uv`. Its carrier is bd-ib-rpit5z.

## Still to measure

- Plan assertion 5 needs at least 20 runs per landed lever against these baselines. Lever 5's Set up job median against
  research 002's 2 s / 4 s is the next read.
- Plan assertion 1 gets re-read after bd-ib-vnmph2 and bd-ib-rpit5z land.
