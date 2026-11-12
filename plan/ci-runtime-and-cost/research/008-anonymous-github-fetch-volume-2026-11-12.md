# Anonymous github.com git volume from the homelab egress

Status: measured by a read-only research pass for the ci-runtime-and-cost seat. Context: livespec-dev-tooling-fc4dzb, livespec-dev-tooling#4329, livespec-dev-tooling-reuqym.
Window: 2026-11-11T15:00Z to 2026-11-12T15:00Z (24 h). Measured 2026-11-12 ~15:00Z.

## Bottom line

- **About 12,000 anonymous github.com git operations in 24 h, roughly 500 per hour.** Busy hours reach about 750. Each operation is a clone, fetch or ls-remote. Each one is at least two HTTPS requests: `GET info/refs` (where a 401 arrives), then `POST git-upload-pack`.
- **About 60% of that volume is clones of fleet repos at their default branch or release tag.** These come from factory sandboxes, delegated gates, the warm-cache populator and one livespec CI job. An in-cluster git mirror (livespec-dev-tooling-reuqym) can serve all of them. **The mirror is the single change that cuts the most volume.**
- **The uv git fetches in CI are only about 12%.** A warm uv git cache addresses this part. They come in bursts: every release fan-out makes every consumer's bump-PR CI fetch at once. At 13:15–13:35Z there were 8 bump-PR CI runs, one per consumer, all cold for `livespec-dev-tooling v1.201.0`. That is close to when the 401s began (~13:20Z).
- **A 401-only credential helper does not lower anonymous volume.** For a public repo, git sends the first request with no credentials and only asks the helper after a 401. Every operation still starts anonymous. Only a pre-set `http.extraHeader` (the actions/checkout method) makes the first request authenticated.

## Method

Where the traffic leaves: the k3s node `poweredge-xubuntu` and the factory hosts sit behind the homelab NAT, 73.231.243.71. `tailscale status` shows gmktec, poweredge and hp all sharing that address. The dev host this ran on (`vps`) has a different egress. Its host-local gate runs (724 of 733 local `tmp/gate-runs` records in the window, venue `host_local`) are therefore **excluded**.

Volume per source is measured as **operations per unit × units per hour**:

- Units come from Honeycomb `livespec/metrics`: distinct `k8s.pod.name` per namespace per hour, filtered to pods that report `k8s.pod.cpu.usage`. Factory run start times are decoded from the ULID in each `petri-<ulid>-l0` pod name. The units were cross-checked against the GitHub Actions API.
- Operations per unit come from workflow and template source, and are confirmed in sampled job logs and live gate pod logs.

Caveats on the units:

- Hourly distinct counts include pods that span two hours. The hourly sums are 4–19% above the 24 h distinct counts, so the 24 h totals below use the 24 h distinct counts.
- Honeycomb's COUNT_DISTINCT is approximate. The factory namespace read 256 in one query and 228 in another.

### How each kind of operation was classified

**actions/checkout is AUTHENTICATED.** Every sampled job log shows `git config --local http.https://github.com/.extraheader AUTHORIZATION: basic ***` before the `git fetch`. The header is therefore on the first request. The same holds for the `git fetch --unshallow origin` / `git fetch origin master` steps, which run inside that same workspace repo.

```bash
gh api --cache 6h repos/thewoolleyman/livespec/actions/jobs/131212079504/logs | grep -n 'extraheader\|From https'
```

**Some git operations in the same jobs are ANONYMOUS.** The header is `--local` to the workspace repo, so it does not reach:

- a new `git clone` into `$RUNNER_TEMP`;
- uv's own git database under `UV_CACHE_DIR=/__w/_warm/uv/git-v0/db`.

The job image's global config holds only `safe.directory`. No credential helper or `insteadOf` is baked into any `docker/fabro-sandbox/*/Dockerfile`. Commands that reproduce this:

