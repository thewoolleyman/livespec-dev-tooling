# 005 — The #3110 gate-proxy revert (2026-11-02)

Stop-the-line record for plan `dev-host-test-gate-load` (epic
`livespec-dev-tooling-6vuiwe`). It is recorded here because it touched two of
this plan's carriers, etoyip and iascyn.

## What broke

`livespec-dev-tooling-etoyip` merged as PR #3110 (merge `0a90e0dc`, 11:56:41Z).
It made gate Jobs rewrite `uv.lock` so that locked artifacts are fetched
through `http://pypi-proxy.ci-warm-cache.svc.cluster.local:8081/packages/`.
From that point every livespec-dev-tooling gate Job logged
`:: gate: 1 uv.lock file(s) rewritten …`, and then `install_worktree_pack`
failed with "hypothesis was not found in the package registry …
livespec-dev-tooling:dev depends on hypothesis==6.122.3 … unsatisfiable".
That happened before any check ran. The gate therefore emitted no
failed-target summary.

Two Jobs were observed red this way: `gate-livespec-dev-tooling-z2kpv` (the
etoyip janitor) and `gate-livespec-dev-tooling-rjzxj` (the iascyn janitor,
after PR #3128). The full output is kept on the dev host under
`tmp/janitor-failed-output/`.

## Reader analysis: why the revert alone was enough

- `gate_remote_delegate.resolve_renderer` prefers the repository's own
  in-tree `ci-runner/k3s/phase2/gates/render-gate-job.sh`, together with its
  template. livespec-dev-tooling's own gates therefore read master. Reverting
  master fixes them directly.
- Every other repository renders through the copy packaged in the wheel. Only
  v1.152.1 contains #3110. Its sibling fan-out (run 41442631286) was cancelled
  before its dispatch job ran, so no consumer was bumped to v1.152.1.
- The node's converged `/usr/local/lib/ci-runner-k3s/gates/` copy dates from
  2026-10-20 and was untouched by #3110. No converge was needed.

## Remedy and proof

- PR #3131 is a server-side revert of #3110, merged 12:27:48Z as `4bfc418c`.
- Lift proof: the plain `reconcile-merged` of iascyn ran its janitor as
  `gate-livespec-dev-tooling-8255m`. The Job completed 1/1 in 4m22s, and its
  log carries no rewrite line.
- etoyip is reworked through a fresh dispatch. Its Definition of Done now
  requires two things: a fall-through to `files.pythonhosted.org` when the
  proxy misses, and a live gate Job that resolves the full locked dev set
  through the proxy.

## Why this note carries a `Release-As` footer

release-please cannot parse the six `Revert "…"` commits that the forge's
revert wrote: "unexpected token ' ' at 1:7". It therefore opened no release
after #3131. The commit that lands this note carries `Release-As: 1.152.2`,
so that a release containing both iascyn's fix and the revert is cut and
fanned out, superseding v1.152.1.

### Correction (2026-11-02, ~13:05Z)

That footer was unnecessary, and it was harmful. qgv3tb's `feat` released
v1.153.0 at 12:58:52Z, before the note merged, and that release already
carries the revert and iascyn's fix. The `Release-As: 1.152.2` footer then made
release-please propose release PR #3136 at 1.152.2, which is BELOW v1.153.0.
#3136 was converted to draft to stop it auto-merging, and it is closed
unmerged.

release-please honours the newest `Release-As` footer since the last release.
The commit that lands this correction therefore carries
`Release-As: 1.153.1`, so that the pending release goes forward rather than
backward.

The lesson: before forcing a release with a footer, re-read the latest
published tag at merge time, not at authoring time. On a busy master, an
ordinary `feat` or `fix` can cut the release first.
