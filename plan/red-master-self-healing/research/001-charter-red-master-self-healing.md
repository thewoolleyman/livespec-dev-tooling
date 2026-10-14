## The maintainer's statement of what done means

"Yes, I like the self-healing" ... "it should be: if progress is being made, but still with a hard cap on it (for example, 2 hours). After that, a revert is done unconditionally, as long as it can be proven (or likely expected) that the revert will actually fix the failure." ... "Okay, this sounds like a good approach. Make a detailed plan for it with a definition of done."

## Definition of Done assertions derived from that statement

- When master CI goes red on a merge in a fleet repository and the failure is classified as a genuine regression, a revert pull request for the culprit merge is opened automatically within one reconcile cycle, with no human or agent session acting.
- A red master with no fix-forward claim returns to green by the revert pull request landing as soon as the revert's own CI is green.
- A claimed fix-forward that keeps making forward progress holds the revert, and master turns green through the fix with the culprit's work kept on master.
- A claimed fix-forward that thrashes or stalls releases the held revert, which lands once its own CI is green.
- Once master has been red for the configured hard cap, the revert lands regardless of fix-forward progress when its own CI is green, and when its CI is not green it is not merged and a needs-attention item is raised instead.
- A master failure that passes on re-run or is classified as infrastructure never results in a revert landing, and is surfaced as needs-attention instead.
- Every decision the reconciler takes is computed without any LLM call.
- Every fleet repository carries the reconciler shim installed by wire-fleet-member, and the fleet conformance run fails a repository whose shim is missing or drifted.
- A master red longer than the configured threshold with no revert pull request in flight appears as a needs-attention item.
- A scheduled drill proves the revert path end to end on a throwaway branch, and a failed drill is surfaced as a needs-attention item.
- A pull request that is green before rebase-merge does not turn master red through commit-metadata differences alone.

### Human-attested

Reason: ratifying a policy amendment is the maintainer's own act; an agent session may file the proposal but must never self-ratify it.

- The maintainer has ratified the amended ci-gate-discipline directive and the livespec merge-gate specification that sanction revert-by-default with a progress-bounded fix-forward.

## Why this plan exists

A red `master` in any fleet repository stops that repository's factory: the green-master gate refuses every dispatch until
`master` is green again. Today the return to green depends on a human or an agent session noticing and acting. This plan makes
red master SELF-HEALING: a deterministic reconciler reverts the culprit merge by default, or lets a claimed fix-forward land
while it is demonstrably making progress, under a hard cap.

Owner check (2026-10-14): no live plan in livespec-dev-tooling, livespec, or livespec-overseer has this purpose. Checked and
ruled out: livespec `gitops-deployment-instructions-and-enforcement` (livespec-okypgg), dev-tooling
`fleet-heading-coverage-convergence` (livespec-dev-tooling-0bse — owns the triggering defect a6gq5n, not the remedy class),
overseer `repo-gates-and-test-integrity` (overseer-4z97, overseer-only), overseer `fleet-plumbing-and-dispatch-reliability`
(dispatcher/beads/pin plumbing), livespec `fleet-delivery-lane-visibility`, dev-tooling `delegated-gate-fleet-rollout`
(pre-push gate). A full-ledger scan (`--status all`) of all three tenants for revert / red-master / merge-queue / fix-forward
found no open owner; the nearest is overseer-tdfe.22 (below).

## The triggering incident (2026-10-14, thewoolleyman/livespec-orchestrator-beads-fabro)

- PR #2917 passed PR CI (run 38493306513). GitHub rebase-merge minted a NEW commit `35fea321` whose committer date was
  `2026-10-13T18:12:41-07:00`.
- Master CI run 38494465107 failed `check-heading-coverage-debt-register`, which reads `%cs` — the committer date in the
  commit's OWN timezone — so the rebase-merge's metadata alone flipped the verdict. Filed as livespec-dev-tooling-a6gq5n under
  plan `fleet-heading-coverage-convergence` (epic livespec-dev-tooling-0bse); it stays there.
