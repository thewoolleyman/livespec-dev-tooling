# 002 — Red-master episode calibration (child F, livespec-dev-tooling-s7ctpr)

Measured 2026-10-14 from a HOST session, using read-only `gh api` calls (cached, serial). The window is **2026-08-14T00:00Z to
2026-10-14 (61 days)**. It covers all ten `fleet` members of livespec's `.livespec-fleet-manifest.jsonc`. No repository setting
was read for write or changed.

This note calibrates the reconciler's per-step stall durations and the hard cap (charter §"Open maintainer calls" 2 and 3).
Child C2 (livespec-dev-tooling-joqff6) consumes the result.

## Method

- **Gating workflow.** Every fleet repo's required check is `ci-green`, the final job of the workflow named `CI` (`ci.yml`).
  console-beads-fabro also requires `upstream-dep-gate-wired` from a separate `gate-wiring` workflow, which this note does not
  measure. The source is every `CI` run with `branch=master, event=push` created in the window: 5,834 runs. The API's
  1,000-result cap truncated two repos (orchestrator-beads-fabro and overseer), so they were refetched in 5-day windows.
- **Verdict timeline.** Each run attempt is an event at its completion time; earlier attempts were read through
  `/runs/{id}/attempts/{n}`. Master's state at time *t* is the latest attempt's conclusion for the newest-pushed commit with a
  completed verdict. Cancelled runs carry no verdict.
- **Episode.** A maximal interval in which that state is `failure`. It starts at the first red verdict's completion and ends
  at the first green verdict's completion. 154 episodes were found, and none was still open at measurement time.
- **Ending.** The commit whose green ended the episode:
  - **re-run of same SHA**: a red SHA turned green on a later attempt.
  - **revert**: the subject starts with `Revert` or `revert`.
  - **fix-forward**: anything else.
- **Classes.** Each episode gets one class, applied in this order:
  1. `flake`: green came from a re-run of a red SHA.
  2. `infra`: every failing job other than `ci-green` and `export-telemetry` failed only in a setup step (`Initialize
     containers`, `Set up job`, `Install Python dev deps via uv`, `mise trust + install`, `Checkout`, `Stop containers`, and
     similar).
  3. `pin`: the culprit commit is a `chore(deps): bump … pin` commit.
  4. `revert`: ended by a revert.
  5. `fix-forward`: ended by a PR that was opened AFTER the red start and is a plausible fix. Plausible means it touches a
     file the culprit touched, its subject starts with `fix`/`test`/`chore(test…)`, or it touches `tests/`, `.github/`,
     `justfile` or a `*.toml`.
  6. `self-cleared`: none of the above. Usually the next unrelated commit, often already in flight before the red, came back
     green with no fix. One release-please PR that the heuristic matched through `pyproject.toml` was moved by hand to
     `self-cleared`.

  The classes are heuristics. The table below lets a reader reclassify any row.
- **Step times** are taken from the ending PR (the "fix PR") of genuine episodes (`revert` + `fix-forward`, n = 27):
  - red → fix PR `created_at`
  - `created_at` → `merged_at`
  - `merged_at` → master green

  Percentiles are linear-interpolated. All times are minutes.

## Headline: episode counts and red duration by class

| class | n | median red | p90 red | max red |
| --- | ---: | ---: | ---: | ---: |
| revert (genuine) | 7 | 36.4 | 86.0 | 121.8 |
| fix-forward (genuine) | 20 | 87.5 | 661.7 | 1341.6 |
| self-cleared (no fix landed) | 39 | 16.9 | 118.7 | 830.5 |
| flake (green on re-run) | 36 | 26.5 | 474.6 | 1300.3 |
| infra (setup-step failure only) | 44 | 31.6 | 1205.2 | 2541.4 |
| pin (toolchain pin bump culprit) | 8 | 134.6 | 916.4 | 1165.7 |
| **all** | **154** | **33.9** | **633.6** | **2541.4** |

Ending kind, all 154 episodes: 36 re-run of the same SHA, 7 revert, 111 fix-forward. Only 27 of the 111 fix-forward endings
were a genuine fix.

Per repo (episodes, then classes):

| repo | episodes | classes |
| --- | ---: | --- |
| livespec | 21 | infra 12, fix-forward 4, self-cleared 2, flake 2, pin 1 |
| livespec-dev-tooling | 18 | flake 8, infra 5, fix-forward 2, self-cleared 2, pin 1 |
| livespec-driver-claude | 7 | flake 5, pin 1, infra 1 |
| livespec-driver-codex | 8 | infra 4, flake 3, fix-forward 1 |
| livespec-driver-pi | 3 | self-cleared 1, flake 1, infra 1 |
| livespec-orchestrator-beads-fabro | 15 | revert 5, fix-forward 3, self-cleared 3, infra 2, flake 2 |
| livespec-orchestrator-git-jsonl | 4 | infra 3, pin 1 |
| livespec-runtime | 7 | infra 4, flake 2, pin 1 |
| livespec-console-beads-fabro | 27 | self-cleared 12, fix-forward 9, flake 6 |
| livespec-overseer | 44 | self-cleared 19, infra 12, flake 7, pin 3, revert 2, fix-forward 1 |

## Per-step medians and p90 (genuine episodes)

| step | population | n | median | p90 | max |
| --- | --- | ---: | ---: | ---: | ---: |
| master red → fix PR opened | revert + fix-forward | 27 | 56.3 | 409.7 | 1333.3 |
| | revert only | 7 | 22.7 | 51.3 | 56.3 |
| | fix-forward only | 20 | 68.4 | 608.7 | 1333.3 |
| fix PR opened → fix merged | revert + fix-forward | 27 | 5.8 | 49.8 | 118.3 |
| | revert only | 7 | 5.7 | 34.7 | 74.8 |
| | fix-forward only | 20 | 5.9 | 40.9 | 118.3 |
| fix merged → master green | revert + fix-forward | 27 | 5.2 | 12.6 | 18.9 |
| | revert only | 7 | 3.8 | 6.0 | 6.5 |
| | fix-forward only | 20 | 5.7 | 13.0 | 18.9 |
| total red | revert + fix-forward | 27 | 70.9 | 434.5 | 1341.6 |
| | revert only | 7 | 36.4 | 86.0 | 121.8 |
| | fix-forward only | 20 | 87.5 | 661.7 | 1341.6 |

Reading the table:

- The first step dominates. Once a fix PR exists, it merges in a median of about 6 min and master is green about 5 min later.
- The long tail of "red → fix PR opened" is unattended time, such as overnight and sessions not watching. It is not engineering
  time. The revert-only row is the closest measurement of an ATTENTIVE actor: someone was watching and acted, and opened the
  PR within 56 min every time.
- At a 2 h hard cap, 8 of 27 genuine episodes (7 of 20 fix-forwards) would have hit the cap. All of them ran 122–1342 min,
  and the ≥ 600 min ones spanned unattended hours. Every revert-ended episode finished within 122 min.

