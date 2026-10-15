# The master-health reconciler core — decisions recorded by child C1

Authored for work-item `livespec-dev-tooling-hrpcgl`, child C1 of plan
`red-master-self-healing`
(`plan/red-master-self-healing/research/001-charter-red-master-self-healing.md`,
epic `livespec-dev-tooling-zcp5vb`).

This document records the two decisions the charter delegated to C1, and ONE
VERIFICATION THAT CAME BACK NEGATIVE and that the rest of the plan has to
absorb. It is not a restatement of the charter; read that first.

## What C1 is, and where it stops

C1 is the DECISION layer: four pure modules under
`livespec_dev_tooling/cross_repo/` that read a recorded GitHub state and decide
AT MOST ONE next step.

| Module | Question it answers |
| --- | --- |
| `master_health_state.py` | What a recorded GitHub state and the committed config ARE |
| `master_health_episode.py` | How far back the red episode extends, and which merge caused it |
| `master_health_verdict.py` | Is this red a genuine regression, or a flake / outage / unrelated failure |
| `master_health_reconcile.py` | Given all of the above, the ONE step this run takes |

It ships NO network transport, by the binding contract of the package it lives
in: `livespec_dev_tooling/cross_repo/__init__.py` states that modules here are
network-I/O-free and "the workflows that consume them are where any network I/O
lives". The reusable workflow, the per-repo shim, the `wire-fleet-member`
install and the conformance row are child D. That boundary is also what makes
every acceptance assertion gradeable: each one opens "given a recorded GitHub
state", and a recording is something only a pure decision can be replayed
against.

The no-LLM rule is enforced mechanically rather than by review.
`tests/livespec_dev_tooling/cross_repo/test_master_health_state.py` walks the
AST of every `master_health_*.py` module and fails if any imports a network,
subprocess or model client. It is written as a GLOB, so a sibling added by a
later slice inherits the guarantee without anyone remembering to extend the
test.

## Decision 1 — the revert is opened AFTER classification, not in parallel

The charter left this to C1: "the revert PR MAY be opened in parallel with the
re-run (its CI then runs concurrently) and closed if the re-run classifies
flake/infra; it is never MERGED before classification."

**Decided: SEQUENTIAL.** The revert is opened only once the episode has been
classified as a regression. The step table reaches `STEP_OPEN_REVERT` only
through the `VERDICT_REGRESSION` branch, and an unclassified red yields
`STEP_RERUN_FAILED_JOBS` instead.

Why, given that parallel would return a red branch to green sooner:

- **The common case is the one parallel penalises.** A revert opened in
  parallel must be CLOSED again on a flake or infra verdict, and that close is
  not free: the pull request, its own CI run, and its notifications are all
  outward-facing artifacts created for an episode that turned out to be a
  non-event. Flakes and outages are not the rare case in this fleet.
- **It adds CI load exactly when CI may be the failure.** The charter puts the
  reconciler on GitHub-HOSTED runners precisely because the self-hosted k3s
  pool can itself be the thing that is broken. Opening a revert during a runner
  outage queues another run against the broken pool and makes the outage worse.
- **A closed-then-reopened revert is a worse audit trail** than one that was
  never opened. A human reading the episode later sees a revert that was
  abandoned and has to work out whether it was abandoned correctly.
- **The latency it costs is bounded and small against the governing deadline.**
  One re-run at the plan's measured master-CI duration (median 6.4 min, p90
  10.5 min) delays the revert by roughly one CI cycle. The hard cap that
  governs the whole episode is 2 hours (child C2), so the sequential ordering
  spends about 10% of the budget in the worst measured case.
- **"Never merged before classification" becomes structural.** Under
  sequential ordering there is no window in which a merge-eligible revert and
  an unclassified episode coexist, so the guarantee does not depend on a guard
  that a later change could remove.

Consequence for C2: nothing. The fix-forward claim acts on a revert that
already exists, and under this ordering it exists from the moment the
regression verdict is reached.

## Decision 2 — the needs-attention item is one issue per EPISODE

A GitHub issue carrying the fixed label `master-health-needs-attention`
(`NEEDS_ATTENTION_LABEL`), reachable from a hosted runner, following the
sibling `release_lane_issue` precedent — including its recorded hazard that the
label is the JOIN with whatever reads the screen, so renaming it silently
empties that reader rather than erroring.

The episode key is `<target_branch>@<oldest-red-commit-sha>`, computed by
`episode_key`. It is keyed on the OLDEST commit in the red block, not the head:
the head changes every time another merge lands on an already-red branch, so a
head-keyed identifier would mint a new key — and therefore a second issue — on
every such merge. The oldest commit in the block is the one identity that is
stable for as long as the episode lasts.

`target_branch` is committed CONFIGURATION rather than a hardcoded `master`
(`ReconcileConfig.target_branch`), so the scheduled end-to-end drill (child E2)
can exercise the whole path against a throwaway branch. The episode key is
derived from it, so a drill's issues cannot collide with a real episode's.

## The negative verification: a web-flow revert here is UNSIGNED

The work-item required: "The revert must be a GitHub web-flow revert (expected:
GraphQL `revertPullRequest`) — verify the produced commit satisfies
`docs/server-side-revert-exemption.md` before relying on it."

**Verified on 2026-10-14, and it does NOT.** Read-only evidence:

