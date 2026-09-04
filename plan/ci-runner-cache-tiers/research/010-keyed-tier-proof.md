# 010 — The keyed tier needs no forked runner: proven on the pool

Written 2026-09-04 in the planning session that ran child
`livespec-dev-tooling-dajhxa` (decision D2 of the plan-decision-record on
`livespec-dev-tooling-efqeip`). It answers the charter's open question 1 —
"is tier 2's forked-runner cost real today?" — which `research/002`
answered from the runner source and left as "hypothesis until run on the
host". It has now been run on the host. Everything below was a SCRATCH
experiment on `poweredge-xubuntu`: nothing converged, nothing boot-durable,
every object deleted at the end (the cleanup record is the last section).

## Result, in one line

A stock `actions/runner` 2.336.0 image, untouched, redirected `actions/cache`
v4 to a pool-local `falcondev-oss/github-actions-cache-server` 9.7.0 through
ONE env line on the job container of a scratch hook pod template
(`NODE_OPTIONS=--require=<preload>`), the save landed on the local server,
the restore was served by it, and `actions/upload-artifact` /
`download-artifact` v4 passed through to GitHub unchanged. The forked-runner
cost recorded by the tier-2 design (and still stated by the server's own
docs) is NOT real on this pool.

## The mechanism, as run

- **Server.** `ghcr.io/falcondev-oss/github-actions-cache-server:9.7.0`
  (digest `sha256:3999b020…`), one Deployment + ClusterIP Service in a
  scratch namespace `ci-actions-cache`, filesystem storage + sqlite on a
  scratch subdirectory of the `ci-cache` tier
  (`/var/cache/ci-runner/actions-cache-scratch-dajhxa`, hostPath). Env:
  `API_BASE_URL` = the Service URL, `STORAGE_DRIVER=filesystem`,
  `DB_DRIVER=sqlite`, `DEFAULT_ACTIONS_RESULTS_URL` left at its default
  (`https://results-receiver.actions.githubusercontent.com`). Token
  validation was NOT skipped: the server verified each job's
  `ACTIONS_RUNTIME_TOKEN` against GitHub's OIDC JWKS and recorded the
  entry under the token's own scope.
- **Preload.** A 12-line CommonJS file in a ConfigMap mounted read-only at
  `/opt/keyed-cache/preload.js` in the job container. If
  `KEYED_CACHE_SERVER_URL` is set it rewrites `process.env.ACTIONS_RESULTS_URL`
  and `ACTIONS_CACHE_URL` to it (trailing slash) and logs the original to
  stderr. Nothing else.
- **Hook pod template.** A DEDICATED scratch template (not the production
  `arc-hook-pod-template`): the `$job` container gets
  `NODE_OPTIONS=--require=/opt/keyed-cache/preload.js`,
  `KEYED_CACHE_SERVER_URL=http://actions-cache.ci-actions-cache.svc.cluster.local:3000/`,
  and the ConfigMap volume. It kept `hostUsers: false` and the
  `ci-runner-workflow` AppArmor profile, so the proof ran under the pool's
  real confinement.
- **Scale set.** A DEDICATED scratch `AutoscalingRunnerSet`
  `keyed-cache-proof-k3s` (chart 0.14.2, `maxRunners: 1`, one churn-slot,
  no Kueue queue label — Kueue's `manageJobsWithoutQueueName` is off, so
  it was scheduled directly), derived from `values-poweredge-xubuntu-k3s.yaml`
  with the scratch template ConfigMap. No production set was touched.