- Master was red ~01:17Z to ~01:55Z. A one-line fix-forward (`372f5d3d`) was still inside the local pre-push gate when a
  manual server-side revert (#2918) landed. The green-master gate refused every factory dispatch from that repository for the
  whole window, and the reverted spec revision then had to be re-landed.

Two lessons: (1) a check that is not invariant under rebase-merge metadata turns a green PR into a red master with nothing
anyone could have caught at PR time; (2) revert-vs-fix-forward was decided by whoever happened to be fastest, with no rule.

## Prior decisions this plan builds on (and does not reopen)

- livespec spec v126 (2026-06-22, maintainer-accepted; `SPECIFICATION/history/v126/proposed_changes/merge-gate-drop-strict*.md`;
  commits 27405002, 53e5edd6, 39c33ac5): branch protection MUST NOT enable `strict`; a semantic conflict between two
  individually-green PRs is ACCEPTED and caught by master CI after the merge (livespec
  `SPECIFICATION/non-functional-requirements.md` §"CI as a merge gate (branch protection)", an H3 under §"Constraints"). That
  section also rejects a merge queue and "a hand-rolled serialized auto-rebase driver". This plan is the missing second half
  of that decision: if post-merge master CI is where conflicts are caught, red master must heal without a human.
- Enforcement today: dev-tooling `branch_protection_alignment` (`strict_enabled` failure mode, e5cb8f44);
  `wire-fleet-member` PUTs `strict: false` (`livespec_dev_tooling/fleet/_reconcile.py:199`); conformance row
  `livespec_dev_tooling/fleet/_rows_github.py:194`.
- livespec `.ai/ci-gate-discipline.md`: the remedy for a gate deadlock is revert-and-reland, the revert created SERVER-SIDE;
  it forbids adding "any lever, flag or severity knob". dev-tooling `docs/server-side-revert-exemption.md` exempts a
  web-flow-signed revert that is byte-identical to the reverted commit's parent from the Red-Green-Replay range gate.
- overseer-tdfe.22 (P1, ready; successor of overseer-hgq4wi.33; parent-child edge to overseer-4z97 while its dotted id still
  ties it to CLOSED epic overseer-tdfe) records the Aug-2026 incident where two individually-green PRs merged 87 s apart
  reddened master for ~70 min, and recommends a merge queue. The maintainer has since ruled the merge queue out (below); this
  plan is the successor MECHANISM for its defect class. Disposition: a comment on overseer-tdfe.22 points here; it is not
  closed (it lives in another tenant and its owning plan decides).

## Maintainer rulings (conversation, 2026-10-14)

- Repositories are PERSONAL: GitHub merge queue is unavailable and is not a goal.
- `strict` plus an eager rebase-updater: REJECTED — up to N² CI runs per merge burst kills factory throughput.
- A serialized merge train: REJECTED — loses parallelism, and deadlocks exactly when master is broken.
- Parallel merges and today's CI volume stay. The remedy is to make red master SELF-HEALING.

## Measurements (taken in the 2026-10-14 maintainer session)

- livespec-orchestrator-beads-fabro master CI duration: median 6.4 min, p90 10.5 min (n=26).
- Merges in the prior 24 h: orchestrator 46 (peak 6/h), dev-tooling 14, overseer 20, livespec 4.
- Branch protection read 2026-10-14 (this session): `required_linear_history` is TRUE on livespec, livespec-dev-tooling,
  livespec-orchestrator-beads-fabro, and FALSE on livespec-overseer. livespec NFR §"Commit and merge discipline" requires
  `required_linear_history: true`; the `wire-fleet-member` protection PUT (`_reconcile.py:197-203`) omits the key, and a PUT
  replaces the whole protection object, so any repo it (re)wires loses linear history. Filed as a separate child (G).

## The approved design (recorded faithfully)

1. **Metadata invariance.** Every fleet CI check is invariant under rebase-merge metadata: no check depends on commit SHA,
   committer date or committer timezone (use UTC / author-date / tree content). a6gq5n is the first instance; a spec rule
   prevents reintroduction.
2. **A deterministic MASTER-HEALTH RECONCILER.** One Python module in livespec-dev-tooling (Red-Green-Replay, coverage,
   `just check`, released and pinned like other fleet tooling). Stateless reconcile: each run reads current truth from GitHub
   (master CI status per commit, open revert PR, fix-forward claim, fix PR state and CI) and takes AT MOST ONE next step.
   GitHub is the state, so crashes, missed runs and duplicate runs cannot wedge it. NO LLM in any decision path (an LLM may
   only write an optional advisory diagnosis text).
3. **Triggers.** A thin per-repo workflow shim on `workflow_run` (CI completed on master, failure or success), on revert /
   fix-forward PR events, and on a ~5-minute schedule (deadline enforcement and missed-event cover). Runs on GitHub-HOSTED
   runners so it works when the k3s runner pool is the failure. Uses the fleet GitHub App token so its PRs trigger CI.
4. **Behaviour on red master.** (a) Re-run failed jobs once and classify flake/infra — passes on re-run, or the failure also
   appears on unrelated commits, or it names an outage (no runners, expired token, registry down) — then NO revert;
   needs-attention instead. (b) Identify the culprit = the earliest red master commit whose parent was green (test candidates
   when runs were cancelled or batched). (c) Immediately OPEN the revert PR of the culprit's PR — a GitHub web-flow revert, so
   it carries the signing the server-side-revert exemption recognises — with auto-merge HELD.
5. **Revert by default, fix-forward by claim.** No claim: release the revert as soon as its own CI is green. A fix-forward
   CLAIM (mechanical: a label/comment on the revert PR naming the fix PR, by the culprit PR's owning session or the
   maintainer) HOLDS the revert while the fix makes PROGRESS. Forward transitions: claim names a fix PR; fix PR opened / new
   commit; CI starts; CI green or fewer failing checks; auto-merge armed; merged; master CI on the fix starts, goes green.
   THRASHING releases the revert: repeated red on the same check; a new commit not reducing failures; new checks failing;
   fix merged but master still red; no transition within the measured expected duration of the current step (session died,
   push never comes); competing fix PRs. Progress-based judgement, not a fixed grace timer, PLUS a HARD CAP: after 2 hours
   red (the maintainer's example value) the revert lands UNCONDITIONALLY — but only if the revert is proven (its own CI green
   on master-minus-culprit) or likely expected to fix the failure; if the revert's CI is not green it is NOT merged and a
   needs-attention item is raised for a human.
6. **Distribution.** Reusable workflow + module in livespec-dev-tooling; thin shim in every fleet repo installed and
   reconciled by `wire-fleet-member`; a conformance row fails a repo whose shim is missing or drifted. Never configured by hand
   (GitOps).
7. **Watching the watcher.** A needs-attention/hygiene row "master red longer than N minutes with no revert PR in flight"; a
   scheduled drill proving the end-to-end revert path on a throwaway branch.
8. **Policy.** ci-gate-discipline mandates the server-side revert and forbids "any lever, flag or severity knob"; the
   fix-forward claim is a SECOND sanctioned path, so the directive and livespec §"CI as a merge gate (branch protection)" are
   amended through `/livespec:propose-change` and RATIFIED BY THE MAINTAINER — never self-ratified by a session.
9. **Non-goals.** No merge queue; no `strict`; no serialized merge train; no extra CI on the happy path.

## Open maintainer calls (to be put to the maintainer in the revise of child A, one at a time)

1. WHO may claim a fix-forward: the culprit PR's owning session (identified how — PR author identity, a session id trailer?),
   the maintainer, or both. Recommendation: both; the session identified by the culprit PR's head-branch author or an
   explicit `Claimed-By:` field, and the maintainer by forge login.
2. The HARD-CAP value: 2 h proposed. Recommendation: 2 h, configurable per repo through committed config, never by hand.
3. The STALL step durations: calibrated from child F's measurement of past red-master episodes (red duration, fix-forward vs
   revert, time red→fix PR, fix PR→master green); recommendation: p90 of each measured step × a margin, recorded in config.
