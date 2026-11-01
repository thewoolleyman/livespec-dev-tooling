## The maintainer's statement of what done means

Okay I'm revisiting the test performance problems. First of all the automatic commit didn't used to be a problem as far as I know. The red-green commit was working fine so I want you to do research to see if there's a regression about the automated commit or something. And second of all, running only the test which changed is a risk because you don't know when you might have broken something unrelated. Ideally we can make the test run faster. I thought we delegated these to Kubernetes. But in the first step yes, we can only run the tests which were changed and then run the whole suite before the commit. Look into all these problems and then kick off a plan and open it in a tab so I can follow up. This seems like the highest priority.

## Definition of Done assertions derived from that statement

- This plan's research names, with dated evidence from factory implement runs before and after 2026-10-19, the change or changes that made implement turns end with partial progress or with a Red test committed apart from its implementation, and states whether the automated commit regressed.
- In a factory implement run, the Red and Green commit legs execute only the changed test files, and the whole test suite runs once against the final tree and passes before the run's commit is final.
- No commit produced by a factory implement run or by the commit hooks on a host lands without a passing whole-suite run over its final tree.
- The whole-suite run with coverage, including the per-file coverage gate, of livespec-orchestrator-beads-fabro and livespec-dev-tooling completes faster than the baseline recorded in this plan's research, measured on the same host class.
- This plan's research states, for each commit-time and push-time gate, whether it runs as a Kubernetes Job or on the committing host, and commit-time whole-suite runs from the dev host either run as Kubernetes Jobs or the reason they do not is recorded.
- Over at least 20 consecutive factory implement dispatches after the fixes ship, no run ends LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS or REENTRY_BUDGET_EXHAUSTED because its turn was spent waiting on a test gate.

# Charter and measured baseline — implement-test-performance

## Why

Factory implement runs across three tenants began ending `needs-human` with LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS or
REENTRY_BUDGET_EXHAUSTED after 2026-10-19, and commit-time test gates now dominate both factory turns and the dev host.
The maintainer asked (2026-11-01, statement above) for three things in order: (1) find out whether the automated
commit regressed, since Red/Green used to work; (2) stop paying full-suite cost on every Red/Green leg WITHOUT
giving up a full-suite run before the commit is final; (3) make the suite itself faster, and explain what is and is
not delegated to Kubernetes. The maintainer called this the highest priority.

Commissioned by the fleet coordinator (session gitops-fleet-capacity-monitoring, epic livespec-dev-tooling-dfixhe).
The Definition of Done assertions were derived by this session from the statement and created without a
confirmation round, on the maintainer's instruction relayed by the coordinator to kick the plan off at once; they are
recorded as session-derived in the first handoff, for the maintainer to amend in this tab.

## Fix shape already ruled by the maintainer

- Red/Green legs run only the changed tests; the WHOLE suite runs once before the commit is final.
- Running only changed tests without a full run is NOT acceptable.
- Make the suite itself faster where possible.

## Measured facts at creation (2026-11-01)

From the coordinator (epic livespec-dev-tooling-dfixhe, comments ROOT-CAUSE FINDING 1/2 and CORRECTION):

- 45 needs-human endings since 2026-10-24 name LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS / REENTRY_BUDGET_EXHAUSTED
  (orchestrator 33/146, overseer 9/26, dev-tooling 3/19). Zero before 2026-10-19 in all three tenants.
- Three runs analysed from `fabro dump` (overseer-e6bvmt 01M69Z9YFYV9, overseer-uzvcbn.9 01M69FCAP6B8,
  bd-ib-37wvsk 01M6A0NNJ1CG; Codex implementer). Share of each implement turn spent in gate-wait / poll calls:
  e6bvmt 61.6 min 85%, 33.8 min 81%; uzvcbn.9 32.5 min 78%, 29.0 min 85%; 37wvsk 47.1 min 92%, 23.7 min 78%.

From seat sandbox-commit-gate-ceiling (plan epic bd-ib-qy5wol):

- In-sandbox hook wall time: a Red commit with only the staged test takes 45 s to 3 min; a Green amend with the
  full aggregate takes 5 to 17 min.
- In 5 of 6 turns the turn ended 20-30 s after its own commit run had already FAILED. Settle reads only RUNNING
  records, and implement_hook_route re-runs pre-commit over what is STAGED; the engine checkpoint commit
  (`--no-verify`) has already committed the staged tree, so the re-entry sees no refused commit and gets no failed
  targets. The same checkpoint splits the Red test from its implementation. Fixes D (bd-ib-jzuryr) and B (fold
  trailing checkpoint commits back into the index before `start`) are OWNED by that seat; this plan does not
  duplicate them and maps them as external carriers once they land.
