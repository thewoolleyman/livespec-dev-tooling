# Superseded master CI runs: measurement and three options (2026-11-09)

Asked by legacy-coordinator-agent on 2026-11-09 at about 07:3xZ. The question was whether the master CI workflow's lack
of `cancel-in-progress` for superseded master pushes is deliberate, and what it costs. This note holds the measurement
and drafts of two proposals. **Nothing here is filed.** The three options below form one design choice that belongs
to the maintainer. The coordinator carries it under FOR THE MAINTAINER, because the choice changes the master-health
reconciler's contract and runs less CI.

## Finding

The absence is not recorded as deliberate. livespec-dev-tooling's `.github/workflows/ci.yml` has no `concurrency`
stanza at all, for master or for pull requests, and no comment explains why. Other workflows in the repository set it
deliberately: `auto-enable-merge.yml` sets it to true, the image builds set it true on pull requests only,
`release-please.yml` sets it false, and `reusable-master-health-reconcile.yml` sets it false with a reason.

It is load-bearing all the same. livespec core's `non-functional-requirements.md` §"CI as a merge gate (branch
protection)" ("Red master heals itself") makes the reconciler "(b) identify the culprit as the earliest red `master`
commit whose parent was green". This repository's realization, `contracts.md` §"Master-health reconciler", adds: "A
culprit that cannot be proven … MUST raise needs-attention instead of a revert." A cancelled master run leaves a commit
with no verdict. That commit can be neither the proven green parent nor the proven red culprit, so an automatic revert
degrades to needs-attention.

## Measurement

Master push runs of the workflow named `CI`, over 72 h (2026-11-06T07:48Z to 2026-11-09T07:48Z), through cached
`gh api` reads with 0 skipped pages. A run is SUPERSEDED when a newer master push run was created before it completed.
SAVABLE is the runner minutes its jobs spent after that moment, which is what `cancel-in-progress` would have saved.
Minutes are summed from each job's `started_at` to `completed_at`.

| member | master runs | superseded | master-lane min/day | superseded min/day | savable min/day | reconciler caller |
|---|---|---|---|---|---|---|
| livespec-dev-tooling | 208 | 169 (81%) | 3,612 | 3,210 | 2,467 | none (ships the reusable workflow only) |
| livespec-orchestrator-beads-fabro | 166 | 110 (66%) | 4,480 | 3,209 | 1,640 | none (named in a `ci-root-uid.yml` comment only) |
| livespec-overseer | 28 | 1 | 176 | 11 | 4 | none |
| livespec-runtime | 5 | 1 | 11 | 4 | 0.2 | none |
| livespec | 25 | 0 | 97 | 0 | 0 | `master-health-reconcile.yml` |
| livespec-driver-claude | 15 | 0 | 48 | 0 | 0 | none |
| livespec-driver-codex | 24 | 0 | 70 | 0 | 0 | none |
| livespec-console-beads-fabro | 0 | 0 | 0 | 0 | 0 | none |

The fleet can save about 4,110 runner-min/day, roughly 68 runner-hours/day, which is 48% of all master-lane CI time
(about 8,500 min/day). Nearly all of it is in the two repositories that take factory merges in bursts. livespec, the
one reconciler caller, has no superseded runs, so where the proof is armed today it costs nothing. The script is
`master_supersede.py`, kept in the measuring session's scratchpad. Its definitions are the two sentences above.

The waste also shows up as queue delay. During the 2026-11-09 merge gap the dev-tooling master lane stacked 7 runs.
Each new head's jobs waited more than 3 min for runners until the superseded runs were cancelled by hand: 11 runs,
from 07:30 to 07:34Z.

## Option A: the reconciler resolves an unverdicted commit by re-running its cancelled run (the durable fleet fix)

**Core draft** (livespec `non-functional-requirements.md` §"CI as a merge gate (branch protection)", clause (b)):

> (b) identify the culprit as the earliest red `master` commit whose parent was green. A `master` commit inside the
> suspect range whose all-green gate has no completed verdict, because its run was cancelled when a newer push
> superseded it, MUST be resolved before a culprit is named. The reconciler re-runs that commit's cancelled run, one
> commit per reconcile step, choosing commits by bisection over the unverdicted range. A culprit MUST NOT be named
> from an unverdicted commit. Once the commits needed for the proof are verdicted, every fleet repository's `master`
> push CI MAY set `cancel-in-progress` for superseded runs.

**Dev-tooling realization draft** (`contracts.md` §"Master-health reconciler", "Culprit and revert"), with scenarios:

> When the commits between the newest green-verdicted `master` commit and the red newest commit include commits whose
> gate verdict is cancelled or missing, the reconciler MUST take as its one step a re-run of the cancelled run for the
> bisection midpoint of that range, and MUST name a culprit only from completed verdicts. A cancelled run older than
> the forge's re-run window MUST raise needs-attention naming the commit.

- Scenario: a red master whose suspect range holds three cancelled runs is bisected by re-running at most two of them,
  and the culprit names the earliest red commit with a green parent.
- Scenario: a cancelled run past the re-run window raises needs-attention naming the commit, and no revert is opened.

**Mechanism note.** GitHub re-runs a cancelled run on its own commit for 30 days (`gh run rerun <id>`), so no temporary
ref or `workflow_dispatch` on a SHA is needed. The reconciler already re-runs failed jobs for classification.

**Cost.**
- A core revise, a dev-tooling revise, and a reconciler change with tests.
- After that, a one-line `concurrency` stanza per member.
- A red-master episode on a busy repository takes about log2(n) extra CI runs and the same number of reconcile ticks
  to prove its culprit. Over n=5 cancelled runs that is about 3 runs.
- **Saves:** about 4,110 min/day fleet-wide, and every member keeps automatic revert.

## Option B: per-repository `cancel-in-progress` on master, only where no reconciler caller exists (interim)

Add to `ci.yml` of livespec-dev-tooling and livespec-orchestrator-beads-fabro:

```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'push' && github.ref == 'refs/heads/master' }}
```

Pair it with a guard (a conformance row or a check) that refuses this setting in any member that calls the
master-health reconciler. Retire it when option A lands.

**Cost.**
- Two workflow edits, which are host-only and need the workflow-edit exemption, plus the guard.
- **Saves:** about 4,107 min/day today, 99.9% of the fleet saving.
- **Caveat:** core already requires every fleet repository to carry the reconciler. Both of these repositories are
  short of that today, so adopting the reconciler later forces removing this setting unless option A has landed. The
  interim is honest only if option A is the planned end state.
- Pull-request runs are unchanged by this stanza, because it cancels only master pushes.

## Option C: keep cancelling by hand, in open merge gaps only

**Cost.** None in code. About 68 runner-hours/day of waste continues outside gaps, along with master-lane queue delay
on every merge burst. A session has to be awake and authorized to act, which is the "a person notices" pattern the
coverage post-mortem (`006-coverage-fallback-post-mortem-2026-11-06.md`) set out to remove.

## Recommendation

**B now, A as the end state.**
- B takes 99.9% of the saving at once, for two workflow lines and a guard, in the two repositories with no reconciler
  caller.
- A is filed as the core-plus-realization change before either repository adopts the reconciler. It is what makes
  cancellation safe everywhere, and it retires B.
- C is the fallback only if the maintainer wants every master commit to keep its own verdict regardless of cost.
