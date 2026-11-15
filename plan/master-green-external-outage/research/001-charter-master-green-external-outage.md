## The maintainer's statement of what done means

Maintainer, verbatim, in the legacy-coordinator-agent seat, 2026-11-15 ~23:1x-23:5xZ, as recorded in the plan-scope-event marked SUPERSEDES on livespec-dev-tooling-6tgd2z (2026-11-15T23:22:17Z):

(a) "I want to discuss how we can incorporate this into the master green check itself. I don't know if it's possible because I don't think it currently involves LLMs and that might break some of the rules about the pre-check gates where we don't want LLMs involved. But we want some easy way to incorporate this concept into future situations that are the same, where master is read for something external, and we don't want to stop everything completely"

(b) (from another seat, pasted) "The whole point is to not let failures stack up" / "But this failure is external. It's not due to anything we can fix" / "So even though what you're pushing through doesn't directly fix it, the same logic still applies until the external error is completely resolved"

(c) "On the question for me, number one, it should be designed flexibly so it can handle any sort of external outage that meets this category of failure. Whether it's any GitHub failure or something else, it could be that the internet is down. It could be anything else: a third-party tool is down or something that we rely on is down but we can still do commits and push things through. That's the category of error that we care about: things that are not our own problem to fix or cannot be fixed immediately for some reason external to us . And on the second one I don't necessarily know that there should be a time limit. External errors could last a long time. Make the time limit like a day. Hopefully all external errors can be resolved within a day"

Definition of Done as legacy-coordinator-agent relayed the maintainer's order to this seat (~23:5xZ): (1) spec ratified in livespec-dev-tooling and livespec core: the external category, machine-produced external-cause evidence, fail closed on anything not recorded as external, tolerance for every commit and push until master ci.yml push reads green, a 24 h limit after which it blocks again and alerts the maintainer, and no flag or env var; (2) check-master-ci-green implements it in livespec-dev-tooling with tests, keyed on that evidence, with no LLM in the gate; (3) proved live on a real or drilled external outage; (4) every fleet repository that consumes the master-green check runs the released build.

## Definition of Done assertions derived from that statement

- The ratified livespec core and livespec-dev-tooling specifications define the external failure category as any GitHub service failure including quota and rate limits, the network or internet being unreachable, and a third-party service or tool the fleet depends on being down, and exclude a credential or permission the fleet configures, a test, lint, type or configuration failure, which stay defects.
- Each master gating job that fails publishes machine-produced external-cause records of the form dependency, kind and evidence taken from the transport or HTTP layer, and master's ci-green publishes one master-health check run reading external only when every failed gating job published such a record and defect otherwise, while ci-green's own red verdict stays unchanged.
- check-master-ci-green fails closed: a red master whose master-health run is absent, unreadable or reads defect blocks a commit and a push exactly as it does today.
- While master's only red reads external, check-master-ci-green exits 0 with a warning naming each dependency and kind and admits every commit and push, not only fixes, until master's ci.yml push run reads green, with every PR's own checks still binding.
- After 24 hours of continuous external-only red on master, check-master-ci-green blocks again and raises the repository's needs-attention signal so the maintainer is alerted.
- No environment variable, flag or configuration key changes check-master-ci-green's external-red decision, and the decision path contains no LLM call; the livespec-dev-tooling implementation is covered by tests keyed on the external-cause evidence.
- The tolerance is observed live on a real or drilled external outage: a commit or push that check-master-ci-green blocks today is admitted with the external warning while master's only red is external, and the run ids and master-health evidence are recorded on this epic.
- Every fleet repository that consumes check-master-ci-green runs a released livespec-dev-tooling build carrying the tolerance, as read from livespec core's committed fleet manifest and each consumer's pin.

# Master-green check tolerates an external outage

## Outcome and scope

`check-master-ci-green` (the fleet-shared pre-commit and pre-push gate that
refuses work while master's `ci-green` check run is red) learns ONE evidence-
keyed exception: when master's only red is EXTERNAL, it warns and admits every
commit and push instead of stalling the fleet, while the failing check itself
stays red on master and a real defect still blocks. The tolerance is bounded to
one day, after which the gate blocks again and alerts the maintainer. No flag,
environment variable or configuration key influences the decision, and no LLM
sits in the gate.

The plan is done when the four outcomes in the Definition of Done above are
OBSERVED, in order: the specification is ratified in livespec core and in
livespec-dev-tooling; the check implements it in livespec-dev-tooling with
tests keyed on the evidence; the tolerance is proved live on a real or drilled
external outage; and every fleet repository that consumes the master-green
check runs the released build. Creating the plan changes no gate, no workflow
and no verdict.

Opened 2026-11-15 ~23:3xZ by this seat on legacy-coordinator-agent's relay of
the maintainer's order (~23:5xZ wall clock in the coordinator's record).
throughput-plans-coordinator (hetzner-xubuntu, workspace throughput-
improvements) DRIVES this plan; this seat takes its direction. The seat never
raises a blocking picker; a question that truly needs the maintainer goes to
the coordinator non-blocking.

