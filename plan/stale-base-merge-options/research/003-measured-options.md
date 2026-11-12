# 003 — Measured options for stale-base merges, and one recommendation

Written 2026-11-12 ~18:4xZ by the plan seat of `stale-base-merge-options` (epic livespec-dev-tooling-xowhol). Every
number below is named: where it comes from, its window and its sample. Read note 002 first for the prior decisions.

**Nothing here is decided.** The maintainer decides the direction (coordinator-duties §9). GitHub's own merge queue is
unavailable: the account is personal (maintainer, 2026-11-12, twice). It appears below only to be excluded.

## The measurements

Window: 2026-10-15T00:00Z to 2026-11-12T00:00Z (28 days) unless stated.

**Data and scripts.** Everything is committed under `data/2026-11-12/` next to this note. The scripts are stored as
`*.py.txt`, so the repository's Python gates do not treat analysis scripts as product code; run them as
`python3 <name>.py.txt`.
- `fetch.py` pulls the raw gh API dumps of merged PRs and `ci.yml` runs.
- `analyze.py` writes `rows/<repo>.rows.json` (one row per merged PR: head-CI start and end, merge time, behind count,
  merge commit) and `summary.json`.
- `episodes.py` writes `summary2.json` (M4) and reads `rows/<repo>.master-runs.json`.
- `overlap.py` writes `summary3.json` (M5).
- `batch_sim.py` runs the batching replay, with a failure-rate parameter.
- `classify.py` writes `refs.json` (note 004).

The raw dumps themselves are not committed: `fetch.py` regenerates them in about 20 minutes.

### M1. Merge cadence (gh API, merged pull requests)

| Repository | Merged PRs | Per day | Peak day | Peak hour | Hours with 3 or more merges | Median gap between merges |
|---|---|---|---|---|---|---|
| livespec-orchestrator-beads-fabro | 1,688 | 60.3 | 93 | 10 | 302 | 13.6 min |
| livespec-dev-tooling | 1,518 | 54.2 | 132 | 13 | 242 | 10.1 min |
| livespec-overseer | 424 | 15.1 | 40 | 6 | 36 | 43.3 min |
| livespec | 327 | 11.7 | 31 | 5 | 12 | 59.4 min |
| six smaller members | 78 to 278 each | 2.8 to 8.6 | 13 to 46 | 4 to 5 | 4 to 18 | 54 to 139 min |

The two busiest repositories carry 3,206 of 4,940 fleet merges (65%). The 2026-10-14 charter of red-master-self-healing
measured 46 and 14 merges a day for those two, so dev-tooling has grown about fourfold since.

### M2. How often a pull request merges on a stale base