```bash
grep -rn -i 'credential\|insteadof' docker/fabro-sandbox/
ssh poweredge-xubuntu 'kubectl get pod -n arc-runners <wf-pod> -o json'   # env: UV_CACHE_DIR=/__w/_warm/uv, no git credential
```

**uv git fetches.** uv prints `Updated https://github.com/<repo>.git (<sha>)` only when it fetches from the network. A warm cache prints nothing.

## Units (24 h)

### CI on the self-hosted ARC/k3s pool

Runner pods per scale set, from Honeycomb query `fodeuYuMSab`:

```
dataset metrics; COUNT_DISTINCT(k8s.pod.name)
where k8s.namespace.name = arc-runners and k8s.pod.cpu.usage exists
calc scaleset = REG_VALUE($k8s.pod.name, `^(.*)-[a-z0-9]{5}-runner-[a-z0-9]{5}$`)
breakdown scaleset; 2026-11-11T15:00Z..2026-11-12T15:00Z
```

Totals: **4,595 runner pods**, about 191 jobs/h.

| Scale set | Repository it routes | Runner pods / 24 h |
|---|---|---|
| livespec-dev-tooling-k3s | dev-tooling coverage and incident jobs | 1,345 |
| livespec-orchestrator-k3s | orchestrator coverage shards | 1,315 |
| livespec-dev-master-k3s | dev-tooling push to master | 530 |
| livespec-local-ci-k3s | livespec | 327 |
| livespec-overseer-k3s | livespec-overseer | 214 |
| livespec-driver-codex-k3s | livespec-driver-codex | 209 |
| livespec-driver-claude-k3s | livespec-driver-claude | 171 |
| livespec-console-beads-k3s | livespec-console-beads-fabro | 139 |
| livespec-orchestrator-git-k3s | livespec-orchestrator-git-jsonl | 127 |
| livespec-driver-pi-k3s | livespec-driver-pi | 116 |
| livespec-runtime-k3s | livespec-runtime | 96 |
| fabro-k3s | fabro | 7 |

Scale-set routing is from:

```bash
gh api repos/thewoolleyman/<repo>/actions/variables
```

dev-tooling and orchestrator send their other jobs to `ubuntu-latest`, which is hosted and therefore not this egress.

Cross-check against the GitHub API. A single sampled CI run has 10 k3s jobs for livespec; 34 CI runs × 10 ≈ 340, against 327 pods. Commands:

```bash
gh api --paginate "repos/thewoolleyman/<repo>/actions/runs?created=>=2026-11-11T15:00:00Z&per_page=100"
gh api "repos/thewoolleyman/<repo>/actions/runs/<id>/jobs"   # one PR run and one push run per repo
```

dev-tooling needed a second window query, because the runs list stops at 1,000 results.

### Delegated gate Jobs (namespace `gates`)

Gate pods per repo, from Honeycomb query `BzGnJMAgYDc`. The query is the same as above, with these changes:

```
filter k8s.namespace.name = gates
calc gaterepo = REG_VALUE($k8s.pod.name, `^gate-(.*)-[a-z0-9]{5}-[a-z0-9]{5}$`)
```

Totals: **707 gate pods**, about 29.5/h.

| Repository | Gate pods / 24 h |
|---|---|
| livespec-dev-tooling | 474 |
| livespec-orchestrator-beads-fabro | 216 |
| livespec | 24 |
| livespec-overseer | 7 |
| livespec-driver-codex | 5 |
| livespec-driver-claude | 4 |
| livespec-runtime | 1 |

A live check agrees: `ssh poweredge-xubuntu 'kubectl get jobs,pods -n gates -o json'` shows 63 gate Jobs created in hour 14Z. Their TTL is 3600 s, so the cluster keeps only the last hour.

The local `/data/projects/*/tmp/gate-runs` records cannot measure this source. 724 of the 733 records in the window are `host_local` runs on `vps`, and the delegated pre-push gates write no record there.

### Factory (Fabro/petri sandboxes in k3s namespace `factory` on poweredge)