## Source of truth

Both are ledger comments on epic `livespec-dev-tooling-6tgd2z`
(legacy-coordinator-agent). Read them with
`/usr/local/bin/with-livespec-env.sh -- bd comments livespec-dev-tooling-6tgd2z`.

1. The plan-scope-event of 2026-11-15T23:22:17Z marked SUPERSEDES, titled
   "MAINTAINER DESIGN DIRECTION: the master-green check tolerates an EXTERNAL
   red". It carries the maintainer's verbatim words (a), (b), (c), quoted in
   full in the statement above, and the coordinator's seven-point deterministic
   design, restated in "The design" below.
2. The plan-scope-event of 2026-11-15T23:06:10Z, the BYPASS RULING: the
   coordinator's YES to lifting check-master-ci-green for the quota fixes,
   with five bounds. Widened by the maintainer on `livespec-dev-tooling-r7iuj6`
   at 23:13Z ("Yes the same skip can cover whatever else is chicken-and-egg on
   this plan to get things moving again") and clarified at 23:15Z ("The whole
   point is to not let failures stack up" / "But this failure is external. It's
   not due to anything we can fix" / "So even though what you're pushing
   through doesn't directly fix it, the same logic still applies until the
   external error is completely resolved").

## The design, as the coordinator read the maintainer (deterministic, no LLM)

1. The failing check's verdict is UNCHANGED. It stays red on master, so nothing
   passes vacuously. This answers the vacuous-gate objection recorded at
   `livespec_dev_tooling/fleet/_manifest_git.py:40-45` (z4qi, sh71, x7ml: a
   gate that passes because the check could not RUN).
2. CATEGORY "external": a failure whose cause is outside the repository and its
   own configuration, and which the repository cannot fix now. Examples: any
   GitHub API or service failure (rate limits and quotas, 5xx, outage), the
   network or internet unreachable (DNS, connect or timeout to a host we do not
   run), a third-party service or tool we depend on being down. NOT external: a
   credential or permission we configure (401/403 on our own token or App), a
   test, lint or type failure, our own configuration. Those stay defects.
3. The evidence is structured and MACHINE-PRODUCED: a shared helper records
   each external failure as `{dependency, kind, evidence}` from the transport
   or HTTP layer. Each master gating job publishes its records with its result,
   and `ci-green` publishes one `master-health` check run reading `defect` or
   `external` plus its causes.
4. FAIL CLOSED: a red job with no external-cause record is a defect, and
   check-master-ci-green blocks on it exactly as today. An absent or unreadable
   `master-health` run also blocks.
5. When master's only red is external, check-master-ci-green WARNS and does not
   block, for EVERY commit and push (not only fixes), until master's `ci.yml`
   push run reads green. Each PR's own checks still bind.
6. TIME LIMIT: one day. After 24 h of continuous external-only red the
   tolerance ends (the check blocks again) and the maintainer is alerted
   through the repository's needs-attention signal, so a long outage is
   surfaced, never silent. The limit is a module constant.
7. Keyed on evidence an agent cannot fabricate (the transport or HTTP layer's
   own record), never a flag or env var: compatible with livespec's
   ci-gate-discipline ban on levers. This is the ONE evidence-keyed exception
   to that rule, and `.ai/ci-gate-discipline.md` is updated alongside the
   implementation.

## Where the check lives today

- `livespec_dev_tooling/checks/master_ci_green.py` (505 lines), run by the
  justfile recipe `check-master-ci-green`. Its module docstring records why it
  reads the `ci-green` CHECK RUN on master's head commit from master's own push
  runs, and why a credentialed read that fails is `unprovable` and blocks: the
  2026-07-19 GitHub outage is the case where a fail-soft reopened the
  silent-red-master hole. The new tolerance must NOT reopen that hole: an
  outage that prevents the read is still `unprovable`, and only a `master-
  health` run that master's own CI PUBLISHED can admit a push.
- The check is fleet-shared through the livespec-dev-tooling release that
  every consuming repository pins. Discover the consumer set from livespec
  core's committed fleet manifest at implementation time; a dev-tooling-only
  rollout does not satisfy assertion 8.

## Route (rule K: fleet-shared, so core and dev-tooling both ratify)

Spec first, then ratify, then implement. No implementation before
ratification.

Two proposals were already DRAFTED by the expedited-incident-response-flag
seat (bqnzcm, hetzner) before the coordinator withdrew that routing and gave
both to this plan. Neither has a PR. They are this plan's to use, rework or
discard:

- livespec core, topic `master-green-tolerates-external-red`: branch
  `spec/propose-master-green-tolerates-external-red` at `f5e1b5d9`, worktree
  `~/.worktrees/livespec/spec/propose-master-green-tolerates-external-red`,
  file `SPECIFICATION/proposed_changes/master-green-tolerates-external-red.md`
  (blob `e0df178c`). It adds to `non-functional-requirements.md`, after "CI as
  a merge gate", the paragraph "The master-green gate tolerates an external
  red, on evidence and for at most one day", with three scenarios.
- livespec-dev-tooling, same topic: branch
  `spec/propose-master-green-tolerates-external-red` at `6ff5a9483`, worktree
  `~/.worktrees/livespec-dev-tooling/spec/propose-master-green-tolerates-external-red`,
  same file path (blob `124062ad`). It adds a `contracts.md` H2 "Master-green
  gate and external red" (the shared external-cause helper, the `master-health`
  check run, the gate's read, warn, block and 24 h rules) and four scenarios.

Grading both drafts against the design above is this seat's first task; a
grade that changes a draft re-authors it in the same worktree before the PR.
Then open both proposal PRs, revise core first (the dev-tooling contract
realizes the core rule), then dev-tooling, each revise co-editing
`tests/heading-coverage.json` per the repository's revise co-edit discipline.

Implementation children are filed under this epic only after the carrier-map
scope event exists, through capture-work-item, and are executed through the
factory. Expected cut (to be confirmed by the ratified text): the shared
external-cause helper and its publication from gating jobs; the `master-
health` check run published by `ci-green`; the gate's read-and-decide change
with the 24 h constant and the needs-attention alert; the live or drilled
proof; the fleet roll (release, then every consumer's pin).

## INTERIM, live now (recorded as this plan's first scope event)

Until the tolerance ships, the maintainer's bypass ruling IS how this plan
applies to the current quota incident `livespec-dev-tooling-zq2i4c` and to any
other external red during the livespec-ai migration. Its terms:

- `SKIP_TARGETS=check-master-ci-green` ONLY; every other gate member runs and
  every other PR check stays required and green.
- Only while master's red is external (today: the GitHub API quota and rate
  limits in check-fleet-conformance). A master red from a real check failure
  is NOT covered.
- It covers any commit or push that check-master-ci-green alone blocks, not
  only the fixes (maintainer, r7iuj6 23:13Z and 23:15Z, widening the
  coordinator's bound 1; bounds 2 to 5 stand).
- The bypass is named on the PR with the ruling, and each use is named on its
  incident item. A revert path is named before the merge.
- It ENDS the moment master's `ci.yml` push run on livespec-ai/livespec-dev-
  tooling reads SUCCESS; from then on check-master-ci-green binds as before.

This seat runs the interim with throughput-plans-coordinator, which drives
the plan; the interim is not a Definition of Done assertion, because it ends
when the plan ships.

## Deferrals

- A change to the master-health RECONCILER's classification (the existing
  `## Master-health reconciler` contract) is out of scope; the tolerance reads
  a new published check run and leaves the reconciler alone. Reconsidered only
  if the ratified text requires the reconciler to consume the same records.
- Automatic re-arming of auto-merge or merge-queue behaviour under an external
  red is out of scope; this plan changes one local gate's decision only. The
  merge-queue bypass for incidents belongs to expedited-incident-response-flag
  (bqnzcm) and stale-base-merge-options (xowhol).
- A tolerance for an outage that prevents the gate from READING master at all
  is explicitly NOT granted (design point 1 and the 2026-07-19 record); such a
  read stays `unprovable` and blocks. If the fleet needs to flow during a full
  GitHub API outage, that is a separate ruling for the coordinator to carry.

## Evidence gotchas for a successor

- Read `.ai/livespec-operation-gotchas.md` before any revise or propose-change
  step, and the revise co-edit discipline in `CLAUDE.md` before the revise
  commits.
- Resume from the ledger: `/livespec-orchestrator-beads-fabro:plan
  master-green-external-outage`, take the typed `next_action`, and start the
  `/loop` with no interval in the same turn. A seat that resumed and is not
  looping is stalled by definition.