- `thewoolleyman/livespec-orchestrator-beads-fabro` PR **#2918** — the manual
  server-side revert from the incident that opened this plan, on GitHub's own
  auto-generated branch `revert-2917-plan/factory-run-wall-budget`. Both of its
  revert commits (`7a1a7263`, `a36f6634`) carry committer
  `GitHub <noreply@github.com>` and exactly one parent, and report
  `verification.verified: false`, `verification.reason: "unsigned"`, with NO
  signature present. GitHub minted those commits and did not sign them.
- A survey of the 30 most recent `master` commits in each of
  `livespec-orchestrator-beads-fabro` and `livespec-dev-tooling`: **60 of 60
  are `unsigned`**, including the rebase-merge commits GitHub itself mints.
- `livespec-overseer` commit `32c27a24` — the commit the exemption document
  names as its regression fixture — is also unsigned.

Why this was not already known: the exemption's ADMITTED path has only ever
been exercised against a SYNTHETIC key. `tests/livespec_dev_tooling/checks/
test_red_green_replay_revert.py` builds a throwaway gpg key per test
(`_new_signing_key`) and injects it through the keyword-only `trust_root` test
seam. The one test that touches the shipped pin
(`test_shipped_trust_root_pins_githubs_own_web_flow_keys`) asserts only that
the pin CONTAINS key material and a fingerprint — never that a real GitHub
commit verifies against it. So the exemption is correct about what it checks
and has never been confronted with what the forge actually produces.

### What it means, and what it does not

The exemption requires BOTH a web-flow signature AND byte-identity with the
reverted commit's parent, and it FAILS CLOSED. An unsigned revert therefore
gets no exemption and keeps the pre-existing verdict — conviction by
`check-red-green-replay`'s commit-range gate — whenever the revert touches
product impl `.py`.

**This does not block C1 and did not change its behaviour.** The acceptance
assertion it bears on is conditional: "given a held revert pull request with no
fix-forward claim WHOSE OWN CI IS GREEN, the reconcile run releases it to
merge." When the range gate convicts a revert, that revert's CI is not green,
so the reconciler takes the other sanctioned branch — it does not merge, and it
raises a needs-attention item. The decision table is correct under both
outcomes, which is why this is recorded rather than worked around.

**It does block end-to-end self-healing for the case the plan cares most
about.** A culprit merge that touches product impl `.py` is the common
regression, and for it the reconciler will reach needs-attention every time
rather than returning master to green unattended. Children D (fleet rollout)
and E2 (the drill) will observe exactly that, and a drill exercising a
docs-only revert would pass while the real case does not — so the drill must
revert a product-`.py` change if it is to prove anything here.

**This is not C1's to fix, and must not be fixed by weakening anything.** Both
`livespec/.ai/ci-gate-discipline.md` and the exemption document forbid adding a
lever, flag or severity knob, and a subject-line carve-out is the specific
abuse the exemption was keyed away from. The honest repairs are upstream
decisions for the maintainer:

1. Establish whether GraphQL `revertPullRequest` can produce a signed commit at
   all for these repositories — the surveyed repos show no signed commits from
   any source, which points at a repository- or account-level setting (web-flow
   commit signing) rather than at the revert API. If it can be turned on, the
   exemption works as designed and nothing else changes.
2. If it cannot, the exemption's first half needs a different unforgeable
   property. The second half — byte-identity with the reverted commit's parent,
   which is a CONTENT proof an agent cannot fake without the restored bytes
   already having earned trailers — survives on its own merits and is the
   natural place to look.

Recorded here rather than acted on, per this repository's rule that a factory
or tooling breakage stops the line instead of being routed around.

## The repair: the reconciler describes the revert commit, the forge commits it

Work-item `livespec-dev-tooling-7n2itg` acts on the finding above, and it is
NEITHER of the two repairs that section listed. Both of those put the next move
on the forge or on the exemption; this one puts it on the only participant that
was ever ours — the step that asks.

The revert step no longer asks the forge to AUTHOR a revert
(`revertPullRequest`). It builds the revert commit itself, as a
`createCommitOnBranch` mutation authenticated with the fleet GitHub App
installation token (`SPECIFICATION/contracts.md` §"GitHub App auth model"),
restoring the bytes the culprit's parent held at every path the culprit
changed. The request is a VALUE built by
`livespec_dev_tooling/cross_repo/master_health_revert_commit.py` and posted by
child D's workflow, because this package is network-I/O-free — which is also
what keeps the claim replay-testable rather than merely observed.

What this does and does not settle:

- **Both halves of the exemption still hold, unchanged.** The described commit
  carries the `This reverts commit <sha>.` lookup line and restores the
  parent's bytes, so the byte-identity half is satisfied by construction; the
  signature half is satisfied only if the forge signs. The paired tests in
  `tests/livespec_dev_tooling/checks/test_red_green_replay_revert.py` assert
  the admission AND the refusal of the same described commit without a
  signature, so describing a revert buys an agent nothing.
- **Whether the forge signs an App-authored commit is still UNMEASURED here.**
  It needs a live fleet repository and the App's private key, neither of which
  a factory sandbox publishes, so the work-item carries it as a host-captured
  assertion. If it comes back unsigned, that is a finding for the plan epic —
  the refusal leg is what still holds, and the answer is not a weaker
  exemption.
- **Restoring the parent's bytes does not narrow by what landed afterwards.**
  A later commit touching one of the culprit's paths is overwritten, which is
  the state `git revert` would stop on as a conflict. Resolving it here would
  mint new code the byte-identity half must then refuse, so the module records
  the hazard and leaves the "refuse the episode and escalate instead" decision
  to child C2, where "the revert may not be safe" already lives.