- **Workflow.** Run 33906630133 in this repository, dispatched from a
  scratch branch (`workflow_dispatch` runs the file from the chosen ref
  as long as a file of that path exists on the default branch — the
  dispatch-only `k3s-arc-proof-job.yml` path was reused for exactly that
  reason; master's copy was never changed). Two jobs, both
  `container: ubuntu:24.04` on the scratch set: `save` (write a payload,
  `actions/cache/save@v4`, `actions/upload-artifact@v4`) then `restore`
  (`actions/cache/restore@v4` with `fail-on-cache-miss`,
  `actions/download-artifact@v4`, `cmp` the two payloads).

Why the env line works at all (the fact `research/002` read from source and
this run confirms on the shipped hook): the container hook writes each
step as `exec env KEY=VAL … <entrypoint>` under `sh -l`, so the runner's
per-step `ACTIONS_RESULTS_URL` is layered OVER the container's own env
rather than replacing it, and the container's `NODE_OPTIONS` reaches every
node process — including the one that runs `actions/cache`. The runner
itself never sets `NODE_OPTIONS`; the job's first step printed
`NODE_OPTIONS=--require=/opt/keyed-cache/preload.js` and an EMPTY
`ACTIONS_RESULTS_URL` (a `run:` step is not a node action, so the runner
does not export it there).

## Evidence, against the child's three acceptance criteria

1. **The save landed on the local server.** Job log: the preload line
   `ACTIONS_RESULTS_URL https://results-receiver.actions.githubusercontent.com/
   -> http://actions-cache.ci-actions-cache.svc.cluster.local:3000/` then
   `Cache saved with key: dajhxa-proof-33906630133-1`. Server storage after
   the run: one 315-byte object (`storage/133072490/merged`) and one
   `cache_entries` row — key `dajhxa-proof-33906630133-1`, scope
   `refs/heads/scratch/keyed-cache-proof`, repository id `1245319543`.
   GitHub's own cache for the repository: `gh cache list --key dajhxa-proof`
   returned nothing. The restore job then logged `Cache hit for:
   dajhxa-proof-33906630133-1` / `Cache restored successfully` — served by
   the local server, since GitHub held no such entry.
2. **Artifacts still pass through.** With the SAME redirected
   `ACTIONS_RESULTS_URL`, `upload-artifact` reported
   `Artifact dajhxa-proof-33906630133 has been successfully uploaded! …
   Artifact ID is 9949729123`, `download-artifact` restored it, and the
   `cmp` of the cache-restored and artifact-downloaded payloads passed.
   GitHub's API confirms artifact 9949729123 (185 bytes) exists on the
   repository — the server forwarded the artifact twirp calls upstream.
3. **The stock runner image was not modified or forked.** The scratch set
   ran `ghcr.io/actions/actions-runner:2.336.0@sha256:0cfdcc70…`, the same
   pinned digest every production set runs; no `--disableupdate`, no
   patched `Runner.Worker.dll`, no `CUSTOM_ACTIONS_RESULTS_URL`.

Timings, for the record only (a 315-byte payload measures nothing about
throughput): save 1.2 s, restore 0.3 s, both including the JWKS-verified
token round trip.

## What it changes, and what it does not

- The recorded cost of tier 2 drops from "a forked runner in every scale
  set, self-update pinned" to "one env line on the production hook pod
  template, one preload ConfigMap, one namespace on the `ci-cache` tier".
  The maintainer's skepticism of the forked-runner claim (charter, open
  question 1) was correct.
- It does NOT change the scope decision. The keyed tier is still not
  transparent: a workflow must carry `actions/cache` steps to benefit, and
  every fleet workflow gates its uv cache step to the hosted lane today.
  The scope event's "offered-not-required" posture (v054: the pool MAY offer
  an emulation only through a mechanism that leaves the stock runner
  untouched, only after proof on the pool) is now SATISFIABLE, not
  satisfied. Its shape is filed as a separate child of the plan epic, low
  priority, human-gated because it changes the production template.
- Fail-soft properties observed: a job that does not use `actions/cache`
  is unaffected; a workflow that sets its own `NODE_OPTIONS` would lose
  the redirect and fall back to GitHub's cache; the preload does nothing
  when `KEYED_CACHE_SERVER_URL` is empty, which is the kill switch the
  production shape would wire to `CI_CACHE_KILL_SWITCH`.
- Trust tiering came free, as `research/002` read from `lib/scope.ts`: the
  entry was recorded under the GitHub-signed token's scope
  (`refs/heads/scratch/keyed-cache-proof`) with no forgeable pod-side
  input. A PR job would read base-ref entries and write its own ref's.

## Cleanup record

All deleted the same session, in this order, then verified: the helm
release `keyed-cache-proof-k3s` (listener and runner pods gone), the two
ConfigMaps in `arc-runners` (`keyed-cache-preload`,
`keyed-cache-proof-hook-template`), the namespace `ci-actions-cache`, the
scratch storage directory on the `ci-cache` tier, the staging directory in
the operator's home, the pulled `curlimages/curl` probe image, the scratch
branch (remote ref deleted through the GitHub API — the primary-checkout
hook refuses a `push --delete` from the primary, correctly), the local
branch and worktree. Residue check after: zero `keyed*` objects in
`arc-runners` and `arc-systems`, 11 scale sets as before, `ci-cache` tier
holds only `crates-proxy`, `k3s-containerd`, `k3s-storage`. The `ubuntu:24.04`
image pulled by the job container was left in containerd like any other
job image.