**205 runs started in 24 h, about 8.5/h.** This comes from decoding the ULID timestamps of the 239 `petri-*-l0` pod names returned by Honeycomb query `CevJKrtwGy9`.

The `factory-mi-homelab` namespace had no pods. gmktec currently runs no sandbox workload: `docker ps` shows one old sandbox container and redis.

### Warm-cache populator (CronJob `ci-warm-cache/warm-cache-populate`, `*/30`)

This adds 48 ticks per day, plus the hourly `warm-cache-populate-fabro`.

## Operations per unit

| Unit | Anonymous operations each | Evidence |
|---|---|---|
| CI job in a uv-git consumer repo: livespec, driver-claude/codex/pi, orchestrator, orchestrator-git-jsonl, overseer, runtime | **0.57 average uv git fetch (estimate)**. Range 0–2; ≥1 fetch in 11 of 28 jobs (39%) | `sample.sh` over 4 runs per repo spread across the window: 16 `Updated https://github.com` lines in 28 job logs. The fetches cluster on `chore/bump-*` PRs and on master pushes before the next populator tick rebuilds the warm generation. Example: the 13:30Z tick logged `REBUILD: lock changed` for 8 repos and published `20261112T133001Z` |
| CI job in dev-tooling or console | 0 git. dev-tooling `incident-ci` does `uv pip install git+https://github.com/...@<tag>` and resolved from a warm cache with no `Updated`. The tag resolution may be one anonymous REST call; not counted here | `logs/dt-incident.log`, job 131246296842 |
| livespec CI run, job `check-doctor-static` | **3** anonymous `git clone --depth 1` (orchestrator-git-jsonl, dev-tooling, runtime) | livespec `ci.yml` "Clone sibling repos"; log of job 131212079504 shows 3 `Cloning into` |
| orchestrator `check-fleet-materialized-workflow-toml-size` | Clones every fleet member, but it runs on `ubuntu-latest` (hosted), so **0 here** | orchestrator `ci.yml` line ~1257 |
| Gate pod, any repo | **1** core fetch (`fetch-livespec-core` initContainer, `https://github.com/thewoolleyman/livespec.git`, no credential) **+ 1 per PUBLIC cross-repo sibling** (`git clone --depth 1`). Private siblings get a minted token through `http.extraHeader`. The tree fetch goes to the in-cluster git-daemon, not GitHub | `ci-runner/k3s/phase2/gates/gate-job-template.yaml`, `render-gate-job.sh` (`LIVESPEC_CORE_URL`, private-sibling branch); live pod logs |
| … dev-tooling gate | **3** (core + livespec + orchestrator) | `gatepod.gate-livespec-dev-tooling-44h7n-gmmpd.log` |
| … orchestrator gate | **10** (core + 9 public of 12 siblings; dolt-server, livespec-tdd-proof and openbrain are private), + 0.57 uv (est.) | `gatepod.gate-livespec-orchestrator-beads-fabro-22crr-4sbq7.log` lists 12 siblings; `gh api repos/thewoolleyman/<r> --jq .visibility` |
| … livespec / overseer / claude / codex / runtime gate | 6 / 5 / 3 / 2 / 4 (core + `cross_repo_targets`), + 0.57 uv (est.) | `.livespec.jsonc` `cross_repo_targets` key counts per repo |
| Factory run | **~24 (ESTIMATE; nothing observed in a log)**. Breakdown below the table | orchestrator `_dispatcher_overlay_siblings.py`, `_dispatcher_run_from_clones.py`, `implement-work-item/workflow.toml` |
| Populator tick | **≤31**: 10 `git fetch --depth 1` of the routed repos + ≤21 `git ls-remote` (action refs are re-resolved every tick, even when unchanged). A lock-change rebuild adds the uv git fetches of the unique pins (~6) | `kubectl logs -n ci-warm-cache warm-cache-populate-29908260-zpp6q` ("21 pinned action refs across 10 repositories"); `warm-cache-populate.sh` lines 587–613 and 1152–1231 |