## Master CI duration per repo (bounds the "CI running" step)

Time from run created to completed, first attempt, success or failure. `run_started_at` equals `created_at` at the run level,
so the job-queue wait is inside these figures.

| repo | n | median | p90 |
| --- | ---: | ---: | ---: |
| livespec | 439 | 3.3 | 14.0 |
| livespec-dev-tooling | 977 | 4.4 | 11.7 |
| livespec-driver-claude | 217 | 3.6 | 14.4 |
| livespec-driver-codex | 183 | 3.3 | 16.3 |
| livespec-driver-pi | 209 | 2.1 | 9.9 |
| livespec-orchestrator-beads-fabro | 1397 | 4.8 | 9.9 |
| livespec-orchestrator-git-jsonl | 195 | 3.0 | 12.9 |
| livespec-runtime | 163 | 3.2 | 16.2 |
| livespec-console-beads-fabro | 564 | 5.4 | 13.2 |
| livespec-overseer | 1490 | 3.2 | 9.7 |
| **fleet** | **5834** | **4.0** | **11.3** |

For comparison, the charter measured orchestrator-beads-fabro at median 6.4 / p90 10.5 over 26 runs in one day. Over 61 days
the median is lower and the p90 agrees.

## Proposed defaults (for child C2's committed config)

Rule: **stall = p90 of the measured step × 1.5, rounded up to 5 min.** Any forward transition named in charter design point 5
restarts the step clock.

| reconciler step (no forward transition within) | measured basis | p90 | × 1.5 | **proposed default** |
| --- | --- | ---: | ---: | ---: |
| any CI run in flight: the classification re-run, the revert PR's CI, the fix PR's CI, master CI on the fix | fleet master CI duration | 11.3 | 17.0 | **20 min** (per repo below) |
| fix-forward claim → fix PR opened / new commit pushed | red → PR opened, attentive actor (revert-only population) | 51.3 | 77.0 | **80 min** |
| fix PR opened → fix merged (any push, CI start or CI result restarts it) | PR opened → merged, genuine | 49.8 | 74.7 | **75 min** |
| fix merged → master green | merged → green, genuine | 12.6 | 18.9 | **20 min** |

Per-repo CI stall (p90 × 1.5, rounded up to 5):

| 15 min | 20 min | 25 min |
| --- | --- | --- |
| driver-pi, orchestrator-beads-fabro, overseer | dev-tooling, orchestrator-git-jsonl, console-beads-fabro | livespec, driver-claude, driver-codex, runtime |

The claim → PR step deliberately uses the attentive population. The all-genuine fix-forward p90 (608.7, giving 915 min) is
idle time, and is exactly what the stall rule exists to cut off. A claimed fix comes from a session that is actively working,
and the claim itself comes after the red start, so 80 min is generous for that population.

**Hard cap: 120 min**, which matches the maintainer's example. The cap is derived two ways:

- **Attentive path.** The per-step p90s on the attentive path sum to 51.3 + 49.8 + 12.6 = 113.7 min. Rounded up, that is
  120 min, a margin of about 1.06.
- **Cross-check.** Every revert-ended episode finished within 121.8 min. The revert-ended p90 is 86.0 × 1.4 = 120 min.

A fix-forward that has not landed by the time a revert would have reliably finished has lost its advantage. At this cap, 35%
of historical fix-forwards (7 of 20) would have been reverted. All seven were over 2 h and most spanned unattended hours. That
is the intended outcome.

The E1 detector (red with no revert PR in flight) is not asked for here. The basis it should use: two reconcile cycles
(2 × 5 min) plus the per-repo CI stall gives about **30 min**.

## Findings a revert-by-default reconciler would mishandle

1. **Only 27 of 154 episodes (18%) were genuine regressions.** The other 127 split into 36 flakes, 44 infra failures, 39
   self-cleared episodes and 8 pin bumps. The "re-run once" classification in design point 4a catches the 36 flakes. It does
   not obviously catch the next two groups.
2. **39 self-cleared episodes: a later unrelated commit went green with no fix.**
   - 19 are in overseer and 12 in console-beads-fabro.
   - overseer: 15 are `check-per-file-coverage` reds, 8 of them on `chore(master): release …` (release-please) commits. The
     next push cleared each within 1–3 min; on 2026-08-22 there were 6 inside 4 h.
   - If that verdict depends on commit shape (a release commit touches no `.py`), a re-run of the same SHA fails again and
     the reconciler would REVERT A RELEASE COMMIT. Its tag and release would then disagree with master. This is a
     metadata/shape-invariance suspect for child B (yfqvqm).
   - Independent of that, C1 needs a **superseded-green rule**: once a later non-revert master commit is green, close the
     held revert. Culprit selection should also exclude release-please commits, or route them to needs-attention.
3. **console-beads-fabro `check-e2e-tmux` is chronically flaky.** It failed in 25 of that repo's 27 episodes, mostly cleared
   by docs commits. Charter signal (a), "the failure also appears on unrelated commits", needs per-check flake history to be
   effective here. Otherwise the reconciler reverts innocent `docs(plan)` merges.
4. **The "infra = setup step failed" heuristic misfires on toolchain pin bumps.**
   - The dev-tooling v1.37.1 (2026-09-01) and v1.40.0 (2026-09-02) bumps broke `Install Python dev deps via uv` in driver-codex,
     driver-pi, orchestrator-git-jsonl and overseer. Those repos stayed red for 19–22 h until the next release (rows classed
     `infra` above).
   - Those failures are caused by the commit, not by an outage. One upstream release reddens N repos at once.
   - Reverting the bump is correct locally, but the pin-freshness / bump-pin shim will re-bump. The reconciler and the bump
     shim need a rule, for example "revert the bump and hold re-bumps until the next upstream release".
5. **The triggering incident is the third of its kind in five days.** orchestrator-beads-fabro master went red on
   `check-heading-coverage-debt-register` (inside `check-metadata-batch`) on three `chore(spec): ratify …` merges:
   - 2026-10-10 03:20Z, #2742, reverted by #2743 after 36 min
   - 2026-10-11 23:02Z, #2794, reverted by #2797 after 28 min
   - 2026-10-14 01:17Z, #2917, reverted by #2918 after 33 min

   Those are 3 of the fleet's 7 episodes since 2026-09-10. All three are the a6gq5n class, which reinforces child B and
   carrier a6gq5n. Each revert also had to be re-landed.
6. **Low-traffic repos stay red for a day on flake/infra because nothing re-runs CI.** The longest were orchestrator-git-jsonl
   at 2541 and 1298 min, dev-tooling 1502, runtime 1477, driver-codex 1300 and overseer 1212. Master turns green only when the
   next push arrives. The classification re-run alone would shorten those 80 episodes (p90 8–20 h) to about one CI duration,
   with no revert at all.
7. **Temporal skew.** 147 of 154 episodes fall between 2026-08-14 and 2026-09-09, the k3s/ARC cutover era (infra
   concentration). Only 7 are later. Re-measure after C1 ships before tightening any default.