"Behind" counts the other pull requests that merged between the start of the PR's final-head CI run and the PR's own
merge. The PR CI run tests `refs/pull/N/merge` (the head merged onto the base as it stood when the run began), so a PR
with behind ≥ 1 merged a combination that no CI run ever tested. Source: gh API runs of `ci.yml` (event
`pull_request`, matched to the PR's head SHA), joined to M1.

| Repository | Behind ≥ 1 at merge | Behind p50 | Behind p90 | PR CI wall-clock p50 / p90 |
|---|---|---|---|---|
| livespec-dev-tooling | **56.0%** | 1 | 5 | 13.5 / 52.4 min |
| livespec-orchestrator-beads-fabro | **43.6%** | 0 | 2 | 10.2 / 40.2 min |
| livespec-overseer | 10.8% | 0 | 1 | 5.1 / 19.0 min |
| livespec | 4.9% | 0 | 0 | 3.4 / 8.0 min |
| six smaller members | 1.2% to 9.8% | 0 | 0 | 1.9 to 7.0 / 5.2 to 15.2 min |

### M3. What one CI run costs (Honeycomb, environment `livespec`, dataset `github-ci`, 14 days to 2026-11-12 ~18:0xZ)

- **Runner-minutes per run.** Query `m9QwWrm8ruz` sums the `duration_ms` of `ci.job.*` spans per `ci.run_id`, over push
  runs that reached `ci-green`. Spans with a duration below 0 or above 6 h are excluded, because some job spans carry
  epoch-sized durations.
- **Wall-clock per run.** Query `pFSBpRRfMyR` takes the `ci.run` root span, push event, runs with a `ci-green` child.

| Repository | Runner-minutes per run | Master run wall-clock p50 / p90 | Runs (14 d) |
|---|---|---|---|
| livespec-orchestrator-beads-fabro | 61.95 | 23.7 / 51.8 min | 788 |
| livespec-dev-tooling | 33.31 | 21.3 / 78.7 min | 657 |
| livespec-overseer | 14.01 | 6.5 / 20.1 min | 175 |
| livespec | 9.70 | 4.2 / 9.7 min | 132 |

The `github-ci` export carries master push runs; it carries `pull_request` runs only for the console repository. The PR
gate equals the master gate (livespec NFR §"CI as a merge gate", "PR gate ≡ master gate"), so the per-run master cost
is used as the cost of a PR re-run.

**Why the 14-day total is larger than runs × runner-minutes.** Query `dq5Vp19xjc8` sums job spans over ALL 990
dev-tooling push runs: 33,118 runner-minutes. That includes runs the B' master-push group cancelled partway, so they
reach no `ci-green`. The per-run figure (`m9QwWrm8ruz`) divides over the 657 runs that DID reach `ci-green`:
657 × 33.31 = 21,885. The difference, about 11,200 runner-minutes in 14 days, is spend on runs that never produced a
verdict. That is the same superseded-run waste plan ci-runtime-and-cost measured on 2026-11-09. The baseline below uses
the larger, all-runs total because that is what the runners actually spent. The per-run figure is used to price
re-runs, because a queue re-run is a run that completes.

**Baseline for scale (28 days).**
- livespec-dev-tooling: 2,337 PR CI runs × 33.31 + master 2 × 33,118 (Honeycomb `dq5Vp19xjc8`, 14 d) ≈ **144,000
  runner-minutes**.
- Orchestrator: 2,772 × 61.95 + 2 × 51,651 ≈ **275,000 runner-minutes**.

### M4. What stale-base merges cost today: red master (gh API master push runs)

An "episode" runs from the first completed failing master run after a green one to the next completed green one.

| Repository | Episodes | Hours red | Episode p50 / p90 | Episodes that start on a merge whose PR was green and behind ≥ 1 |
|---|---|---|---|---|
| livespec-dev-tooling | 38 | 13.3 | 18.5 / 51.7 min | 22 (5.9 h) |
| livespec-orchestrator-beads-fabro | 35 | 10.2 | 13.0 / 48.0 min | 20 (4.7 h) |
| livespec-overseer | 10 | 19.5 | 52.0 / 704.6 min | 2 |
| livespec | 1 | 1.1 | 66 min | 0 |

The last column is an UPPER bound on stale-base breaks: it also counts flakes and infrastructure failures that landed on
such a merge.
- A run whose failed jobs were re-run and passed shows only its final conclusion, so flake episodes cleared by re-run do
  not appear here at all.
- The B' master-push group cancels pending runs, so the first failing completed run is not always the culprit's.
- **Today, outside the window.** livespec-dev-tooling#4339 merged at 16:09Z on a base without #4330. Master read red
  from 16:52:20Z. The fix #4357 merged 17:40:49Z, and its master run 43271983614 was still running at 18:28Z.

### M5. Would a "re-test only when files overlap" rule have caught them? (local git, 28 days)

For each behind PR, compare its changed files (`git diff --name-only` between consecutive merge commits on master) with
the files of the merges it missed.

| Repository | Behind PRs | Of those, overlapping files | Red-episode starts on a behind green PR | Of those, overlapping |
|---|---|---|---|---|
| livespec-dev-tooling | 850 | 51 | 22 | **0** |
| livespec-orchestrator-beads-fabro | 736 | 34 | 20 | **2** |
| livespec-overseer | 46 | 7 | 2 | 1 |

Today's pair did overlap: both changed `ci-runner/k3s/phase2/reconstruct/converge-ci-stack.sh`. Across the window,
though, an overlap-gated re-test would have caught at most 3 of 44 episode starts. **It is cheap and nearly blind**, so
it is not offered as an option.

## The options, replayed against the real merge sequence

Each option was replayed over the 28-day sequence of M1 and M2, using each PR's own measured CI wall-clock as its re-run
duration and M3's runner-minutes per run as its cost.

Assumptions, which are kept deliberately simple:
- every re-run and every batch passes, so no bisection is modelled;
- runner capacity is unlimited, so queueing for runners is not modelled;
- the base time is the start of the final-head CI run.

"Added latency" is simulated merge time minus actual merge time.

### (a) Require branches up to date (`strict`), with an updater

GitHub's own update under auto-merge MERGES master into the branch. That is why v126 turned `strict` off, and
`allow_update_branch` is false on every member. So `strict` only works with a rebase updater bot, and the bot is one of
two shapes:

| Shape | Repository | Extra CI runs (28 d) | Extra runner-minutes | Added latency p50 / p90 |
|---|---|---|---|---|
| **Eager** (rebase every behind PR on every merge) | livespec-dev-tooling | 130,854 | 4,358,747 (≈30× today's total) | 6 min / 201 h |
| | orchestrator | 48,413 | 2,999,185 (≈11×) | 0.3 min / 15 h |
| **Lazy, one at a time** (rebase and re-test only the PR at the head of the line; Kodiak's model) | livespec-dev-tooling | 1,065 | 35,475 (+25%) | **31.6 h** / 256 h |
| | orchestrator | 1,041 | 64,490 (+23%) | 11.6 min / **83 h** |
| either shape | overseer | 59 to 139 | 827 to 1,947 | ≈0 / 2 to 14 min |
| either shape | livespec | 17 | 165 | ≈0 |

- **Eager** is the N² treadmill the maintainer rejected on 2026-10-14. The measurement confirms it.
- **Lazy** is the "serialized merge train". On the two busy repositories the line never drains: re-runs take longer than
  the gaps between merges (M1's median gap is 10-14 min, and M2's re-run p50 is 10-14 min with a 40-52 min p90), so the
  delay grows without bound across the window.
- On the quiet repositories either shape is cheap, but those repositories rarely go red this way (M4).

### (b) A self-built merge queue

- **Serializer.** One PR at a time, re-test when behind. This is (a)-lazy above, with the same numbers. It does not scale
  to the busy repositories.
- **Batching train.** When the train is free, take every ready PR, test their combined tip in ONE CI run, and merge all
  of them on green. A single up-to-date PR merges directly. On red: bisect (not modelled), and halt while master is red.

| Repository | Extra CI runs (28 d) | Extra runner-minutes | Share of baseline | Batch size p50 / p90 / max | Added latency p50 / p90 / max |
|---|---|---|---|---|---|
| livespec-dev-tooling | 447 | 14,890 | **+10%** | 1 / 3 / 22 | **18 min / 112 min** / 6.1 h |
| orchestrator | 646 | 40,020 | **+15%** | 1 / 2 / 13 | **8 min / 66 min** / 2.9 h |
| overseer | 45 | 630 | under +5% | 1 / 1 / 4 | ≈0 / 8 min |
| livespec | 17 | 165 | under +5% | 1 | ≈0 |

**Sensitivity: when batches fail.** The table above assumes every batch passes. `batch_sim.py` adds a per-PR failure
probability `p`: a failed batch is bisected into halves, and each half is one more CI run. Two values of `p` were
measured on the same 28 days:
- the per-run failure rate of master push runs (`rows/<repo>.master-runs.json`): failures over completed verdicts,
  3.3% for dev-tooling (44 of 1,333) and 2.4% for the orchestrator (40 of 1,646). This is the best proxy for green
  code failing CI: flakes, infrastructure and semantic conflicts;
- the PR CI failure rate: 11.3% for dev-tooling (262 of 2,318) and 6.8% for the orchestrator (186 of 2,750). It is an
  upper bound, because it includes PRs that were genuinely red, which never enter a queue.

| Repository | p | Extra runner-minutes | Added latency p50 / p90 / max |
|---|---|---|---|
| livespec-dev-tooling | 0 | 14,890 | 18 min / 112 min / 6.1 h |
| livespec-dev-tooling | 3% | 14,790 | 20 min / **4.1 h** / 11.1 h |
| livespec-dev-tooling | 5% | 14,756 | 23 min / **6.1 h** / 10.8 h |
| livespec-dev-tooling | 11.3% (upper bound) | 17,954 | **16 h / 95 h**: the single lane backs up |
| orchestrator | 0 | 40,020 | 8 min / 66 min / 2.9 h |
| orchestrator | 3% | 40,825 | 8 min / 75 min / 4.3 h |
| orchestrator | 6.8% (upper bound) | 41,135 | 9 min / 99 min / 9.8 h |

The CI cost barely moves. The **tail latency** does, sharply on dev-tooling. A single-lane batching queue on
dev-tooling is fragile to its own flake rate. It needs either parallel test lanes, which GitHub's merge queue provides
as "build concurrency" and which this replay does not model, or a lower flake rate. The +8-18 min median in the
comparison below holds; the p90 there should be read as 1.3-6 h on dev-tooling at measured failure rates.

What building it would take:
- one stateless module plus a hosted-runner shim, in the reconciler's mould;
- CI on its staging ref;
- merging through the API while keeping linear history and the Red-Green-Replay trailers;
- bisection;
- halting on red master;
- replacing GitHub auto-merge (`auto-enable-merge.yml`) for queued PRs, because armed auto-merge would merge outside the
  train;
- a factory interface (`merge-hold:on` today).

v126 rejected "a hand-rolled serialized auto-rebase driver" as "a fragile central loop that can orphan, mis-order, or
wedge PRs". A batching train is that kind of loop. A stateless, forge-is-the-state design (as in the reconciler) is the
known answer to "fragile", and it is real engineering.

### (c) Third-party tools (web research 2026-11-12; vendor pages, URLs in the plan's working notes)

| Tool | Personal account? | Price here | Model | Fit |
|---|---|---|---|---|
| **Mergify** | Not documented either way | **$0**, Open Source plan, "public repositories only"; bots do not count | Temp branch `mergify/merge-queue/*` with a draft PR; **batching, bisection, speculative checks** | Rebase method fine; needs a ruleset bypass for the app; armed GitHub auto-merge must stop; no automatic halt on red master (manual pause or API) |
| Trunk Merge Queue | Prerequisite reads "Admin access to your GitHub organization" | Free up to 5 committers; OSS "contact sales" | Draft PR or `trunk-merge/**`; batching, bisection, predictive | Probably org-only; unproven |
| Aviator MergeQueue | Setup mentions org admins only | Paid, $20/dev/month and up; no OSS plan | Draft PRs; batching | Paid; unproven on personal |
| Graphite MQ | Personal repos are on the free Hobby tier, which has no merge queue | $40/user/month (Team) | Speculative | **Unavailable** in practice |
| Kodiak | Not stated; $0 | $0 (AGPL, self-hostable) | Serial update-then-merge, no batching | It is (a)-lazy: **infeasible** at our cadence |
| bors-ng | — | — | Staging-branch batches | **Archived** 2024-04-04; makes merge commits (breaks linear history) |
| Bulldozer, Mergeable | — | — | Do not test the combined result | Not a fix |
| Prow Tide, Zuul | — | free | Bring their own CI system | Too heavy |
| GitHub merge queue | **No** on a personal account. GitHub documents it for PUBLIC repositories owned by an ORGANIZATION, on any plan; only private org repositories need Enterprise Cloud | $0 for public org repositories | Temp branch `gh-readonly-queue/*`, `merge_group` event, parallel groups ("build concurrency"), fast-forwards the tested commit | Excluded on the current account (maintainer, 2026-11-12). Fact recorded, not a recommendation: an org transfer would make it available. The transfer costs (URLs, marketplaces, a new org App, ARC re-registration, secrets, GHCR) are measured in note 004 |

Mergify is the only tool that is free for us and implements the batching train of (b). It costs (b)'s CI and latency
without building (b). Its two unknowns can only be settled by trying it, and the try is reversible:
- whether the app runs on a personal account;
- how its draft PRs route through our self-hosted ARC runners and the fork-safety rules.

### (d) The decided baseline: red-master-self-healing

- **What exists.**
  - The reconciler module and the reusable workflow, on master since 2026-10-31.
  - The incident-observer step, since 2026-11-10.
  - livespec's shim, since 2026-10-31.
- **What is missing.**
  - The shim in livespec-dev-tooling (`livespec-dev-tooling-okij46`, BLOCKED) and in the orchestrator. Both are held by
    the B' ruling (coordinator-duties §10): no adoption "before A lands unless B's setting is removed first".
  - **Option A has no work item**: no item in the dev-tooling or livespec ledger has the reconciler re-run a cancelled
    master run before naming a culprit. A needs a livespec propose-change plus a dev-tooling realization.
  - The watch-the-watcher row (`4xrhck`) and the drill (`yilv6p`), which sit at pending-approval.
  - The plan epic (zcp5vb) has been parked since 10-19 on a stale gate.
  - **Distance to shipping in the busy repositories**: option A (spec change plus code), then two shim adoptions. That is
    one spec revise and about three implementation items.
- **What it would have done today.**
  - Master read red at 16:52:20Z. The culprit's own run (b9838b28c) and the next one were CANCELLED by B'. So even if
    armed, today's reconciler could not have named the culprit: that is exactly the gap A closes.
  - With A, it would re-run the cancelled runs (≈21 min, M3's p50), revert, run the revert's PR CI (≈13.5 min) and master
    CI (≈21 min). That puts green at about 17:48Z to 18:00Z.
  - The roll-forward was still not green at 18:28Z, so the reconciler would have saved roughly half an hour or more.
  - It **prevents nothing**: the red happens first, and the factory's green-master gate stops dispatch for the episode.
    By design it costs no CI on the happy path.

## The options side by side (the two busy repositories; 28-day replay)

| Option | Stops stale-base reds? | Extra CI | Merge latency | Build cost | When master is red |
|---|---|---|---|---|---|
| 0. Status quo plus the finished reconciler | No; shortens them | none | none | option A, then 2 adoptions | reverts the culprit |
| 1. `strict` plus eager updater | Yes | **11-30× today's total** | p90 15-201 h | small bot | stalls |
| 2. `strict` plus lazy updater (= serializer, = Kodiak) | Yes | +23-25% | **p50 up to 31 h; the line never drains** | small bot | stalls |
| 3. Self-built batching train | Yes, except bisection misses | **+10-15%** | **p50 +8-18 min, p90 +66-112 min** if every batch passes; p90 1.3-6 h on dev-tooling at measured failure rates | large: a new stateless service | halts (by design) |
| 4. Mergify (free) batching queue | Yes, as 3 | as 3 (+10-15%) | as 3 | small: config, a ruleset bypass, and retiring auto-enable-merge for those repositories | manual or API pause; the reconciler can call it |
| 5. Overlap-gated re-test | Barely (3 of 44 episode starts) | +1-2% | small | medium | — |

On the quiet repositories (overseer, livespec and the six smaller ones), 1-11% of merges are behind and red episodes
from this cause are rare. Every option is either cheap or pointless there, so this is a two-repository problem.

## Recommendation (as first written; superseded, see below)

> **Superseded 2026-11-12 ~19:0xZ.** The maintainer disfavoured third-party tools in the merge path (scope event on
> livespec-dev-tooling-xowhol). The seat then recommended option 3, and then, after the maintainer asked about GitHub's
> own queue, a fleet move to an organization with GitHub's merge queue, subject to the two checks of note 004. The
> maintainer has not chosen a direction. The original text is kept below for the record.

**Pilot Mergify's free merge queue in batch mode on livespec-dev-tooling, keep red-master-self-healing as the backstop
by filing option A, and extend the queue to the orchestrator only if the pilot holds its numbers.**

Why:
- It is the only option that **prevents** this failure at an affordable price. A batching queue costs about +10-15%
  runner-minutes and a median of +8-18 minutes per merge.
- `strict` is unaffordable in either shape at today's cadence: the eager updater is the N² treadmill (11-30× the
  current CI bill) and the lazy one is a line that never drains.
- Buying the batching train for $0 avoids building the "fragile central loop" that v126 warned against.
- The reconciler is still needed, because no queue stops flakes, infrastructure reds or bisection misses.

The pilot measures what the replay assumed: real batch failure and bisection rates, real latency, and the CI and runner
behaviour of the app's draft PRs on ARC.

What it costs to try (all reversible):
- one GitHub App install on the personal account;
- a `.mergify.yml`;
- a ruleset bypass for the app;
- stopping `auto-enable-merge.yml` from arming GitHub auto-merge on livespec-dev-tooling, replaced by queueing through
  Mergify. That is a workflow edit, so it needs the workflow-edit approval;
- a hook from the factory's merge-hold release into the queue.

Stop rule: if Mergify cannot be installed on a personal account, or its draft PRs cannot get a `ci-green` verdict on our
runners, the fallback is option 3, the self-built batching train, built in the reconciler's stateless mould.

## Two interactions the maintainer weighs with option 4 (raised by the coordinator, 2026-11-12 ~18:5xZ)

- **Security: an outward-facing grant.** Mergify is a third-party GitHub App. Installing it grants write access
  (contents, pull requests, checks) to every repository it covers, and the ruleset needs a bypass entry for it. That is a
  maintainer security call, independent of the CI numbers. The pilot limits it to livespec-dev-tooling by installing the
  app on selected repositories only.
- **`auto-enable-merge.yml`.** It arms GitHub auto-merge (`gh pr merge --auto --rebase`) on every pull request opened by
  the owner, or by the factory bot for release PRs. With `strict` off, GitHub merges an armed PR as soon as `ci-green`
  passes on the PR, outside any queue. So a queued repository must either stop arming auto-merge there and enqueue
  through Mergify, or require a Mergify queue status check so that auto-merge waits for it. The pilot must prove the
  second approach before relying on it. Either way it is a workflow edit and needs the workflow-edit approval.
- **The B' master-push group.** Mergify tests on its own draft PRs, which run `pull_request` CI, so B' does not touch
  the queue's tests. A landed batch still pushes master once per PR, and B' keeps only the in-progress run and the
  newest pending one, as today. Fewer stale-base reds also means fewer episodes whose culprit run B' cancelled, which is
  the case option A exists for.

## Option A is filed regardless of the queue decision

The coordinator directs, per the 2026-11-09 ruling, that option A be filed now whatever the queue decision. B' and the
orchestrator preflight fix (bd-ib-kbfd3s, closed 2026-11-09) are both on master, which were its preconditions. Option A:
the reconciler re-runs a cancelled master run in the suspect range before naming a culprit, and never names a culprit
from an unverdicted commit. It is filed as a livespec core propose-change plus a dev-tooling realization item. It
belongs to red-master-self-healing (zcp5vb), not to this plan's queue decision.

## Questions only the maintainer can answer

1. Direction: which option (0 to 5), or another.
2. Is an outside SaaS (Mergify) acceptable in the merge path, given the fleet's GitOps posture and that the app gets write
   access?
3. Do the earlier rejections of `strict` stand? The numbers above say they should.
4. The Definition of Done of this plan is session-derived. Does it say what done means to you?

## Limits of these numbers

- The replays assume every re-run and batch passes and that runners are unlimited. Real bisection on red batches and
  runner queueing would add CI and latency to options 1-4.
- "Behind" uses the start of the final-head CI run as the base time.
- M4 cannot separate genuine stale-base breaks from flakes, because re-run-cleared failures are invisible and B' cancels
  runs.
- Third-party facts are from vendor pages read 2026-11-12, and none of them states personal-account support. Only an
  install settles it.
- The scripts and per-PR rows are committed under `data/2026-11-12/`. The raw gh API dumps are not; `fetch.py`
  regenerates them.