How the factory figure of ~24 per run breaks down:

- 9 sibling work clones, each preceded by a `git ls-remote --exit-code`: 18 operations. These are full-history clones, so the most expensive of all.
- 1–3 run-from clones and tag resolutions.
- Clone of the target repository: about 1.
- Refreshes and fetches: about 2.
- uv git fetches: 0–2.

All of these are plain `git clone https://github.com/...`. `GITHUB_TOKEN` sits in the environment, but plain git does not read it.

## Per-source table (24 h window)

| Source | Ops / unit | Units / h | **Ops / h** | Ops / 24 h | Basis |
|---|---|---|---|---|---|
| **Factory sandbox runs** | ~24 (est.; range 18–30) | 8.5 runs | **~205** | ~4,920 (3,690–6,150) | ESTIMATE |
| **Delegated gates**, total | — | 29.5 pods | **~164** | ~3,930 | measured units, ops from source and logs |
| … orchestrator gates | 10.57 | 9.0 | 95 | 2,283 | |
| … dev-tooling gates | 3 | 19.8 | 59 | 1,422 | |
| … other repos' gates | 2.6–6.6 | 1.7 | 10 | 229 | |
| **Warm-cache populator** | ≤31 per tick | 2 ticks | **≤62** | ≤1,488 (+ rebuilds, + ≤24 fabro clones) | from source and log |
| **CI uv git fetches** (consumer k3s jobs) | 0.57 (est.; ~0.3–0.9) | 107 jobs (2,575/24 h) | **~61** | ~1,470 (770–2,320) | measured units, sampled rate |
| **CI livespec sibling clones** | 3 | 1.4 runs | **4** | 102 | measured |
| CI checkout and in-workspace fetches | 0 (authenticated) | — | 0 | 0 | extraheader in logs |
| **TOTAL** | | | **~496** | **~11,900** | |

Share of the total:

| Source | Share |
|---|---|
| Factory | ~41% |
| Gates | ~33% |
| Populator | ~12% |
| CI uv | ~12% |
| CI livespec sibling clones | ~1% |

**Clones and fetches of fleet repos at their default branch or tag come to ≈8,800/day, about 74%.** That is factory siblings, gate core and siblings, populator fetches and the livespec CI siblings. **Without the factory estimate, the measured part is ≈7,000/day, about 290/h.**

## Hourly shape across the window

The hourly columns use hourly distinct pods, which overcount by 4–19% at hour edges. The factory column assumes ~24 operations per run. The populator is a constant 62/h.

```
hour(Z)    arc pods  CI uv  CI clone  gate pods  gates  fac runs  factory  total
11-11T15     136      35      0        26        101      4         96     293
11-11T16     157      42      0        44        215     15        360     679
11-11T17     167      44      0        37        225      7        168     498
11-11T18     115      24      0        31        176      6        144     406
11-11T19     213      74     12        21        122      9        216     485
11-11T20      58      19      3        22        124      0          0     208
11-11T21     293     131     30        35        234      7        168     624
11-11T22     165      47      3        23        143      4         96     351
11-11T23     119      19      3        29        113     12        288     485
11-12T00     243      76      0        46        188     15        360     686
11-12T01     225      84      0        48        237     10        240     623
11-12T02     164      56      3        37        217      6        144     482
11-12T03     182      43      0        50        251      7        168     524
11-12T04     172      40      0        41        259     11        264     626
11-12T05     353     142     12        40        218     13        312     746
11-12T06     161      51      6        39        207      8        192     519
11-12T07     163      47      0        36        237      6        144     490
11-12T08     339     143     12        33        239     11        264     720
11-12T09     216      62      0        28        190      8        192     506
11-12T10     364     131      6        39        261     12        288     747
11-12T11     186      44      0        42        262      4         96     464
11-12T12     247      73      0        17         81      5        120     336
11-12T13     317     100     12        19         87     14        336     598
11-12T14     124      22      0        57        315     11        264     662
```

