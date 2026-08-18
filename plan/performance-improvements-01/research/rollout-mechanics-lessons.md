# Rollout mechanics lessons (2026-08-17/18 execution waves)

Analysis extracted from executing this plan's fleet rollouts (.7/.8/.9/.10
unblocking, the 3gy1/6e6g/y23f bug family, and the coverage-pair CI dedup).
Item-level state lives on the ledger epic (`livespec-dev-tooling-yilyxr`)
and each child's comments; this note carries only the reusable mechanics
that will bite again on the NEXT fleet-wide rollout.

## 1. Pin-carried reusable workflows bootstrap-deadlock on their own fixes

A consumer's `bump-pin-from-dispatch.yml` shim calls dev-tooling's reusable
workflow **at the consumer's current pin**. Consequence: any fix shipped in
the reusable workflow (here: the 3gy1 rename-aware reconciler, v1.28.3)
cannot repair the very bump PR that would deliver it — the PR was generated
by the old-pin workflow, and it cannot merge because the missing fix keeps
its CI red. The fleet observed this as three repos (runtime, overseer,
driver-codex) stuck simultaneously on `ModuleNotFoundError` for renamed
check modules.

**Break the deadlock manually, once per consumer**: push the corrective
commit (slug renames) onto the bot's bump branch, or rebuild the branch from
master at the new tag. After ONE post-fix pin lands, all subsequent bumps
self-repair. Budget for this whenever a reusable-workflow fix changes
behavior the bump PR itself depends on.

## 2. A conflicted PR gets NO CI runs — and it looks like runner trouble

GitHub creates zero `pull_request` workflow runs when it cannot build the
merge ref (branch conflicts with base). There is no annotation; the PR just
shows "no checks reported" indefinitely, which reads as runner routing or
Actions breakage. Console PR #670 sat 20 hours in this state; even a fresh
push changes nothing while the conflict persists.

**Check `mergeable` FIRST** when a PR reports no checks: `gh pr view
--json mergeable,mergeStateStatus`. Rebase resolves it; runs appear on the
next push.

## 3. The dispatch fan-out is manifest-driven; absence is silent until the safety net sees it

The release fan-out reads livespec's committed fleet manifest. A repo
missing from the manifest gets **no dispatches, no bump PRs, no errors** —
for driver-pi this lasted its whole life, invisible because the discovery
safety net (`users/<owner>/repos` sweep) only listed the first 100 repos.
The pagination fix (PR #1503) did not route dispatches to driver-pi; it made
the conformance check finally FLAG the absence (and the Fleet-conformance
workflow is deliberately red on that finding until registration).

Three distinct failure modes produced the same visible symptom (stale pin):
- **3gy1** — dispatch arrives, bump PR opens, CI red (rename-stranded slugs);
- **6e6g** — dispatch never arrives (not in the manifest; safety net blind);
- **y23f** — dispatch arrives, bump job RUNS, dies pre-PR (reconciler's
  `check-aggregate-completeness` anchor-matrix expectation unmet by the
  Rust console's matrix).

Diagnose stale pins by locating WHERE the pipeline stops (fan-out target
list → consumer run history → run logs), not by assuming the newest known
bug.

## 4. A live dispatch cycle is cheap to synthesize

`gh api repos/<owner>/<consumer>/dispatches -f event_type=sibling-released
-f 'client_payload[source_repo]=…' -f 'client_payload[tag]=…' -f
'client_payload[release_url]=…'` exactly reproduces the release fan-out for
one consumer. This turned y23f's "verify with a live dispatch cycle" exit
criterion from "wait for the next release" into a five-minute proof (run
32185088244 → automated bump PR #676).

## 5. Dedicated jobs that inherit a matrix leg's work need the leg's environment too

The coverage-pair split (#1504) moved a suite-running target out of the
`check-python` matrix into a dedicated job and lost the matrix's node-PATH
shim — the full suite spawns `node`, so master went red with
`FileNotFoundError: 'node'` (#1511 restored the shim). When extracting a
matrix leg into its own job, copy the leg's run-step environment wholesale,
then trim; don't reconstruct it from what the target "should" need.

## 6. Natural-experiment readout for the batching rollout

With 9/10 repos batched and driver-pi still on the full historical matrix,
the 24h jobs-per-run table (query `DpmKoHaXtSz`, 2026-08-19) shows the fleet
blended at ~20 jobs/run while the unbatched control sits at 63.3 — the
pre-rollout shape almost exactly. When closure windows mature, driver-pi's
own before/after (once batched) is the cleanest single-repo measurement of
the setup-tax mechanism this plan will get.