## Per-episode list (all 154)

Times are UTC. "class" is the heuristic above. The PR shown for flakes is the culprit PR. For other classes, "ending SHA (PR)"
is the commit whose green ended the episode, and its PR's opened/merged times feed the step table. An "ending PR opened" time
earlier than the red start means the ending PR was not a reaction to the red.

| # | repo | red start (UTC) | green (UTC) | red min | class | ending | culprit SHA (PR) | ending SHA (PR) | ending PR opened / merged (UTC) | failing jobs |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | livespec | 2026-08-14 03:54 | 2026-08-14 05:35 | 101 | infra | fix-forward | `d134fc6b` (#2284) | `cd6b892b` (#2287) | 08-14 04:16 / 08-14 05:12 | coverage-incremental, self-hosted-routing |
| 2 | livespec | 2026-08-14 06:25 | 2026-08-14 06:47 | 22 | infra | fix-forward | `d95e699b` (#2290) | `a197c058` (#2291) | 08-14 05:41 / 08-14 06:06 | shell-quality |
| 3 | livespec | 2026-08-14 07:03 | 2026-08-14 07:44 | 41 | fix-forward | fix-forward | `b13d3d12` (#2293) | `f88f2799` (#2296) | 08-14 07:30 / 08-14 07:36 | aggregate-completeness, canonical-recipe-fidelity, no-dir... |
| 4 | livespec | 2026-08-14 08:14 | 2026-08-14 08:29 | 15 | fix-forward | fix-forward | `b04fbf46` (#2297) | `d506e35b` (#2298) | 08-14 08:16 / 08-14 08:20 | aggregate-completeness, assert-never-exhaustiveness, beha... |
| 5 | livespec | 2026-08-14 08:47 | 2026-08-14 14:08 | 321 | infra | fix-forward | `af27773f` (#2299) | `57b83282` (#2302) | 08-14 13:28 / 08-14 13:36 | coverage-incremental, no-inheritance, source-trees-scoped... |
| 6 | livespec | 2026-08-14 14:58 | 2026-08-14 21:51 | 413 | infra | fix-forward | `a5213c15` (#2304) | `d9f05429` (#2312) | 08-14 21:25 / 08-14 21:34 | mutation, cli-explicit-project-root, codex-no-repo-local-... |
| 7 | livespec | 2026-08-14 22:48 | 2026-08-15 06:21 | 453 | infra | fix-forward | `a11585a3` (#2314) | `9edcee67` (#2319) | 08-15 06:07 / 08-15 06:13 | aggregate-completeness, coverage-incremental, mutation, c... |
| 8 | livespec | 2026-08-15 09:47 | 2026-08-15 10:50 | 64 | self-cleared | fix-forward | `dbc9c4d7` (#2316) | `5de08bbc` (#2326) | 08-15 10:18 / 08-15 10:42 | aggregate-completeness, behavior-scenario-link, canonical... |
| 9 | livespec | 2026-08-15 11:17 | 2026-08-15 11:40 | 23 | flake | re-run of same SHA | `47efcb4a` (#2327) | same SHA | — | comment-no-historical-refs, format, main-guard, match-key... |
| 10 | livespec | 2026-08-15 13:49 | 2026-08-15 14:23 | 34 | infra | fix-forward | `f2a8f468` (#2332) | `827294ff` (#2333) | 08-15 12:27 / 08-15 12:53 | plan-thread-no-tombstone, tests-mirror-pairing |
| 11 | livespec | 2026-08-15 14:36 | 2026-08-15 14:49 | 13 | infra | fix-forward | `50b6ca02` (#2335) | `e25174b1` (#2337) | 08-15 13:12 / 08-15 14:31 | schema-dataclass-pairing |
| 12 | livespec | 2026-08-15 14:57 | 2026-08-15 22:39 | 462 | infra | fix-forward | `1fcb3a38` (#2338) | `b83cbc0b` (#2341) | 08-15 22:28 / 08-15 22:33 | canonical-recipe-fidelity, cli-explicit-project-root, for... |
| 13 | livespec | 2026-08-15 22:49 | 2026-08-16 00:30 | 101 | self-cleared | fix-forward | `1003bb74` (#2342) | `e20d118a` (#2346) | 08-16 00:09 / 08-16 00:15 | assert-never-exhaustiveness, comment-line-anchors, covera... |
| 14 | livespec | 2026-08-16 08:24 | 2026-08-16 12:25 | 241 | pin | fix-forward | `5aff4661` (#2353) | `caf3603d` (#2356) | 08-16 09:08 / 08-16 12:17 | behavior-scenario-link, canonical-recipe-fidelity, covera... |
| 15 | livespec | 2026-08-16 22:05 | 2026-08-17 03:23 | 318 | fix-forward | fix-forward | `167bd788` (#2360) | `2fc9ecff` (#2372) | 08-17 03:19 / 08-17 03:21 | coverage, per-file-coverage |
| 16 | livespec | 2026-08-17 14:12 | 2026-08-17 14:25 | 12 | infra | fix-forward | `1e02390c` (#2389) | `d49b0798` (#2390) | 08-17 13:16 / 08-17 13:31 | per-file-coverage |
| 17 | livespec | 2026-08-17 15:14 | 2026-08-17 15:48 | 35 | infra | fix-forward | `5f3eea72` (#2392) | `9b738670` (#2394) | 08-17 14:19 / 08-17 15:05 | per-file-coverage |
| 18 | livespec | 2026-08-17 16:19 | 2026-08-17 16:24 | 6 | flake | re-run of same SHA | `f180b5b4` (#2395) | same SHA | — | doctor-static, types |
| 19 | livespec | 2026-08-25 15:36 | 2026-08-26 02:13 | 637 | infra | fix-forward | `7f0ed2b7` (#2491) | `143bb36e` (#2493) | 08-26 01:41 / 08-26 01:58 | coverage |
| 20 | livespec | 2026-08-26 10:09 | 2026-08-26 11:54 | 104 | fix-forward | fix-forward | `8a5f8d13` (#2498) | `6779b8f2` (#2499) | 08-26 11:42 / 08-26 11:49 | per-file-coverage |
| 21 | livespec | 2026-09-01 16:03 | 2026-09-01 16:17 | 14 | infra | fix-forward | `37fbf6de` (#2529) | `c835d529` (#2531) | 09-01 15:49 / 09-01 16:02 | coverage |
| 22 | console-beads-fabro | 2026-08-16 01:27 | 2026-08-16 05:39 | 252 | fix-forward | fix-forward | `e906f660` (#644) | `ceaeca14` (#646) | 08-16 03:38 / 08-16 05:36 | e2e-tmux |
| 23 | console-beads-fabro | 2026-08-18 00:14 | 2026-08-18 00:21 | 7 | flake | re-run of same SHA | `f5cc3da1` (#671) | same SHA | — | e2e-tmux |
| 24 | console-beads-fabro | 2026-08-18 01:59 | 2026-08-18 02:07 | 8 | flake | re-run of same SHA | `00ed7e17` (#672) | same SHA | — | e2e-tmux |
| 25 | console-beads-fabro | 2026-08-19 01:34 | 2026-08-19 03:25 | 111 | self-cleared | fix-forward | `407ac9db` (#680) | `52cefd07` (#682) | 08-19 00:00 / 08-19 01:26 | e2e-tmux |
| 26 | console-beads-fabro | 2026-08-19 03:54 | 2026-08-19 05:32 | 98 | fix-forward | fix-forward | `4748daff` (#689) | `90a71ee4` (#691) | 08-19 05:25 / 08-19 05:28 | e2e-tmux |
| 27 | console-beads-fabro | 2026-08-19 05:49 | 2026-08-19 05:56 | 7 | self-cleared | fix-forward | `acd82918` (#692) | `3851cc05` (#690) | 08-19 05:23 / 08-19 05:52 | e2e-tmux |
| 28 | console-beads-fabro | 2026-08-19 11:42 | 2026-08-19 12:48 | 66 | fix-forward | fix-forward | `80d2cc68` (#694) | `1f7cf9c3` (#698) | 08-19 12:11 / 08-19 12:32 | e2e-tmux |
| 29 | console-beads-fabro | 2026-08-19 23:14 | 2026-08-20 01:45 | 151 | flake | re-run of same SHA | `4d67a559` (#707) | same SHA | — | e2e-tmux |
| 30 | console-beads-fabro | 2026-08-26 14:09 | 2026-08-26 14:21 | 11 | self-cleared | fix-forward | `a8acb980` (#849) | `f7d6c782` (#851) | 08-26 13:24 / 08-26 14:09 | e2e-tmux |
| 31 | console-beads-fabro | 2026-08-27 03:58 | 2026-08-27 04:12 | 14 | self-cleared | fix-forward | `6e20d2fa` (#855) | `778c5094` (#856) | 08-27 03:56 / 08-27 04:04 | e2e-tmux |
| 32 | console-beads-fabro | 2026-08-27 13:19 | 2026-08-27 14:48 | 89 | fix-forward | fix-forward | `84e2cc32` (#861) | `a18e7411` (#862) | 08-27 14:34 / 08-27 14:40 | e2e-tmux |
| 33 | console-beads-fabro | 2026-08-27 22:30 | 2026-08-28 17:24 | 1134 | fix-forward | fix-forward | `b333fa00` (#866) | `0c3835a6` (#867) | 08-28 17:04 / 08-28 17:11 | e2e-tmux |
| 34 | console-beads-fabro | 2026-08-29 10:16 | 2026-08-29 10:21 | 5 | self-cleared | fix-forward | `02eba253` (#871) | `75a2be9b` (#872) | 08-29 09:50 / 08-29 09:57 | e2e-tmux |
| 35 | console-beads-fabro | 2026-08-29 12:46 | 2026-08-29 14:04 | 78 | self-cleared | fix-forward | `fded418e` (#876) | `15693452` (#879) | 08-29 13:46 / 08-29 13:57 | e2e-tmux |
| 36 | console-beads-fabro | 2026-08-29 17:48 | 2026-08-29 18:01 | 13 | fix-forward | fix-forward | `66fc0145` (#883) | `19763efe` (#884) | 08-29 17:49 / 08-29 17:55 | e2e-tmux |
| 37 | console-beads-fabro | 2026-08-30 00:07 | 2026-08-30 02:42 | 155 | flake | re-run of same SHA | `0c1edcd4` (#886) | same SHA | — | e2e-tmux |
| 38 | console-beads-fabro | 2026-08-30 06:10 | 2026-08-30 08:40 | 150 | self-cleared | fix-forward | `78554595` (#889) | `9f549085` (#890) | 08-30 07:12 / 08-30 07:59 | e2e-tmux |
| 39 | console-beads-fabro | 2026-08-30 11:04 | 2026-08-30 11:15 | 12 | flake | re-run of same SHA | `5f97c099` (#893) | same SHA | — | e2e-tmux |
| 40 | console-beads-fabro | 2026-08-30 13:10 | 2026-08-30 13:31 | 22 | flake | re-run of same SHA | `d1b0a7c0` (#894) | same SHA | — | e2e-tmux |
| 41 | console-beads-fabro | 2026-08-30 15:07 | 2026-08-30 16:58 | 111 | self-cleared | fix-forward | `856ec7bf` (#898) | `44888a1a` (#899) | 08-30 16:02 / 08-30 16:10 | e2e-tmux |
| 42 | console-beads-fabro | 2026-08-31 08:54 | 2026-08-31 09:30 | 35 | self-cleared | fix-forward | `d2525905` (#901) | `bee1b079` (#902) | 08-31 08:48 / 08-31 09:21 | e2e-tmux |
| 43 | console-beads-fabro | 2026-08-31 09:37 | 2026-08-31 09:58 | 21 | self-cleared | fix-forward | `c34571b9` (#903) | `a7dd7b4d` (#904) | 08-31 09:27 / 08-31 09:50 | e2e-tmux |
| 44 | console-beads-fabro | 2026-08-31 11:36 | 2026-09-01 01:26 | 831 | self-cleared | fix-forward | `55ba3911` (#907) | `1bcc6c4c` (#908) | 08-31 11:37 / 09-01 01:19 | e2e-tmux |
| 45 | console-beads-fabro | 2026-09-01 02:21 | 2026-09-01 10:56 | 514 | self-cleared | fix-forward | `b4e81104` (#910) | `acca58b8` (#911) | 09-01 09:43 / 09-01 09:51 | e2e-tmux |
| 46 | console-beads-fabro | 2026-09-02 05:45 | 2026-09-02 08:07 | 142 | fix-forward | fix-forward | `4f7392f5` (#926) | `246d6e1f` (#934) | 09-02 06:54 / 09-02 08:02 | e2e-tmux, plan-no-tombstone |
| 47 | console-beads-fabro | 2026-09-02 16:59 | 2026-09-02 18:18 | 79 | fix-forward | fix-forward | `8a5997b0` (#942) | `e93e7f29` (#946) | 09-02 18:06 / 09-02 18:13 | (ci-green only) |
| 48 | console-beads-fabro | 2026-09-09 21:20 | 2026-09-09 22:21 | 62 | fix-forward | fix-forward | `2c0f0cb0` (#1169) | `3a290dd2` (#1179) | 09-09 22:10 / 09-09 22:15 | clippy, coverage, nextest |
| 49 | dev-tooling | 2026-08-16 08:13 | 2026-08-16 09:15 | 62 | flake | re-run of same SHA | `85dca9fd` (#1450) | same SHA | — | red-green-replay |
| 50 | dev-tooling | 2026-08-17 01:26 | 2026-08-17 02:05 | 38 | fix-forward | fix-forward | `98167dd1` (#1467) | `5e4af91d` (#1470) | 08-17 01:51 / 08-17 01:55 | fleet-conformance |
| 51 | dev-tooling | 2026-08-17 21:40 | 2026-08-18 20:02 | 1342 | fix-forward | fix-forward | `e42e57fc` (#1504) | `395589ed` (#1511) | 08-18 19:53 / 08-18 19:58 | per-file-coverage |
| 52 | dev-tooling | 2026-08-18 20:15 | 2026-08-18 22:11 | 116 | flake | re-run of same SHA | `2cd02950` (#1513) | same SHA | — | fleet-conformance |
| 53 | dev-tooling | 2026-08-19 05:53 | 2026-08-19 06:25 | 32 | flake | re-run of same SHA | `968bac97` (#1552) | same SHA | — | per-file-coverage |
| 54 | dev-tooling | 2026-08-19 06:35 | 2026-08-19 07:04 | 29 | infra | fix-forward | `38d5fe5d` (#1553) | `06b97970` (#1554) | 08-19 06:57 / 08-19 07:00 | format |
| 55 | dev-tooling | 2026-08-25 15:39 | 2026-08-26 00:09 | 510 | infra | fix-forward | `b7c365f0` (#1632) | `c3044754` (#1633) | 08-25 23:58 / 08-26 00:02 | coverage-incremental, format, lint, metadata-batch, per-f... |
| 56 | dev-tooling | 2026-08-28 02:39 | 2026-08-29 03:42 | 1502 | infra | fix-forward | `793f9670` (#1652) | `e40ede3b` (#1653) | 08-29 03:33 / 08-29 03:38 | coverage |
| 57 | dev-tooling | 2026-09-02 08:13 | 2026-09-02 08:34 | 21 | infra | fix-forward | `061b4db7` (#1672) | `facd66ca` (#1671) | 09-02 06:39 / 09-02 08:10 | format, lint, per-file-coverage |
| 58 | dev-tooling | 2026-09-04 15:31 | 2026-09-04 15:39 | 9 | flake | re-run of same SHA | `e568c588` (#1711) | same SHA | — | coverage |
| 59 | dev-tooling | 2026-09-04 23:55 | 2026-09-05 01:05 | 70 | flake | re-run of same SHA | `ca59f514` (#1736) | same SHA | — | coverage-incremental, per-file-coverage, red-green-replay |
| 60 | dev-tooling | 2026-09-06 06:15 | 2026-09-06 06:23 | 8 | flake | re-run of same SHA | `654b9e0d` (#1741) | same SHA | — | fleet-conformance |
| 61 | dev-tooling | 2026-09-06 09:16 | 2026-09-06 09:18 | 2 | self-cleared | fix-forward | `85ee238f` (#1804) | `f31c99f0` (#1805) | 09-06 09:02 / 09-06 09:12 | fleet-conformance |
| 62 | dev-tooling | 2026-09-06 14:06 | 2026-09-06 14:22 | 15 | pin | fix-forward | `295b27f1` (#1853) | `c33a2a0f` (#1854) | 09-06 13:50 / 09-06 14:18 | fleet-conformance |
| 63 | dev-tooling | 2026-09-06 17:04 | 2026-09-06 17:21 | 17 | flake | re-run of same SHA | `d15fdcc3` (#1885) | same SHA | — | fleet-conformance |
| 64 | dev-tooling | 2026-09-06 17:58 | 2026-09-06 18:22 | 24 | self-cleared | fix-forward | `4fde8983` (#1896) | `1fe66ead` (#1895) | 09-06 17:44 / 09-06 17:53 | fleet-conformance |
| 65 | dev-tooling | 2026-09-09 11:43 | 2026-09-09 11:48 | 5 | infra | fix-forward | `2e2463a6` (#2142) | `6ba78f63` (#2143) | 09-09 11:40 / 09-09 11:44 | fleet-conformance |
| 66 | dev-tooling | 2026-10-12 10:54 | 2026-10-12 12:06 | 72 | flake | re-run of same SHA | `dda427af` (#2387) | same SHA | — | fleet-conformance |
| 67 | driver-claude | 2026-08-14 13:46 | 2026-08-14 21:43 | 477 | flake | re-run of same SHA | `c49c417a` (#478) | same SHA | — | comment-line-anchors, lint, skill-invocation-paths |
| 68 | driver-claude | 2026-08-15 14:00 | 2026-08-16 00:42 | 642 | pin | fix-forward | `b13854d4` (#485) | `8a4f4f1f` (#486) | 08-15 15:15 / 08-15 15:26 | no-inheritance, rop-pipeline-shape |
| 69 | driver-claude | 2026-08-16 01:17 | 2026-08-16 01:33 | 15 | infra | fix-forward | `f437b74f` (#487) | `2617fef7` (#488) | 08-16 00:55 / 08-16 01:12 | claude-md-coverage |
| 70 | driver-claude | 2026-08-16 08:30 | 2026-08-16 16:22 | 472 | flake | re-run of same SHA | `177941e5` (#492) | same SHA | — | no-inheritance, no-lloc-soft-warnings, supervisor-discipl... |
| 71 | driver-claude | 2026-08-18 20:19 | 2026-08-18 20:38 | 19 | flake | re-run of same SHA | `75c2e6c8` (#519) | same SHA | — | coverage-incremental |
| 72 | driver-claude | 2026-08-19 03:21 | 2026-08-19 06:10 | 169 | flake | re-run of same SHA | `e6d5b286` (#527) | same SHA | — | lint |
| 73 | driver-claude | 2026-08-19 06:21 | 2026-08-19 07:17 | 56 | flake | re-run of same SHA | `56fa0801` (#528) | same SHA | — | red-green-replay |
| 74 | driver-codex | 2026-08-14 05:20 | 2026-08-14 06:06 | 46 | infra | fix-forward | `116558a5` (#447) | `e3306247` (#448) | 08-14 04:42 / 08-14 05:09 | claude-md-coverage |
| 75 | driver-codex | 2026-08-14 09:21 | 2026-08-14 09:58 | 37 | flake | re-run of same SHA | `0a6f3c5e` (#451) | same SHA | — | shell-quality |
| 76 | driver-codex | 2026-08-16 03:01 | 2026-08-16 03:45 | 43 | flake | re-run of same SHA | `101d14ea` (#459) | same SHA | — | coverage-incremental, tests-mirror-pairing |
| 77 | driver-codex | 2026-08-16 08:11 | 2026-08-16 13:17 | 306 | infra | fix-forward | `2a5f51a4` (#460) | `18bf44f1` (#461) | 08-16 13:13 / 08-16 13:15 | no-inheritance |
| 78 | driver-codex | 2026-08-17 11:37 | 2026-08-17 21:47 | 609 | fix-forward | fix-forward | `6ebb346c` (#472) | `e58304cb` (#481) | 08-17 20:50 / 08-17 21:28 | coverage, hooks, per-file-coverage |
| 79 | driver-codex | 2026-08-28 02:46 | 2026-08-29 00:26 | 1300 | flake | re-run of same SHA | `bf3aeed1` (#530) | same SHA | — | lint |
| 80 | driver-codex | 2026-09-01 15:10 | 2026-09-02 10:26 | 1156 | infra | fix-forward | `f4a8a05c` (#539) | `04a9c5c7` (#542) | 09-02 08:28 / 09-02 09:21 | codex-skill-picker, dev-tooling, e2e-cli, red-green-repla... |
| 81 | driver-codex | 2026-09-02 15:53 | 2026-09-02 18:10 | 136 | infra | fix-forward | `117fa0ce` (#544) | `423d123e` (#545) | 09-02 16:50 / 09-02 17:33 | codex-skill-picker, dev-tooling |
| 82 | driver-pi | 2026-08-15 14:38 | 2026-08-15 15:00 | 22 | self-cleared | fix-forward | `d2c6c1ec` | `d3ce3fdf` | — | coverage, per-file-coverage |
| 83 | driver-pi | 2026-09-01 15:10 | 2026-09-02 05:15 | 844 | flake | re-run of same SHA | `2922e96d` (#87) | same SHA | — | extension-quality |
| 84 | driver-pi | 2026-09-02 15:43 | 2026-09-02 17:58 | 136 | infra | fix-forward | `837530de` (#93) | `2173c13f` (#94) | 09-02 16:50 / 09-02 17:33 | coverage-incremental, coverage, doctor-static, extension-... |
| 85 | orch-beads-fabro | 2026-08-17 01:41 | 2026-08-17 02:52 | 71 | fix-forward | fix-forward | `2798769d` (#1474) | `99b64f09` (#1483) | 08-17 02:42 / 08-17 02:48 | coverage (nonroot), coverage (root), per-file-coverage (n... |
| 86 | orch-beads-fabro | 2026-08-17 19:29 | 2026-08-17 21:52 | 143 | fix-forward | fix-forward | `8c696074` (#1522) | `4ba77405` (#1526) | 08-17 21:48 / 08-17 21:49 | coverage (nonroot), coverage (root), per-file-coverage (n... |
| 87 | orch-beads-fabro | 2026-08-20 01:19 | 2026-08-20 02:11 | 52 | revert | revert | `462611c0` (#1587) | `113e9a01` (#1589) | 08-20 02:07 / 08-20 02:08 | per-file-coverage (nonroot), per-file-coverage (root) |
| 88 | orch-beads-fabro | 2026-08-26 04:55 | 2026-08-26 04:57 | 2 | infra | fix-forward | `45d9ba58` (#1885) | `6355423f` (#1886) | 08-26 04:53 / 08-26 04:54 | red-green-replay |
| 89 | orch-beads-fabro | 2026-08-28 08:10 | 2026-08-28 08:30 | 20 | revert | revert | `75e76fab` (#1934) | `13ad49e6` (#1935) | 08-28 08:25 / 08-28 08:26 | per-file-coverage (nonroot), per-file-coverage (root) |
| 90 | orch-beads-fabro | 2026-08-30 02:11 | 2026-08-30 02:18 | 7 | self-cleared | fix-forward | `0b76397c` (#2004) | `65f34d62` (#2005) | 08-30 02:12 / 08-30 02:14 | per-file-coverage (nonroot) |
| 91 | orch-beads-fabro | 2026-09-04 16:41 | 2026-09-04 18:08 | 86 | fix-forward | fix-forward | `482a16c4` (#2139) | `bef83890` (#2143) | 09-04 17:49 / 09-04 17:55 | python-batch (root) |
| 92 | orch-beads-fabro | 2026-09-06 06:07 | 2026-09-06 06:14 | 7 | infra | fix-forward | `b9a40044` (#2175) | `4b2f2e67` (#2176) | 09-06 05:59 / 09-06 06:05 | per-file-coverage (nonroot), per-file-coverage (root), py... |
| 93 | orch-beads-fabro | 2026-09-09 16:27 | 2026-09-09 16:42 | 15 | self-cleared | fix-forward | `ae339643` (#2410) | `af366d59` (#2412) | 09-09 15:57 / 09-09 16:18 | per-file-coverage (root) |
| 94 | orch-beads-fabro | 2026-09-10 21:09 | 2026-09-10 21:28 | 18 | flake | re-run of same SHA | `a52e8f86` (#2456) | same SHA | — | per-file-coverage (root) |
| 95 | orch-beads-fabro | 2026-10-01 02:33 | 2026-10-01 03:03 | 30 | flake | re-run of same SHA | `6a7dd5e0` (#2522) | same SHA | — | per-file-coverage (root) |
| 96 | orch-beads-fabro | 2026-10-10 03:20 | 2026-10-10 03:57 | 36 | revert | revert | `4f0a8d32` (#2742) | `5ddbb49d` (#2743) | 10-10 03:43 / 10-10 03:50 | metadata-batch |
| 97 | orch-beads-fabro | 2026-10-11 23:02 | 2026-10-11 23:30 | 28 | revert | revert | `ac5684ce` (#2794) | `de32fe9e` (#2797) | 10-11 23:19 / 10-11 23:25 | metadata-batch |
| 98 | orch-beads-fabro | 2026-10-13 04:07 | 2026-10-13 04:16 | 9 | self-cleared | fix-forward | `6787b73e` (#2867) | `5891ddb5` (#2868) | 10-13 04:00 / 10-13 04:10 | per-file-coverage (root) |
| 99 | orch-beads-fabro | 2026-10-14 01:17 | 2026-10-14 01:50 | 33 | revert | revert | `35fea321` (#2917) | `c9db470d` (#2918) | 10-14 01:36 / 10-14 01:44 | metadata-batch |
| 100 | orch-git-jsonl | 2026-08-14 06:21 | 2026-08-16 00:42 | 2541 | infra | fix-forward | `dee75ec6` (#617) | `bbb1e314` (#627) | 08-15 15:15 / 08-15 15:26 | all-declared, coverage-incremental, keyword-only-args, no... |
| 101 | orch-git-jsonl | 2026-08-16 08:30 | 2026-08-16 08:45 | 15 | pin | fix-forward | `5dec7733` (#631) | `5ed0bc5e` (#632) | 08-16 07:39 / 08-16 08:42 | canonical-recipe-fidelity, no-raise-outside-io, source-tr... |
| 102 | orch-git-jsonl | 2026-09-01 14:40 | 2026-09-02 10:31 | 1190 | infra | fix-forward | `20badffc` (#712) | `bfe73dbb` (#715) | 09-02 08:28 / 09-02 09:21 | acceptance, coverage-incremental, doctor-static, format, ... |
| 103 | orch-git-jsonl | 2026-09-02 15:37 | 2026-09-03 13:15 | 1298 | infra | fix-forward | `5c9d2b15` (#717) | `0571037d` (#719) | 09-03 13:12 / 09-03 13:14 | acceptance, coverage-incremental, doctor-static, format, ... |
| 104 | overseer | 2026-08-14 07:03 | 2026-08-14 07:47 | 44 | self-cleared | fix-forward | `8ab7c063` (#901) | `2b50545b` (#907) | 08-14 06:14 / 08-14 07:17 | fleet-marketplace-relative-sources, no-lloc-soft-warnings... |
| 105 | overseer | 2026-08-14 07:51 | 2026-08-14 07:54 | 3 | infra | fix-forward | `433c5548` (#908) | `7f8b4166` (#906) | 08-14 06:00 / 08-14 07:47 | prose-release-hygiene |
| 106 | overseer | 2026-08-14 08:31 | 2026-08-14 09:27 | 56 | flake | re-run of same SHA | `36260bb2` (#909) | same SHA | — | rop-pipeline-shape |
| 107 | overseer | 2026-08-14 22:48 | 2026-08-14 22:59 | 11 | infra | fix-forward | `7ff2c433` (#922) | `8e8142f1` (#923) | 08-14 21:57 / 08-14 22:31 | agents-ai-references-resolve, coverage-incremental, tools... |
| 108 | overseer | 2026-08-14 23:09 | 2026-08-14 23:13 | 4 | infra | fix-forward | `19b0c4b2` (#924) | `8753f57d` (#927) | 08-14 23:09 / 08-14 23:11 | local-memory-drift-audit, no-direct-tool-invocation |
| 109 | overseer | 2026-08-15 05:58 | 2026-08-15 06:05 | 7 | infra | fix-forward | `ae562fce` (#931) | `9e9efb49` (#930) | 08-15 05:43 / 08-15 06:03 | heading-coverage, no-direct-tool-invocation |
| 110 | overseer | 2026-08-15 06:13 | 2026-08-15 06:28 | 15 | flake | re-run of same SHA | `38c843bb` (#932) | same SHA | — | coverage, per-file-coverage |
| 111 | overseer | 2026-08-15 06:35 | 2026-08-15 06:40 | 4 | flake | re-run of same SHA | `251f2959` (#933) | same SHA | — | primary-checkout-commit-refuse-hook-installed |
| 112 | overseer | 2026-08-15 07:21 | 2026-08-15 07:33 | 12 | flake | re-run of same SHA | `3c336a5c` (#937) | same SHA | — | newtype-domain-primitives, pbt-coverage-pure-modules |
| 113 | overseer | 2026-08-15 07:36 | 2026-08-15 07:44 | 8 | fix-forward | fix-forward | `d6317efc` (#939) | `5c26656f` (#940) | 08-15 07:40 / 08-15 07:42 | coverage, fleet-marketplace-relative-sources, match-keywo... |
| 114 | overseer | 2026-08-15 08:33 | 2026-08-15 08:35 | 2 | infra | fix-forward | `c771a162` (#949) | `787a8f2f` (#950) | 08-15 08:29 / 08-15 08:33 | prose-release-hygiene |
| 115 | overseer | 2026-08-15 09:54 | 2026-08-15 10:28 | 33 | self-cleared | fix-forward | `bf5d16da` (#953) | `97d7b26c` (#954) | 08-15 09:35 / 08-15 09:40 | claude-md-coverage, fleet-marketplace-relative-sources, h... |
| 116 | overseer | 2026-08-15 10:28 | 2026-08-15 10:42 | 14 | infra | fix-forward | `5753c41b` (#956) | `244d7fd3` (#957) | 08-15 09:52 / 08-15 10:24 | doctor-static, keyword-only-args, local-memory-drift-audi... |
| 117 | overseer | 2026-08-15 11:17 | 2026-08-15 11:26 | 9 | infra | fix-forward | `e0fe3cf1` (#958) | `6d8acb6f` (#959) | 08-15 11:21 / 08-15 11:23 | main-guard, no-shadow-ledger-body-typechecks, no-write-di... |
| 118 | overseer | 2026-08-15 15:42 | 2026-08-16 00:01 | 499 | flake | re-run of same SHA | `89566560` (#964) | same SHA | — | private-calls, public-api-result-typed, source-trees-scop... |
| 119 | overseer | 2026-08-16 01:33 | 2026-08-16 01:36 | 4 | flake | re-run of same SHA | `0cdbd904` (#968) | same SHA | — | per-file-coverage |
| 120 | overseer | 2026-08-16 02:46 | 2026-08-16 04:02 | 76 | self-cleared | fix-forward | `f9ec6a5d` (#972) | `7fb595c6` (#974) | 08-16 03:54 / 08-16 03:59 | coverage, per-file-coverage |
| 121 | overseer | 2026-08-16 05:55 | 2026-08-16 06:04 | 9 | flake | re-run of same SHA | `5fb66573` (#978) | same SHA | — | ci-matrix-completeness |
| 122 | overseer | 2026-08-16 08:21 | 2026-08-16 08:49 | 28 | pin | fix-forward | `e3c77b89` (#982) | `e5ba594b` (#983) | 08-16 07:41 / 08-16 08:46 | agents-ai-references-resolve, tools, ci-matrix-completene... |
| 123 | overseer | 2026-08-16 22:19 | 2026-08-16 22:19 | 0 | infra | fix-forward | `56247342` (#1007) | `16d5bba9` (#1008) | 08-16 21:53 / 08-16 22:15 | plugin-resolution |
| 124 | overseer | 2026-08-17 10:11 | 2026-08-17 13:15 | 184 | self-cleared | fix-forward | `2fa83a45` (#1059) | `f294e113` (#1062) | 08-17 11:50 / 08-17 12:16 | coverage, per-file-coverage |
| 125 | overseer | 2026-08-19 06:10 | 2026-08-19 06:18 | 8 | infra | fix-forward | `453b2d35` (#1172) | `e7903fc1` (#1173) | 08-19 06:11 / 08-19 06:13 | metadata-batch |
| 126 | overseer | 2026-08-19 06:33 | 2026-08-19 06:34 | 1 | infra | fix-forward | `c41d7b81` (#1178) | `26f55b1a` (#1180) | 08-19 06:29 / 08-19 06:31 | per-file-coverage |
| 127 | overseer | 2026-08-19 11:54 | 2026-08-19 12:11 | 17 | self-cleared | fix-forward | `7df315fe` (#1219) | `d64e5091` (#1222) | 08-19 11:52 / 08-19 12:03 | per-file-coverage |
| 128 | overseer | 2026-08-21 15:02 | 2026-08-21 16:04 | 62 | revert | revert | `590ac9d3` (#1443) | `d3a58011` (#1446) | 08-21 15:58 / 08-21 16:01 | per-file-coverage, types |
| 129 | overseer | 2026-08-21 19:19 | 2026-08-21 19:23 | 5 | self-cleared | fix-forward | `1157971e` (#1468) | `d9f82c92` (#1469) | 08-21 19:17 / 08-21 19:20 | per-file-coverage |
| 130 | overseer | 2026-08-22 10:18 | 2026-08-22 10:21 | 2 | self-cleared | fix-forward | `56e680cb` (#1617) | `b4409604` (#1618) | 08-22 10:12 / 08-22 10:16 | per-file-coverage |
| 131 | overseer | 2026-08-22 10:24 | 2026-08-22 10:26 | 2 | self-cleared | fix-forward | `2b0f5285` (#1622) | `54ca8f4b` (#1621) | 08-22 10:14 / 08-22 10:20 | per-file-coverage |
| 132 | overseer | 2026-08-22 10:29 | 2026-08-22 10:31 | 3 | self-cleared | fix-forward | `f9e269d3` (#1625) | `5e2ba05f` (#1624) | 08-22 10:20 / 08-22 10:26 | per-file-coverage |
| 133 | overseer | 2026-08-22 10:33 | 2026-08-22 12:35 | 122 | revert | revert | `f5e1d45c` (#1626) | `924d3220` (#1630) | 08-22 11:17 / 08-22 12:31 | lint |
| 134 | overseer | 2026-08-22 12:36 | 2026-08-22 12:39 | 3 | self-cleared | fix-forward | `ef5e06cc` (#1635) | `33cdb2c1` (#1596) | 08-22 09:02 / 08-22 12:36 | per-file-coverage |
| 135 | overseer | 2026-08-22 12:41 | 2026-08-22 12:44 | 3 | self-cleared | fix-forward | `9c518f9f` (#1636) | `e8d94544` (#1637) | 08-22 12:36 / 08-22 12:40 | per-file-coverage |
| 136 | overseer | 2026-08-22 12:46 | 2026-08-22 13:24 | 39 | self-cleared | fix-forward | `8c341e02` (#1638) | `d1dd6549` (#1632) | 08-22 11:51 / 08-22 13:18 | per-file-coverage |
| 137 | overseer | 2026-08-22 14:18 | 2026-08-22 14:20 | 1 | self-cleared | fix-forward | `477c7bf1` (#1653) | `bbcdbef4` (#1652) | 08-22 14:11 / 08-22 14:16 | per-file-coverage |
| 138 | overseer | 2026-08-22 19:19 | 2026-08-22 19:21 | 2 | self-cleared | fix-forward | `7afe3731` (#1717) | `87054870` (#1718) | 08-22 19:14 / 08-22 19:17 | per-file-coverage |
| 139 | overseer | 2026-08-23 15:14 | 2026-08-23 15:17 | 2 | infra | fix-forward | `d44f8e1d` (#1905) | `c6bdce38` (#1906) | 08-23 15:09 / 08-23 15:13 | red-green-replay |
| 140 | overseer | 2026-08-26 02:34 | 2026-08-26 02:53 | 19 | self-cleared | fix-forward | `a2843678` (#1958) | `c428846a` (#1959) | 08-26 02:35 / 08-26 02:42 | per-file-coverage |
| 141 | overseer | 2026-08-26 03:39 | 2026-08-26 03:54 | 15 | pin | fix-forward | `1107314f` (#1960) | `6e199d81` (#1961) | 08-26 03:37 / 08-26 03:46 | per-file-coverage |
| 142 | overseer | 2026-08-26 06:43 | 2026-08-26 07:00 | 17 | self-cleared | fix-forward | `7e51f270` (#1964) | `da0ba17d` (#1965) | 08-26 06:37 / 08-26 06:49 | per-file-coverage |
| 143 | overseer | 2026-08-27 01:14 | 2026-08-27 01:23 | 9 | self-cleared | fix-forward | `d0ef8c4c` (#1983) | `3dd11927` (#1984) | 08-27 01:11 / 08-27 01:14 | per-file-coverage |
| 144 | overseer | 2026-08-27 08:36 | 2026-08-27 08:40 | 4 | self-cleared | fix-forward | `fac92492` (#2010) | `eb36c17a` (#2011) | 08-27 08:32 / 08-27 08:36 | per-file-coverage |
| 145 | overseer | 2026-08-30 07:31 | 2026-08-30 08:25 | 55 | self-cleared | fix-forward | `6b2589ab` (#2057) | `e905f46a` (#2058) | 08-30 06:56 / 08-30 07:07 | per-file-coverage |
| 146 | overseer | 2026-09-01 14:51 | 2026-09-02 11:03 | 1212 | infra | fix-forward | `097f4708` (#2110) | `119973c9` (#2114) | 09-02 09:30 / 09-02 10:31 | coverage-incremental, doctor-static, format, lint, metada... |
| 147 | overseer | 2026-09-03 13:13 | 2026-09-04 08:39 | 1166 | pin | fix-forward | `2f7e3b34` (#2121) | `5e2e0c68` (#2122) | 09-04 08:28 / 09-04 08:32 | per-file-coverage |
| 148 | runtime | 2026-08-14 06:21 | 2026-08-15 06:58 | 1477 | infra | fix-forward | `a9af5a77` (#525) | `bc775f89` (#529) | 08-15 06:40 / 08-15 06:54 | aggregate-completeness, keyword-only-args, lint |
| 149 | runtime | 2026-08-15 10:44 | 2026-08-15 10:50 | 6 | flake | re-run of same SHA | `bfc588ca` (#531) | same SHA | — | fleet-marketplace-relative-sources, lint, required-role-k... |
| 150 | runtime | 2026-08-15 15:42 | 2026-08-16 02:08 | 626 | infra | fix-forward | `f596c819` (#537) | `34ad3a94` (#540) | 08-16 01:44 / 08-16 01:56 | keyword-only-args, lint, per-file-coverage, tests-no-subp... |
| 151 | runtime | 2026-08-16 08:21 | 2026-08-16 21:50 | 810 | pin | fix-forward | `b12d5eb7` (#541) | `14357003` (#544) | 08-16 21:34 / 08-16 21:40 | aggregate-completeness, canonical-recipe-fidelity, tools,... |
| 152 | runtime | 2026-08-17 15:24 | 2026-08-17 19:29 | 245 | infra | fix-forward | `3350fdc8` (#564) | `ecbfa628` (#566) | 08-17 14:21 / 08-17 19:22 | coverage, per-file-coverage, red-green-replay |
| 153 | runtime | 2026-08-25 15:38 | 2026-08-25 15:58 | 20 | infra | fix-forward | `f12f8d18` (#615) | `6b9f73d0` (#616) | 08-25 15:52 / 08-25 15:54 | types |
| 154 | runtime | 2026-09-04 15:31 | 2026-09-04 15:35 | 4 | flake | re-run of same SHA | `dcf9c034` (#644) | same SHA | — | (ci-green only) |

## Reproduction

Scripts and raw data were kept in the measuring session's scratchpad and are not committed. To reproduce, run the same
`gh api` reads described in §Method: list workflow runs per repo, read run attempts and attempt-1 jobs, read
`commits/{sha}/pulls`, and read PR files. Then apply the class rules in order.