- Host side at load 60-100: livespec-orchestrator-beads-fabro full suite 12749 tests, 2084 s with -n 4, 3392 s inside
  a commit gate; one full pre-commit gate 5064 s; a suite-green commit-msg leg 31 min. livespec-dev-tooling suite
  5686 tests, 2177 s.
- Wall-clock-bound tests flake under that load (three orchestrator cases, one dev-tooling rehearsal); being fixed
  as ordering assertions by that seat.

From seat kubernetes-sandbox-backend (run 01M6A9H4K4PGT6VR0PBWPS697J, overseer-yizu3e, 4 CPU Guaranteed pod):

- About nine ~3-minute suite bursts in ~50 minutes of one implement turn, 2.1-2.5 cores average each, under 10%
  throttled per burst. Pod CPU quota is NOT the limiter. The suspects are the run COUNT per turn and the part-serial
  tail of each run (collection, coverage combine, per-file coverage): `-n 4` averages only ~2.4 cores.

From seat factory-context-per-turn-reduction (orchestrator branch implement-brief-hook-is-the-full-check):

- In three 2026-10-31 implement runs, 70.6 of 227.6 implement minutes (31%) were self-started suite / coverage runs
  and 116.6 min (51%) were hook waits. That seat's brief change ("the commit hook is the full check — run only
  targeted tests yourself") removes the self-started runs; this plan approved it (2026-11-01) as a carrier for the
  "changed tests during Red/Green" half of assertion 2. Hook-wait time stays in this plan's scope.

## Regression leads to test (assertion 1)

Workflow history in livespec-orchestrator-beads-fabro, `.claude-plugin/.fabro/workflows/implement-work-item/`:

- 6a55ff0e9 2026-10-20 "fail the implement stage on a partial-progress turn" (previously published and continued).
- 5abc90469 / 5cab31e42 2026-10-25 implement re-entry after an incomplete turn (implement_hook_route, budget 1).
- 2b2c55a9d 2026-10-28 commit runner settle; 2c9f905e1 / 02ee84386 2026-10-29 detached sandbox commits.
- Engine checkpoint commits are old (bd-ib-6ka, 2026-07-05). Hypothesis: the 10-20 / 10-25 / 10-28 changes made the
  checkpoint's interaction with a mid-ritual turn boundary visible as a failure. To prove or refute against runs from
  before 2026-10-19.
- Also: did the red_green_replay hook get slower (the suite-green leg runs the full suite on every passing commit),
  and was the per-file coverage gate added or widened recently?

## Overlapping live plans in this repository (to fold, not duplicate)

- rgr-touched-test-scope (epic livespec-dev-tooling-5yyjqk, 2026-10-24): a single-test-file commit's suite-green leg
  runs only that test. Carrier livespec-dev-tooling-h3gcs6 is BLOCKED after a deterministic stage-failure
  (ModuleNotFoundError livespec_orchestrator_beads_fabro, run 01M683DMER1FMKKP2T70FM9CKN).
- delegated-commit-time-gates (epic livespec-dev-tooling-2fekp6, 2026-10-24): commit-time Red/Green/suite-green legs
  run as a gates Job with local fallback. Carrier livespec-dev-tooling-sewnfp is pending-approval, gated on livespec
  PR #2941's revise.
- rgr-cycle-agent-efficiency (anchor `unassigned`, 2026-09-06): an older standalone proposal on the same theme.

Both 2026-10-24 plans predate the maintainer's 2026-11-01 ruling and neither alone meets it: the touched-test plan
narrows the leg without the "whole suite once before final" half, and the delegation plan moves cost without
reducing run count. Their disposition (absorb as carriers here, or keep as sibling plans mapped as external
carriers) is decided in this plan's scoping event.

## What is and is not delegated to Kubernetes today (assertion 4, first statement)

- Delegated: the PRE-PUSH aggregate, run as a Job in the gates namespace for opted-in repositories (spec
  §"Delegated pre-push gate"; plan delegated-gate-fleet-rollout, archived).
- Not delegated: every commit-time gate — the pre-commit aggregate and red_green_replay's Red, Green and suite-green
  legs — runs where the commit happens: inside the factory pod for factory runs, on the dev host for hand commits.
- Factory implement runs execute in Kubernetes pods (the sandbox backend), so their commit-time cost is already on
  the cluster; what is not "delegated" there is the per-commit duplication, not the location.
To be confirmed against the code before the scoping event.