4. "Likely expected to fix" under the hard cap: recommendation — ONLY "proven" (revert CI green) authorizes an unconditional
   merge; the "likely" branch is limited to raising needs-attention, because a heuristic merge is exactly the judgement the
   no-LLM rule keeps out of the decision path.

## Design questions settled inside the children (not maintainer calls)

- Order of re-run vs revert-open: the revert PR MAY be opened in parallel with the re-run (its CI then runs concurrently) and
  closed if the re-run classifies flake/infra; it is never MERGED before classification. Child C1 decides and records it.
- The needs-attention surface reachable from a GitHub-hosted runner: an idempotent, one-per-episode GitHub issue with a fixed
  label. Surfacing those issues in the orchestrator's `needs-attention` operation is a deferral (below).
- The revert-creation API: GraphQL `revertPullRequest` is expected to produce a web-flow-signed commit; C1 verifies that the
  produced commit passes the server-side-revert exemption before relying on it.

## Children and order

- A — spec + directive amendment in livespec (spec-change tier; maintainer-ratified). Carries the policy assertion.
- B — metadata-invariance audit and repair of every fleet check reading commit metadata (a6gq5n is a cross-plan carrier).
- F — calibration measurement of past red-master episodes across fleet repos.
- C1 — reconciler core: detect, classify flake/infra, culprit, held revert PR, release on green with no claim, escalate on
  red revert CI, no LLM. Unblocked: revert-by-default is what the CURRENT directive already mandates.
- C2 — fix-forward claim, progress/thrash state machine, hard cap with proof condition. Blocked by A (ratification), F
  (calibrated durations) and C1.
- D — reusable workflow + per-repo shim + `wire-fleet-member` install/reconcile + conformance row. Blocked by C1 (it ships
  revert-by-default fleet-wide, which the current directive already mandates; C2 rides the same shim when it lands).
- E1 — red-without-revert detector row. Blocked by D.
- E2 — scheduled end-to-end revert drill. Blocked by D.
- G — `wire-fleet-member` protection PUT drops `required_linear_history` (separate defect found during archaeology; carries no
  plan assertion).

## Filed children (2026-10-14)

| Letter | Work item | Blocked by |
| --- | --- | --- |
| A | livespec-dev-tooling-4v2yrw (spec-change, needs-human) | — |
| B | livespec-dev-tooling-yfqvqm | — |
| F | livespec-dev-tooling-s7ctpr (host session) | — |
| G | livespec-dev-tooling-oqpfhj | — |
| C1 | livespec-dev-tooling-hrpcgl | — |
| C2 | livespec-dev-tooling-joqff6 | A, F, C1 |
| D | livespec-dev-tooling-dw7dzd | C1 |
| E1 | livespec-dev-tooling-4xrhck | D |
| E2 | livespec-dev-tooling-yilv6p | D |

Cross-plan carrier: livespec-dev-tooling-a6gq5n (plan fleet-heading-coverage-convergence) carries assertion 11 beside B and A.
The carrier map itself lives ONLY in the epic's scoping event, never here.
