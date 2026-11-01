## The maintainer's statement of what done means

"any routine test or gate-related load that runs on a VPS needs to be addressed." (maintainer, 2026-11-01 ~15:2xZ, relayed verbatim by the coordinator) — and, in the implement-test-performance tab: "Okay, all of the VPS load stuff. I want you to split it into a separate plan with a clean boundary, like you agreed. Go ahead and draft that plan. Give me the information you have, including the definition of done."

## Definition of Done assertions derived from that statement

- This plan's research records, from a measured window of at least four hours on the dev host, the CPU share of each routine test and gate load class there (commit-time pre-commit aggregate, commit-hook replay runs, pre-push, janitor post-merge checks, ad-hoc seat suites, coverage trees, and any other class found), with the measurement method and its known blind spots.
- A hand commit's pre-commit check aggregate runs its test and coverage targets as a Kubernetes gates Job keyed to the staged tree rather than on the committing dev host, and the commit's verdict is the Job's verdict.
- A janitor post-merge check runs its full check, pytest and coverage as a cluster Job rather than on the dev host, and its failed output stays readable from the dev host.
- A seat's ad-hoc just check, pytest or diagnostic full-suite run started through the sanctioned gate runner runs as a cluster Job by default, and a run on the dev host happens only on an explicit local choice that the run records.
- Pre-push in every fleet repository with a delegated gate runs as a gates Job, and this plan's research names, per repository, each member that still runs on the dev host and why.
- Over a measured window of at least four hours of normal fleet activity after the carriers ship, the routine test and gate load classes together average under one CPU core on the dev host, measured by the same method as the baseline.

## Origin and boundary

Split out of plan implement-test-performance (epic livespec-dev-tooling-sv6m5p) on 2026-11-01 by the maintainer's order. At ~15:2xZ the coordinator (gitops-fleet-capacity-monitoring, epic livespec-dev-tooling-dfixhe) relayed the maintainer's direction that routine test and gate load on the VPS dev host be addressed, and handed four load classes to sv6m5p. The sv6m5p seat recommended a separate plan with a clean boundary; the maintainer agreed and ordered this plan.

The boundary:

- **Stays in implement-test-performance (sv6m5p):** the commit hook's own Red, Green and suite-green replay test runs (red_green_replay). These are carried by livespec-dev-tooling-sewnfp (dev-tooling spec v105 "## Delegated commit-time replay test runs"), and that plan also covers the factory implement graph, the Red/Green node split and suite speed.
- **Owned here:** every OTHER routine test or gate run on the dev host:
  1. the commit-time pre-commit check aggregate on a hand commit, which v105 deliberately leaves local;
  2. janitor post-merge checks (full check, pytest and coverage in `janitor-*` worktrees);
  3. seats' ad-hoc `just check`, pytest and diagnostic full suites, including those started through `just gate-start`;
  4. coverage test trees, and anything else the measurement finds;
  5. pre-push, which is already delegated: verify it fleet-wide and record which members stay on the dev host.
- **Shared measurement:** this plan's aggregate dev-host test/gate CPU figure includes the commit-hook class, but this plan does not carry that class. It is an external carrier (sewnfp) that this plan reads.

## Coordinator inventory (2026-11-01, relayed, not yet verified here)

1. Pre-push is already delegated. `delegated_gate = true` in dev-tooling, orchestrator, livespec, overseer, console and runtime, and `ubuntu` is in gates-client. Every dev-tooling push since 10-31 ran as a gates Job (~3 min each, "delegated gate passed" in tmp/gate-runs). Only world-reading members (e.g. check-branch-protection-alignment) run on the VPS. To verify for the orchestrator and the other repos.
2. Commit-hook Red/Green/suite-green: sewnfp (sv6m5p), running as factory run 01M6BSXV35NP at 15:00Z.
3. Pre-commit aggregate: not delegated (v105), so every hand commit runs it on the VPS.
4. Janitor post-merge checks: on the VPS.
5. Ad-hoc seat full suites through gate-start: on the VPS (e.g. 25-minute diagnostic suites on 2026-11-01).
6. Coverage test trees (covns-full-tree) and others.

## First measurement (2026-11-01, dev host vmi3006760, 18 CPUs)

Method: a scratch sampler reads every process's utime+stime every N seconds. It charges each process's delta, plus reaped-child CPU net of what those children were already charged while alive, to a class. The class is the first match walking up the process's ancestor chain: a janitor cwd; covns; red_green_replay; `lefthook`/`git push` → pre-push; `lefthook`/`git commit` → pre-commit aggregate; `gate-run.sh __child` → ad-hoc gate-start. A pytest / `just` ancestor → ad-hoc pytest-or-check. Otherwise k3s/docker, dolt, herdr, or agents-and-other. `mpstat` runs in parallel for host totals.

Blind spots: the sampler over-counts by up to ~25% relative to mpstat (residual child double count); a process born and dead within one interval under an unsampled parent is lost; class rules are substring heuristics.

Spot readings (two 5 s intervals, ~15:25Z): the host was 82-90% busy by mpstat, with **57% of CPU in system time**. Attributed: agents-and-other 15.7-20.4 cores, pre-commit aggregate 0.6-0.7 cores (one overseer seat's hand commit, worktree `chore/reown-caam-rendering-lloc`), ad-hoc pytest-or-check 0.4-0.6, herdr 0.8, dolt 0.1-0.4, k3s/docker ~0. Within agents-and-other, petri's `dispatch-dual-r681b.sh` dispatch shells took ~2.9 cores together, and Claude seats took 0.3-1.5 cores each.

Reading: at this instant the test/gate classes were a small share (~1-1.5 cores). The dominant load was agent sessions and factory dispatch supervision, plus very high system time. One short window does not establish the routine share: test/gate load is bursty (a janitor or a 25-minute suite occupies several cores for tens of minutes). A 30-minute window started at ~15:27Z (`samples.jsonl` + `mpstat2.txt` in the sv6m5p seat's scratchpad) is the first real baseline. Its result is to be recorded in research note 002 by this plan's seat, which should then take a longer window (≥4 h) before setting assertion 6's threshold against it.

Leads not owned here, recorded so they are not lost: the 57% system time and the dispatch-shell CPU are NOT test/gate load. They belong to the coordinator's capacity work, not this plan, unless the measurement attributes them to a test/gate class.

## Related state

- Four merged dev-tooling items (u5ppsu, tt4w7h, overseer mqieqw, tsaiew) have post-merge janitors red on the coverage family (check-per-file-coverage). That root cause is owned by sv6m5p (u5ppsu and tt4w7h are its carriers), but this plan's janitor carrier must not move the janitor to a Job in a way that hides it.
- Spec: dev-tooling v105 contracts.md "## Delegated commit-time replay test runs" is the precedent shape (gates Job keyed to the staged tree) for delegating the pre-commit aggregate and the janitor.

## Next actions for the seat

1. Record the 30-minute baseline (note 002), then a ≥4 h window.
2. Verify pre-push delegation per fleet repo (assertion 5).
3. propose-change / revise in livespec-dev-tooling for delegating the pre-commit aggregate, the janitor and the ad-hoc runner, then file the carriers and record the carrier map. Sequence them behind sewnfp.