What the shape shows:

- No hour stands out by volume. 13Z, when the 401s began, is ordinary at about 600.
- The pressure is better described as sustained ~300–750/h, with **short bursts**. The clearest burst is the release fan-out. Between 13:15 and 13:35Z there were 8 `chore/bump-livespec-dev-tooling-v1.201.0` CI runs, one per consumer:

  ```bash
  awk -F'\t' '$2=="CI" && $6>="2026-11-12T13:15" && $6<"2026-11-12T13:35" && $8~/bump/' runs/*.tsv
  ```

  Each made ~10–14 k3s jobs fetch 1–2 git sources cold, within about 2 minutes. That is roughly 100–200 anonymous fetches (estimate), before the 13:30Z populator rebuild.
- Gate volume peaks overnight (01–04Z, 14Z), driven by dev-tooling and orchestrator gates.
- CI uv volume peaks at 05Z, 08Z and 10Z, the release and bump waves.

## Not observable from here

- **Factory operations per run.** Sandbox pods produce no `kubectl logs`: the sandbox container is an exec target. Their prepare-step scripts are base64 in env vars; they were not decoded, to avoid handling credential material. I did not find sandbox-side git spans in Honeycomb. The ~24 figure comes from orchestrator source and is the biggest uncertainty in the total.
- **The petri server and host-side janitors on gmktec.** Any clones or fetches they make outside the gates namespace were not measured.
- **Other homelab hosts.** Developer and agent sessions on gmktec, hp, poweredge and gamingpc were not measured: local `uv sync`, Claude Code and Codex plugin marketplace auto-updates (git fetches of marketplace repos), and `mise`/`gh` installs.
- **GitHub REST calls.** Anonymous `api.github.com` calls (uv tag resolution, any un-tokened `gh`) are a different limit and are not counted.
- **The 401s themselves.** All 28 sampled CI logs and both gate pod logs predate the 401 window or show none. The 401 rate over time was not measured.
- **Exact uv cold rate.** The 0.57/job figure comes from 28 sampled jobs.

## Which single source to serve from a cache or mirror

**The in-cluster git mirror (livespec-dev-tooling-reuqym), pointed at default-branch and tag clones of fleet repos, is the one change that cuts the most volume.** It covers:

- factory sibling and run-from clones: ~4,900/day estimated, of which the 9 full-history sibling clones per run are about three quarters;
- gate core and sibling clones: ~3,800/day measured. Orchestrator gates alone are ~2,160, the largest measured line item: 216 pods × 10;
- populator repo fetches: 480/day;
- livespec CI sibling clones: 102/day.

Together that is about 9,300 of ~11,900 (≈78%). Restricted to the measured part, it is about 4,400 of ~7,000 (≈63%).

The second lever is the populator's 21 ls-remotes per tick, about 1,000/day. Re-resolving only on a schedule (for example hourly), or through the mirror, cuts it by half or more.

The warm uv git cache addresses ~1,470/day (≈12%), but this is the burst source at release fan-out. Two mitigations follow from that:

- **Have the populator rebuild immediately when a release tag is cut.** Today it waits up to 30 minutes, and bump PRs always run cold.
- **Seed the new pin before the fan-out.** This removes the coincident spike even where hourly volume barely moves.

The 401 helper in livespec-dev-tooling#4329 recovers failed jobs, but every operation still starts anonymous, so it does not reduce anonymous volume.

## Reproduction artifacts

All files are in this scratchpad directory:

- `runs/*.tsv`: GitHub run lists.
- `jobs/*.tsv`: sampled run job lists.
- `logs/`, `sample/`: job logs.
- `sample.sh`: the uv-fetch sampler.
- `hc_*.json`, `*_hourly.tsv`, `fac_starts.tsv`: Honeycomb series.
- `gates.json`, `gatepod.*.log`: gates namespace and gate pod logs.
- `populate.log`: populator log.

GitHub API use was about 110 calls.
