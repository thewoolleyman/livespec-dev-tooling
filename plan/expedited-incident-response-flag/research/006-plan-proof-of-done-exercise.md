# Plan Proof of Done exercise: capture and independent replay of the 14 assertions

Research note for epic livespec-dev-tooling-bqnzcm. Written 2026-11-07 about 01:00Z to 02:00Z, read-only. No ledger,
forge, host or service was written. This is the procedure; nothing in it has been run.

Marking: **VERIFIED** means read in released code, the ledger or the forge (the source is given). **INFERRED** means
derived from verified facts and not exercised.

Sources: the epic description (14 bullets, no `### Human-attested` sub-heading, so all 14 are `host_captured`); the
plan operation prose at orchestrator build 812c6bb59d02 (v0.298.0), Step 5; that build's `_plan_record_post.py`,
`_plan_proof_leg.py`, `_plan_release_repository.py`, `_dispatcher_host_record_payload.py`; notes 001, 004 (with
section 7) and 005 (sections 9 and 10); the epic's comments, including the last carrier-map event (2026-11-05T21:29:23Z) and
the scope events of 21:31:58Z and 23:56:37Z; livespec-dev-tooling at v1.185.2 (f0fc3025) and v1.184.2;
livespec-orchestrator-beads-fabro at v0.295.1 and v0.298.0; `gh run view` for runs 42296591999 and 42316488005.

---

## 0. Summary

1. **No current evidence can go into the archive-grade record as it stands.** The archive gate grades ONE standing
   `verified` replay. It must cover all 14 assertions, postdate the latest `captured` record and the last carrier-map
   event, and name a release tag the release repository carries (section 1). Last night's evidence ran on entrance
   v1.185.1, orchestrator v0.296.1/v0.297.0 and reader v0.295.1. It also belongs to an item that can take no second
   genesis (ws2idp). It is a rehearsal and a guide to the expected observables, not reusable proof. One fragment is
   already valid on v1.185.2: master run 42316488005 (section 3, A6).
2. **Eight of the fourteen assertions need a live expedited merge to master:** A1, A6 (in its strong form), A7, A8,
   A9, A10, A11 and A12. A14 is read off the same live incident. A2 to A5 and A13 are observed along that incident's
   path. All 14 therefore come from ONE live incident on ONE new item.
3. **Five pieces of released code have no operator-reachable entrance today** (section 2). These are blockers.
   Without them the live sequence cannot produce A3, A7, A8, A9, A10 or A11, however carefully it is run. The
   largest is A7: no live recovery principal is provisioned, and the observer's job universe names only the
   aggregate `ci-green`, so a revert could fire only after the whole master run ends. That contradicts "first failing
   required master job".
4. The minimal live sequence is **three expedited attempts on one incident item** (section 4):
   - attempt 1 carries a planted deferred-spec defect, fails a required master leaf, and is reverted by the observer
     (A7, A8);
   - attempt 2 is corrected from the completed run's full failure set and goes green on master;
   - a draft probe PR then shows a related regression, which reopens the incident and reverts attempt 2 (A11);
   - attempt 3 is corrected and goes green;
   - one normal factory repayment PR removes the marker and repairs a planted DoD-only defect inside that PR (A9,
     A10);
   - closure attempts are refused until the repayment's normal master CI is green (A12), and restarts are injected
     at four points.
5. The estimate is **9 to 14 h** after the prerequisites, of which the live sequence is 5.5 to 9.75 h. Phase 7 also
   waits on two factory canaries held by legacy-dispatcher-agent (P0-11); each canary is one factory run of 1.5 to 4 h. The prerequisites take
   **4 to 8 h** of parallel hand lanes plus maintainer provisioning time that cannot be estimated (section 6).

---

## 1. What the archive gate will grade (VERIFIED, orchestrator v0.298.0)

These constraints shape the whole procedure:

- **One standing replay covers everything.** `_plan_proof_leg._standing_replay` takes the LATEST `verified` or
  `not_reproduced` record. It must be `verified` and must postdate the latest `captured` record. `_covered` then asks
  that one record whether each non-attested assertion reproduced. Consequences:
  - per-assertion or per-phase replays defeat each other, the same trap the accept valve set on bd-ib-4eeefv
    (note 005 §9.4.2);
  - the final capture and the final replay must each carry all 14 assertions;
  - partial captures published early are harmless but useless, because the last capture supersedes them.
- **The record postdates the last carrier-map event.** That is 2026-11-05T21:29:23Z today. Section 2 adds carriers,
  so a new carrier-map event follows. The capture must come after it, and so must the replay.
- **Release rule.** The release repository is named by the first word of the record's first installed build
  identifier. Its first `release_tag` must be a tag that repository carries on the forge
  (`_plan_release_repository.py`, `_release_rejection`). Name `livespec-dev-tooling vX.Y.Z` first, with
  `release_tag` set to the dev-tooling release that every dev-tooling part ran: the observer package, the CI
  entrance (which installs "latest"), the local hooks and the role. List the orchestrator release second, for the
  reader and the dispatcher; the gate does not check the second entry.
- **Independence.** `post-plan-record` computes the publishing identity. It refuses a `verified` post whose identity
  equals that of the capture it replays. The archive gate rejects such a record again however it was posted. A
  replayer launched from the capturing shell inherits `CLAUDE_CODE_SESSION_ID` and is refused
  (`.ai/independent-host-replay-identity.md`). Launch it from a different seat. The leg-2 completeness reviewer may
  be that replayer.
- **Payload shape.** The payload is `{"build": {"release_tag", "installed_build", "commit"}, "assertions": [{"text":
  <exact DoD bullet>, "steps": [...], "proof": "...", "reproduced": true}]}`. `text` must equal a DoD bullet byte for
  byte, or the post is refused as undeclared (`_dispatcher_host_record_payload.read_evidence`). A capture's
  `reproduced` field is dropped. Only the replay's `reproduced` field counts.

**Replay strategy.** The incident's revert, merges and factory run happen once and cannot be re-run without a second
incident. The replay is therefore an independent re-execution of every re-executable step, plus an independent re-read
of the immutable record the one-time events left. Re-executable steps:

- `gh run rerun` of the retained expedited and probe PR runs on their unchanged heads, as fleet-flaky-tests did for
  w7n3ad;
- `read-current` and `read-history` on the incident chain;
- authenticated `/current` and `/admitted` reads while an arm stands;
- `git` verification that the revert tree equals the exact inverse of the landed patch;
- re-running focused tests and touched-file coverage at the recorded heads.

The immutable record is the forge job and commit timestamps, the observer action receipts, the webhook delivery log and
the ledger comments. State this strategy in the capture's steps so the replayer grades re-observation, not a second
incident. Its weakness: a strict replayer may grade a one-time event as not reproducible. The alternative is a second
full incident driven by the replayer, which roughly doubles sections 4 and 6. That is not recommended.

---

## 2. Reachability audit: blockers before any live step

Each row is code that shipped but that no released surface calls, or capability the plan has not provisioned. VERIFIED
by grep over livespec-dev-tooling v1.185.2 (`livespec_dev_tooling/`, `scripts/`, `.github/`, `ansible/`) and
orchestrator v0.298.0 (`.claude-plugin/scripts/`), excluding tests.

| # | Gap | Assertions blocked | Evidence | Recommendation |
|---|---|---|---|---|
| P0-1 | **No live recovery principal.** The manifest's principal is `incident_recovery_journal_service.py`. It "reserves and journals effects; it grants no forge capability". On a registered master leaf failure, `handle_job_callback` records a `pending` action and calls `recover`. No revert reaches master. Master enforces admins, requires `ci-green` and has no rulesets (measured 2026-11-04), so nothing can merge an inverse without checks. | A7, A8, A11 | `ansible/roles/incident_observer/README.md` ("A live recovery principal with branch-protection authority is a separate provisioning the plan still owes"); `docs/incident-inverse.md:74-80`; `docs/incident-recovery-journal.md:9-14`; epic 11-04 12:47Z | File a dev-tooling carrier: a principal process that implements the six-operation protocol (`landed`, `authorize`, `head`, `lookup`, `publish`, `conflict`) against the forge under a dedicated GitHub App. The maintainer then provisions that App, its key in 1Password, and a master ruleset whose bypass list names only that App ([GO-1]). The charter's chosen design is "a dedicated recovery-controller identity" (note 001, "Speed, risk and policy decisions"). No open child carries this today. |
| P0-2 | **The observer's job universe is the aggregate only.** The manifest names `required_jobs: ["ci-green"]`. `ci-green` `needs:` every job with `if: always()`, so it fails only after the whole run. `_matches_leaf` acts only on a job named in that list, which means the revert fires at the end of the run, not at the first failing leaf. | A7 (as worded), A8 | `ansible/roles/incident_observer/defaults/main.yml:24-25`; `.github/workflows/ci.yml:996-1014`; `incident_observer.py:245-253` | Set `incident_observer_required_jobs` to every leaf job and matrix-leg name that `ci-green` needs, spelled as the `workflow_job` event names them. Release, then re-apply the role ([GO-2]). Read the names from a real master run's job list (run 42316488005 lists `check-lint`, `check-format`, `check-types`, `check-python-batch`, `check-metadata-batch`, `check-per-file-coverage`, ...). |
| P0-3 | **No repayment, regression or correction entrance.** `enter_repayment`, `advance_repayment`, `reopen_for_regression`, `record_deferred_finding` and the correction planner (`_incident_recovery_correction`) are library functions. No CLI verb, dispatcher path or drive action calls them. `incident_authority.py` exposes only `commit-transition`, `record-local-gates`, `read-local-gates`, `publish-genesis`, `file-incident`, `read-current` and `read-history`. Only `scrub_incident_flags` is wired, in `_dispatcher_run_checks.py:243`. | A8, A9, A10, A11 | orchestrator v0.298.0 `commands/incident_authority.py:65-81`; `docs/incident-authority.md` §"Normal repayment" ("models and validates the state only") | File an orchestrator carrier that adds the `incident_authority.py` actions `enter-repayment`, `advance-repayment`, `reopen-regression`, `record-deferred-finding` and `correct-attempt`, each a thin adapter over the released function. A driver script calling the functions directly (the note-004 helper precedent) is faster, but it is not an operator surface. A replayer can fairly grade "a successful master run CAUSES a new factory PR" as not reproduced on it. Decided: the carrier. The shape of A9's proof is then: `enter-repayment` refuses with `incident-repayment-master-ci-outstanding` while the master run is incomplete, and succeeds after it is green. That makes the master result the causal gate. |
| P0-4 | **No focused-evidence recorder.** `incident_focused_evidence` (the tests, touched-file coverage and `ManualReproduction` record of xluwqj) has no caller. The hook path records local gate receipts only (`incident_hook_entry.py:73`, `record-local-gates`). | A3 | grep: no importer outside the module and its `_incident_focused_*` helpers | File a dev-tooling carrier for a `python -m livespec_dev_tooling.incident_focused_evidence` entrance, or a `just incident-evidence` recipe. It runs the selected tests and touched-file coverage, takes the manual reproduction outcome and its note, and publishes the record to the incident item before merge. |
| P0-5 | **No failure-collection entrance outside the observer.** `incident_run_collector` (kobmka) has no caller. The observer's `/ci/jobs/collect` and `/ci/jobs/inspect` routes exist (`incident_observer_service.py:40-41`), and their payload has not been read for this note. | A8 | grep | Before the run, read `incident_ci_job_collection.py` and decide whether `/ci/jobs/collect` on the original run id is the collection surface. If it is, no carrier is needed; if not, fold a collector entrance into P0-4's carrier. INFERRED. |
| P0-6 | **No route from a PR-surface regression to the principal.** The observer reverts only on a callback for the registered master run (`_matches_leaf` requires `run_id == registration.run_id`). After `reopen-regression` puts the item in phase `reverting`, nothing tells the principal to revert attempt 2. | A11 | `incident_observer.py:89-166, 245-253` | Two options. (a) Add a control route `POST /recover` that takes a reopened-chain receipt and calls the same `recover`. (b) The operator runs the `EXPEDITED_INCIDENT_RESPONSE_REVERT` local path (all gates deferred, `docs/incident-local-gates.md`) and the principal merges that inverse. Recommended: (a), inside P0-1's carrier, because it keeps "one trusted controller performs every revert". |

Also needed, already in flight or cheap:

- **P0-7, orchestrator rollout.** bd-ib-mnny4v merged, released, installed in this project (`ensure-plugins`), and the
  gmktec dispatcher for dev-tooling rolled to that release and its loop restarted. A project-scope `ensure-plugins`
  here also moves this project's FACTORY dispatch build. So the install step is not the plan owner's to take: ask
  legacy-coordinator-agent first, and it sequences the step with canary 2 (P0-11, CLAUDE.md rule of 2026-11-07). A running loop keeps its build
  until restarted (`.ai/factory-span-receiver.md`). Without mnny4v, the A12 premature-closure probes would succeed
  and close the item. That is why [GO-11] waits for it.
- **P0-8, observer roll.** The observer serves dev-tooling v1.184.2 (role default; commit 00c3841a) with reader v0.295.1.
  Re-apply the role at the capture release with `incident_observer_reader_release` set to the orchestrator release
  that carries k5teti and mnny4v. Two reasons:
  1. One dev-tooling tag can then name every dev-tooling part.
  2. Between v0.295.1 and v0.298.0 the reader's `_incident_authority_reader.py` changed 85 lines and the transition
     module 33. A chain carrying a k5teti reopen carrier change may not validate under the old reader, and if it
     does not, attempt 3's `/arm` is refused. INFERRED, not tested.
- **P0-9, carrier-map event.** Record one scope event with `carriers:` that adds the P0-1, P0-3 and P0-4 children:
  P0-1 under A7, A8 and A11; P0-3 under A8 to A11; P0-4 under A3. Every later record must postdate it.
- **P0-11, factory canaries (relayed by the plan owner from gmktec-factory-placement, 2026-11-07).** The dev-tooling
  factory registration is v0.298.0 (812c6bb59d02), recorded on livespec-dev-tooling-me5aqz at 00:28:13Z.
  legacy-dispatcher-agent HOLDS every dev-tooling factory launch until a canary dispatch is green and its parity check
  passes. The canary is livespec-dev-tooling-wou75w, or xpuv6h if wou75w cannot run. Picking up `ORCH` (mnny4v plus
  P0-3) needs a second canary step on the new registration. The phase-7 repayment dispatch therefore waits on:
  - canary 1 green with parity passed, on v0.298.0;
  - `ORCH` released and registered for dev-tooling;
  - canary 2 green with parity passed, on `ORCH`.

  Canary 1 can run now, in parallel with P0. Canary 2 is on the critical path after `ORCH` is cut (section 6).
  Both are owned by legacy-dispatcher-agent. This note asks for no ordering change.
- **P0-12, range gate and correction order (found 2026-11-07, before the first arm).** `check-red-green-replay` refused
  every expedited product commit until livespec-dev-tooling-zbzls2 made it read recorded provenance through the
  observer's `/provenance` route, and no corrected attempt could get a hook-admitted commit until
  livespec-dev-tooling-se537s. Both ship in the one release that supersedes `DT` v1.187.0, and the P checks that
  version touches are re-run. Their fix PR's workflow edit gives the `check-red-green-replay` leg the read-only query
  token, on same-repository `pull_request` events only.
- **P0-10, release.** Cut one dev-tooling release after P0-1, P0-2 and P0-4 merge, and one orchestrator release after
  P0-3 and mnny4v. Every step in section 4 runs against those two tags. Call them `DT` and `ORCH` below.

**Correction to the brief: the generation floor is per incident.** The served observer v1.184.2 contains
livespec-dev-tooling-ua2scz (93f69528). `_arm_change_refusal` compares generations only when the retained arm names
the SAME incident item (`git show v1.184.2:livespec_dev_tooling/incident_observer_admission.py`, lines 224-236).
VERIFIED in code; the role default says v1.184.2 is served, so re-read the manifest's `release` before arming. A new
item therefore arms at generation 2 with `expected_arm_id` set to the retained (invalidated) gen-5 arm,
`638a230285074729605d44f5608686868c7f2ba693d37b93b9f8cbe02913b8f2`. The floor of 5 binds only ws2idp, which cannot
take a second genesis in any case. Two constraints still hold: one item, one genesis (note 004 §4), and one arm per
repository, so no other incident may arm during the sequence.

---

## 3. Per assertion: observable, reuse, steps, dependencies

The verdict "re-run" in column (b) means the evidence exercised an older build. It can still guide the run, but it
cannot be cited in the record. The steps (c) refer to section 4.

| # | (a) Observable on a real surface | (b) Tonight's evidence | (c) Steps | (d) Depends on |
|---|---|---|---|---|
| A1 | The new item carries a genesis comment. The expedited PR (label `expedited-incident-response` and an incident body block) is merged from a local worktree. No Fabro run exists for the item before repayment. Attempt 2 is committed and pushed while master's latest completed run is red: attempt 1's run failed and the revert run is in flight. The hook admits it in repair mode, where a normal commit would refuse on red master. | Re-run: #3624 never merged; drill entrance v1.185.1 | 3.1-3.6, 4.4, 5.2 | P0-1, P0-10 |
| A2 | The hook output and the `record-local-gates` receipt on the item, for the commit and the push of each attempt: report `expedited-local-partial`; `check-lint` and `check-format` executed, each well under 60 s; every other target `deferred`. No gate-runner record of a `just check` aggregate, and no remote delegated job, in `tmp/gate-runs/` or the cluster for that window. | Re-run (no expedited local commit was part of the drill) | 3.3, 4.4, 6.4 | P0-10 |
| A3 | Before each merge, a focused-evidence record on the item: the selected changed or related tests and their results, per-file coverage for touched product files only, and one manual reproduction with its outcome. | Re-run; no recorder exists (P0-4) | 3.4, 4.5, 6.5 | P0-4 |
| A4 | Expedited PR run: `incident-ci` succeeds; exactly `check-per-file-coverage`, `check-coverage`, `check-check-coverage-incremental`, `check-heading-coverage`, `check-heading-coverage-debt-register` and `check-no-todo-registry` print `omitted-by-incident-policy` (corrected 2026-11-07; `check-doctor` and `check-spec-*` name no real member); `check-lint` and `check-format` and every non-omitted job run in full; the `ci-green` summary lists the omissions. | Re-run: run 42296591999 used entrance v1.185.1 | 3.7, 4.6, 6.6 | P0-10 |
| A5 | `git show` of each attempt's landed commits contains `# EXPEDITED_INCIDENT_RESPONSE flag: <item>` next to a changed line. The hook's marker scope (`incident_hook_scope.py` with `incident_markers`) admitted it. | Re-run | 3.2, 4.4, 6.4 | none |
| A6 | Master push run of each expedited merge commit: `incident-ci` logs `selected nothing (push event: the normal complete policy is the gate)`; every job runs; nothing is omitted, although the merged PR carried the label and block and the commit carries the marker. Variables and the ambient environment are unchanged. | Partial: master run 42316488005 (f0fc3025, entrance v1.185.2, 00:09:32Z to 00:21:58Z) shows the normal policy on v1.185.2, but on a merge with no marker, label or block. Re-run on the incident merges. | 3.9, 4.7, 6.8, 7.4 | P0-10 |
| A7 | Attempt 1's master run: the first failing required leaf (`check-metadata-batch`, about 1.5 min into the run) has a `completed_at`. The observer journal shows the callback and the action. A revert commit by the principal identity lands on master: its tree equals master minus the exact landed patch, and its time is minutes after the leaf failure. No local gate run, factory run or PR CI precedes it. | Not exercised tonight (no merge, no principal) | 3.10-3.11 | P0-1, P0-2 |
| A8 | Attempt 1's run is NOT cancelled. It reaches `completed` with all job conclusions, including legs that finished after the revert. The collected failure set lists every failed member, not only the first. Attempt 2 is a new attempt on the SAME item and chain. Its diff fixes every member in that set and keeps the marker. Its master run is green. | Not exercised | 3.12, 4.1-4.8 | P0-1, P0-3, P0-5 |
| A9 | `enter-repayment` refuses `incident-repayment-master-ci-outstanding` before the green master run completes, and records `repayment-admission` after it. A normal factory run through the petri seat produces a NEW PR on the same item. Neither incident flag is present: there is no label or block, and the dispatch environment is scrubbed. The PR removes the marker. Its normal CI runs full per-file coverage and spec members over the cumulative original paths. | Not exercised | 7.1-7.7 | P0-3, P0-7 |
| A10 | The repayment PR carries the fix and a test for the planted DoD-only defect. `record-deferred-finding` recorded `deferred-finding:<run>` debt and it shows repaid. No revert of attempt 3 exists on master; an attempt to reopen on that finding is refused `incident-finding-deferred-proof-only`. | Not exercised | 7.5-7.6 | P0-3 |
| A11 | Probe PR CI fails on a test that exercises attempt 2's landed change. The attribution names the failing job, the test and the landed commit. `reopen-regression` records phase `reverting` with `repayment_required: true` and a `livespec-incident-recovery-v1` comment. The principal reverts attempt 2. Attempt 3 is a corrected expedited attempt on the same item. Repayment is then re-entered, not skipped. | Not exercised | 5.1-5.6, 6.x | P0-1, P0-3, P0-6 |
| A12 | Four restarts, each followed by exactly one action and no duplicate: (i) observer restart after arm, before merge; (ii) observer restart after bind, before the leaf failure; (iii) webhook redelivery of the failing job delivery answering `existing immutable action; no duplicate effect`; (iv) gmktec dispatcher loop restart mid-repayment. Before the repayment PR merges, and again before its master CI is green, `close`, the `accept:` valve and `reconcile-merged` each refuse and name the open obligation. After green, closure succeeds. | Not exercised; mnny4v not released | 3.8, 3.10, 3.11, 7.3, 7.8-7.9 | P0-7 |
| A13 | Four observations on the same run: incident context crosses the hook (receipt), the credential wrapper (corrected 2026-11-07, measured: the wrapper PASSES `EXPEDITED_INCIDENT_RESPONSE` and `LIVESPEC_INCIDENT_LOCAL_OPERATION` through, so the normal half of this assertion must start with both unset), the detached gate runner (`gate_runner_delegate`) and the PR event boundary (`incident-ci` reads the block from an authenticated PR read). The repayment PR's per-file coverage executes in full (about 10 min or more, not a cache hit). A normal `just check` started in the attempt-3 worktree after the expedited commit does not accept the `expedited-local-partial` report as a pass. | Re-run | 3.3, 6.4, 7.6, 7.10 | P0-10 |
| A14 | One `read-history` plus `context livespec-dev-tooling-<item>` shows all attempts, the PR, merge and revert SHAs, the master run ids, the omitted members, the focused evidence, the deferred spec debt, the deferred finding and the repayment PR with its proof, keyed by the item id alone. | Not exercised | 8.1 | all |

The charter's longer exercise list (note 001, "Proof and completion requirements") also names multi-commit rebase
merges, overlapping incidents, release fan-out and others. Those are not plan assertions, so the archive gate does not
grade them. The children's factory-captured tests carry them. This note does not add live steps for them.

---

## 4. The minimal live sequence

Conventions:

- `ITEM` is the new incident item. `DT` and `ORCH` are the releases from P0-10.
  - Released as of 2026-11-07 ~04:40Z: DT v1.186.1, which carries livespec-dev-tooling#3673 (the observer was
    rolled to it at 04:35Z, evidence on livespec-dev-tooling-7536jf), and ORCH v0.300.0, which carries P0-7
    (livespec-orchestrator-beads-fabro#4584). Neither follow-up release is pending. Re-read the serving versions at
    P.1.
- `IA` is `incident_authority.py` of the registered build; resolve it with `registered_plugin_root.py --repo $REPO`.
- Every ledger call goes through `/usr/local/bin/with-livespec-env.sh --`.
- Every `IA` action takes CANONICAL JSON: build each JSON argument with `jq -cS`. Two actions take more than JSON
  (bd-ib-nabx3u, livespec-orchestrator-beads-fabro#4579):
  - `enter-repayment` takes `--master-run <id>` and reads that run from the forge itself, so it needs `gh` auth.
  - `reopen-regression` takes `--principal` and `--attributed-json`.
- Arming follows note 004 steps 2 to 8 with its §7 corrections:
  - add `do-not-merge` before any reopen;
  - GET the pull until `merge_commit_sha` sits on the base, THEN reopen;
  - reopen once, with the base frozen under a coordinator master hold.
- `[GO-n]` marks a step that needs the coordinator's GO or maintainer consent first (section 5).

### Phase P: pre-flight (no live effect)

- P.1 Verify P0-1 to P0-10 are done. Each serving version must be read from the serving component, not from git.
  Read the observer manifest `release`, `reader_release` and `required_jobs` with `sudo` read-only. Run
  `registered_plugin_currency.py` here. Read the gmktec dispatcher's build from its own loop record.
- P.2 Run the observer's exact reader argv once as `livespec-incident` and require exit 0 (note 004 §7).
- P.3 Prove the plant once without touching master. Open a DRAFT, unlabelled PR carrying only attempt 1's planted
  defect. Require the full normal CI to fail exactly the intended spec member in `check-metadata-batch`, and nothing
  else. Close it.
- P.4 Time 7 `bd show` calls (note 004 R1). The chain will grow to about 12 to 16 generations by attempt 3. At about
  1.07 s per generation beyond 2, a reader pass reaches roughly 20 to 25 s. That is under the 45 s reader ceiling
  and the 60 s CI client ceiling, but it adds about 2 min per expedited PR run (about 5 `/current` calls).
  INFERRED.
- P.5 Confirm the repository webhook subscribes `workflow_job` to the Funnel `/callback`, and that recent deliveries
  answer 202 or 403 (note 004 §5).

### Phase 3: attempt 1, planted master failure, revert (A1-A8, A12 i-iii)

- 3.1 File ITEM with `IA file-incident` or the capture operation: a real small incident with two behavioural DoD
  bullets, B1 and B2. B2 is the A10 plant in 7.5. The item must name an open claim token; the tenant has been cut
  over since truk55.
- 3.2 Worktree; minimal fix for B1 with the marker comment beside it. Planted deferred-spec defect: the fix adds a
  `## ` heading to a governed spec file without its `tests/heading-coverage.json` row. Deferred spec work is allowed
  by the policy. `check-heading-coverage` is an `incident-policy:spec` member, so it is omitted on the PR, deferred
  locally (not annotated fast), and fails on master in `check-metadata-batch`.
  - Alternative if P.3 shows the heading change also trips another member in a way that confuses the evidence: an
    uncovered branch in the touched file, which fails `check-per-file-coverage` about 10 min into the run. This
    alternative gives less margin before the run ends.
- 3.3 Genesis (note 004 step 3), then the expedited commit and push with the incident context. Capture the hook
  output and the `record-local-gates` receipt (A2, A13 hook and wrapper).
- 3.4 Focused evidence through P0-4's entrance: tests for B1, touched-file coverage, manual reproduction (A3).
- 3.5 Open the PR AS A DRAFT from a branch of this repository, then bind it to generation 2 (note 004 step 5).
  Corrected 2026-11-07: `auto-enable-merge.yml` fires on `opened`, and a later `do-not-merge` label may not clear
  auto-merge once set (inferred, not measured), so a non-draft open could merge at 3.7 and skip 3.8 and GO-4 with an
  unbound callback. Assert `autoMergeRequest == null` before the reopen. Add `do-not-merge` before marking ready,
  because `ready_for_review` also fires the workflow. The same holds for 4.6 and 6.x. Genesis at 3.3 declares every
  path the three attempts will touch, in `original_paths`, including `tests/heading-coverage.json`, its debt register
  and the probe test, because a correction cannot widen that list (`incident_hook_scope.py`). Those paths enter the
  repayment's scope.
- 3.6 [GO-3] Master hold. Arm (note 004 steps 6 and 7) with `expected_arm_id = 638a2302…`. Add the label, the block
  and `do-not-merge`. GET until `merge_commit_sha` sits on the frozen base, then reopen once.
- 3.7 Expedited PR run: record A4.
- 3.8 [GO-8] Restart the observer unit. Repeat the authenticated `/admitted` read: still 202 (A12 i).
- 3.9 [GO-4] Remove `do-not-merge` and release the hold. Rebase-merge the expedited PR; `ci-green` passes through
  omission. Within seconds of the push run's creation, a scripted POST `/bind` sends the master head SHA and run id.
  Poll `gh run list --branch master --commit <sha>` every 2 s and bind on first sight. Do not do this by hand: the
  planted leaf fails about 90 s into the run, and a callback that arrives before the bind is ignored as "outside the
  registered incident master leaf universe" (`incident_observer.py:131-138`).
  - The observer acts only on a `workflow_job` delivery whose action is `completed`. It answers `queued` and
    `in_progress` deliveries with 403 by design (repository hook 707919835), so a 403 in the delivery log is not a
    fault.
- 3.10 [GO-8] Between the bind and the leaf failure (or as soon as possible after the bind), restart the observer
  unit, so the bound registration must come back from the state file (A12 ii).
- 3.11 [GO-5] The leaf fails, the callback arrives, and the principal publishes the inverse to master (A7). Then
  [GO-9] redeliver that webhook delivery through the hook deliveries API and require the reply
  `existing immutable action; no duplicate effect` with no second revert (A12 iii).
- 3.12 Do NOT cancel attempt 1's run. Wait for `completed`, then collect every job conclusion (P0-5) (A8). Master is
  red until the revert's own run is green, about 12 min.
  - The P0-5 entrance is `python -m livespec_dev_tooling.incident_original_run_entry collect|propose-correction`
    (livespec-dev-tooling-zvntys, livespec-dev-tooling#3666 and livespec-dev-tooling#3668). Run it as the controller
    account (`livespec-incident`) with `--state-dir` set to the observer's state directory, so the evidence lands
    beside the registration it reads. Each subcommand prints one schema-1 JSON reply. A refusal exits 78 and names
    its reason.
  - The operator supplies the EXPECTED JOB GRAPH as a JSON file (`--expected-graph`) covering every job the
    registration watched. Matrix leg names cannot be derived statically, so write the graph by hand from the
    registration's job list.
  - Order: `IA reopen-regression` (records the `recovery-<digest>` attempt) → `IA record-revert-receipt` (moves that
    attempt to `collecting-failures`) → `collect --revert-sha <sha>` (refuses until the original run has completed)
    → `propose-correction` in 4.1.
  - The evidence record is a ledger comment carrying the marker `livespec-incident-original-run-evidence-v1`.

### Phase 4: attempt 2, corrected from complete evidence (A1 red-master half, A8)

- Order corrected 2026-11-07 (livespec-dev-tooling-se537s). The hook refuses a commit while the chain reads
  `collecting-failures`, so the repair cannot be committed first. Stage the repair (4.2), `git write-tree`, take 4.1
  with `--next-head-sha <base> --staged-tree <tree>`, then 4.4 commits under the hook, and `commit-transition` advances
  the attempt's head before the push, exactly as after genesis. Never `--resolved` for a repair, and never `git
  commit-tree`.
- 4.1 Transition the chain to the corrected attempt through P0-3's `correct-attempt`. The attempt id is new; the item
  is the same.
  - Enter it through the P0-5 entrance's `propose-correction` (see 3.12), which hands the correction to the canonical
    `correct-attempt` action. Pass `--evidence-digest` from the `collect` reply, `--current-attempt
    recovery-<digest>`, `--current-owner <principal>` and `--current-generation <N>`, plus `--next-head-sha` and
    `--target-ref` (the corrected attempt's reserved branch).
- 4.2 Fix every failed member in the collected set: add the heading-coverage row, register its debt, or move the spec
  change into a recorded deferred-spec debt, whichever the failure set demands. Keep the marker.
- 4.3 If the revert run has not yet gone green, take 4.4 while master's latest completed run is still red (A1).
- 4.4 Expedited commit and push: hook receipt (A2, A5).
- 4.5 Focused evidence (A3).
- 4.6 [GO-3] Bind the new PR, then arm with `expected_arm_id` set to attempt 1's arm id. Expedited PR run (A4).
- 4.7 [GO-6] Merge and bind as in 3.9. The master run is green (A6). The chain moves to `master-observation`.
- 4.8 `enter-repayment` BEFORE the run completes: refused `incident-repayment-master-ci-outstanding` (A9 refusal half).
  Do not enter repayment after green yet; Phase 5 needs the attempt-2 reading.

### Phase 5: related regression on another PR (A11)

- 5.1 Open a DRAFT probe PR labelled `do-not-merge`. It adds one test that exercises attempt 2's changed behaviour on
  an input the expedited tests did not cover, and that input breaks on attempt 2. Its normal CI fails on that test.
  This stands in for "another PR's CI caught it" without putting anything red on master.
- 5.2 Enter repayment on attempt 2's green run (`repayment-admission`). This puts the item where k5teti's reopen
  applies (`REOPEN_FROM` = the repayment phases or `closed`).
- 5.3 Record the attribution: probe PR number, run id, failing job and test, and attempt 2's landed commit.
  `reopen-regression` records phase `reverting` with `repayment_required: true` (A11).
- 5.4 [GO-5] The principal reverts attempt 2's landed patch, through P0-6's route.
- 5.5 Show that the superseded repayment is fenced: `require_repayment_current` refuses `incident-repayment-superseded`
  on a proof or closure probe (A12, k5teti).
- 5.6 Close the probe PR unmerged, or keep its test for attempt 3; that test is the regression's evidence.

### Phase 6: attempt 3, corrected expedited attempt (A11 corrected half)

- 6.1 `correct-attempt` on the same item. The fix makes the probe test pass. Include that test.
- 6.2 to 6.8 Repeat 4.4 to 4.7: hook receipt, focused evidence, [GO-3] arm, expedited PR run, [GO-6] merge, bind,
  green master run (A2 to A6 a third time).

### Phase 7: normal factory repayment, deferred-proof defect, closure (A9, A10, A12, A13)

- 7.0 Gate: canary 2 (P0-11) is green, its parity check passed on the `ORCH` registration, and legacy-dispatcher-agent
  has lifted its dev-tooling launch hold. Read this from the canary item and the dispatcher's own record. A handoff
  saying so does not count. Until then, phase 7 waits; the wait is not a maintainer question.
- 7.1 `enter-repayment` on attempt 3's completed green run, which records `repayment-admission` (A9 causal half).
- 7.2 [GO-10] Dispatch the repayment through the `petri-factory-on-gmktec` seat. Do not use a direct `drive impl:`
  call (`.ai/fabro-dispatch-diagnosis.md`). Confirm the dispatch environment carries neither flag.
- 7.3 [GO-8] Restart the gmktec dispatcher loop while the run is active. The run and its claim survive, and no second
  dispatch appears (A12 iv).
- 7.4 Premature-closure probes while only expedited merges exist: `close`, the `accept:` valve and
  `reconcile-merged --pr <attempt 3 PR>`. Each must refuse and name the outstanding repayment ([GO-11]; only after
  P0-7 is verified serving).
- 7.5 The A10 plant is DoD bullet B2. The expedited attempts left an edge case of B2 wrong. Every line is covered and
  no existing test fails, so neither the expedited PR nor master catches it. The repayment brief carries the
  cumulative original scope and the DoD, so the factory implementer must add a Red test for B2 and fix it inside the
  repayment PR.
  - Risk: the worker may miss it. Then acceptance grades the cumulative DoD (mnny4v) and sends rework into the same
    PR. That still satisfies "fixed within that follow-up PR".
  - Do not pre-record the finding. It must be found by the follow-up.
- 7.6 When the run reports the B2 finding, record it with `record-deferred-finding`. Try a reopen on it and require
  the refusal `incident-finding-deferred-proof-only`. The repayment PR's normal CI runs per-file coverage in full and
  runs the spec members (A10, A13 cache half).
- 7.7 The repayment PR merges on full checks. The marker for ITEM is gone (`git grep` on master).
- 7.8 Before the repayment's master run completes, run `close` again: refused (A12).
- 7.9 After that run is green: closure succeeds (A12).
  - Coordinator ruling: run `IA bind-repayment-acceptance --pr <n>` BY HAND first, then `IA complete-incident
    --master-run <id>` with the manual-outcome and debt flags. Keep this manual order until the post-freeze
    Dispatcher binding lands (bd-ib-pqz3nw, livespec-orchestrator-beads-fabro#4583).
  - Name the REPAYMENT attempt in both calls, not attempt 3. `enter-repayment` creates a new attempt
    `repayment-<24hex>` owned by `fabro`. Pass that attempt id with owner `fabro` to both actions:
    `bind-repayment-acceptance` at its repayment-active generation (for example gen 6, which records gen 7), and
    `complete-incident` at the repayment-acceptance generation (which records gen 8, closed). Measured by the
    real-chain test in livespec-orchestrator-beads-fabro#4585 (bd-ib-pqz3nw).
- 7.10 Normal-validation probe: in a clean worktree at attempt 3's head, `just check` re-runs every member. It reuses
  no expedited report (A13).

### Phase 8: capture, replay, review, archive

- 8.1 The capturing session runs `read-history` and `context ITEM` (A14). It assembles one payload with all 14
  bullets, the build `livespec-dev-tooling DT` (orchestrator `ORCH` second) and the steps and proof above. Post it
  with `dispatcher.py post-plan-record --verdict captured`.
- 8.2 A different seat, launched outside this shell, replays every re-executable step (section 1) and re-reads the
  immutable record. It posts ONE `verified` record covering all 14.
- 8.3 A fresh reviewer records the completeness review with `record_completeness_review_evidence` from its own
  session. Before the archive PR: sweep for references to `plan/expedited-incident-response-flag/` outside `plan/`,
  and give osyzv6 its disposition, since leg 1 requires every child closed.

---

## 5. Steps that need GO before they run

| GO | Step | Why it is outward-facing or destructive | Who |
|---|---|---|---|
| GO-1 | Provision the recovery principal: GitHub App, key in 1Password, master ruleset whose bypass names only that App | Grants a principal unchecked writes to master; maintainer tier (`.ai/fleet-and-secrets.md`) | maintainer |
| GO-2 | Role change (`required_jobs` leaf list, reader release), release, `ansible` apply on vps | Host mutation; restarts the observer; changes the arm identity | coordinator GO; maintainer if the role touches secrets |
| GO-3 | Master hold for each arm (3 times, about 4 min each; disarms auto-merge on about 10 PRs) | Holds other people's merges | coordinator |
| GO-4 | Merge attempt 1 knowing it will fail a required master job | A DELIBERATE RED MASTER. If the revert fires, master HEAD never shows a red `ci-green`; see section 7.3. If it does not fire, master is red from about T+12 min until the manual rollback lands. | coordinator GO plus maintainer consent |
| GO-5 | Automatic reverts on master, after attempt 1 and after attempt 2 | Unchecked writes to master by the principal | coordinator (covered by the GO-1 consent) |
| GO-6 | Merge attempts 2 and 3 on reduced PR checks | Merges with coverage and spec omitted, as the incident policy intends | coordinator |
| GO-8 | Restart the observer unit (twice) and the gmktec dispatcher loop | Host and factory mutation during live work | coordinator |
| GO-9 | Webhook redelivery | Re-sends a signed event to our own observer; low risk | coordinator |
| GO-10 | Factory dispatch of the repayment | Spends factory capacity and budget | coordinator, through the petri seat |
| GO-11 | Premature-closure probes | Would CLOSE the item if mnny4v were not serving; run only after P.1 confirms it | plan owner, after P.1 |

Draft probe PR 5.1 and pre-flight PR P.3 are drafts carrying `do-not-merge`. They need no GO.

---

## 6. Wall-time estimate (from measured durations)

Measured inputs:

- Expedited PR run: about 4.3 min of job time (42296591999 attempt 2, 21:46:14Z to 21:50:28Z), plus about 2 min for
  the longer reader (P.4).
- Master run: 12.4 min (42316488005).
- Normal PR per-file coverage: 10 to 46 min (note 005 §9.7).
- Dev-tooling gates: median 3.2 min; orchestrator gates: median 13.4 min (§9.7).
- Arm with a frozen base: about 20 min, against tonight's 3 h 18 m with four failure classes that §7 now prevents.
- Factory runs on plan carriers: about 3.3 h average and 0 of 7 green (note 005 §1). This is the largest risk.

| Phase | Work | Estimate |
|---|---|---|
| P0 | P0-1 and P0-6 principal carrier (code; the maintainer provisioning time is not estimable); P0-3 verbs (orchestrator, about 8 gates); P0-4 recorder; P0-2 and P0-8 role and release; P0-7 rollout; P0-9 scope event. All run in parallel. | 4 to 8 h, plus maintainer time |
| C1 | Canary 1 on v0.298.0 (wou75w or xpuv6h) plus the parity check; runs in parallel with P0 | 1.5 to 4 h (one factory run) |
| C2 | After `ORCH` is cut: registration, then canary 2 plus parity; runs in parallel with phases P to 6 | 1.5 to 4 h (one factory run) |
| P | Pre-flight, including the P.3 plant PR (full PR CI) | 0.5 to 1 h |
| 3 | Attempt 1: file, genesis, commit, evidence, arm, PR run, merge, bind, revert, original run to completion | 1 to 1.25 h |
| 4 | Attempt 2 | 0.75 to 1 h |
| 5 | Probe PR (full PR CI 15 to 45 min), attribution, reopen, revert | 0.5 to 1 h |
| 6 | Attempt 3 | 0.75 to 1 h |
| 7 | Repayment: factory run 1.5 to 4 h, normal PR CI 0.3 to 0.8 h, master 0.2 h, probes | 2.5 to 5.5 h |
| 8 | Capture 0.5 h; independent replay including PR reruns 1 to 1.5 h; completeness review about 1 h; archive PR 0.5 h | 3 to 3.5 h |
| **Total** | after P0: phases P to 8 | **9 to 14 h** |
| | of which the live sequence (phases 3 to 7) | **5.5 to 9.75 h** |

Wall time is dominated by factory runs (C2, then phase 7), then P0-1's provisioning wait. Phases 3 to 6 are about 3
to 4 h of attended work under four short master holds.

The critical path into phase 7 is:

`P0-3 merged` → `ORCH` cut → C2 green → phase 7

That runs in parallel with:

phases P to 6 (about 3.5 to 5 h)

Phase 7 starts at whichever of the two finishes later. With C2 at 1.5 to 4 h, the two branches are about the same
length. A red canary adds a full factory run (another 1.5 to 4 h), and so would a failed repayment run. On note 005's
record of 0 green in 7 plan-carrier runs, the upper bound is the honest planning figure.

---

## 7. Window, holds, affected repositories and rollback (for the coordinator's ruling)

### 7.1 Proposed window

T0 is the first hour after all of the following hold:

- P0 has merged and been released;
- P.1 to P.5 pass;
- the maintainer has given GO-1 and GO-4 and is reachable. GO-4's rollback (7.4) needs nobody else, but a maintainer
  should be able to see the red if it happens.

If P0 lands by about 11:00Z, the proposal is **T0 = 2026-11-07 12:00Z**. Otherwise, the first top of the hour after
the conditions hold.

| Phase | Start | Duration | Holds inside it |
|---|---|---|---|
| C1 (canary 1) | now, independent of T0 | 1.5 to 4 h | none |
| P | T0 | 0.5 to 1 h | none |
| 3, attempt 1 | T0 + 1 h | 1 to 1.25 h | H1, about 40 min: arm, PR run, merge, bind, revert, then attempt 1's run and the revert run to completion |
| 4, attempt 2 | T0 + 2 h 15 m | 0.75 to 1 h | H2, about 25 min: arm to green master |
| 5, probe and revert | T0 + 3 h 15 m | 0.5 to 1 h | H3, about 20 min: revert of attempt 2 and its master run |
| 6, attempt 3 | T0 + 4 h 15 m | 0.75 to 1 h | H4, about 25 min |
| C2 (canary 2) | when `ORCH` is cut, before T0 if possible | 1.5 to 4 h | none |
| 7, repayment | the later of T0 + 5 h 15 m and C2 green | 2.5 to 5.5 h | none: the repayment merges through normal checks |
| 8, capture, replay, review | after 7 | 3 to 3.5 h | none |

Holds total about 1 h 50 m, spread over about 4 h 15 m, so between holds master is open for ordinary merges. A
**release freeze** runs from the cut of `DT` until the 8.2 replay is posted (7.3).

### 7.2 Master hold and auto-merge disarm

A hold does two jobs:

- it freezes the base from arm to CI run (note 004 §7: a reopen moves `.base.sha`);
- it keeps unrelated merges out of the window in which an incident patch lands and may be inverted, so the inverse
  applies to a quiet master and nobody rebases onto a commit about to be reverted.

**Which PRs.** Every open, non-draft PR whose auto-merge is enabled at the moment the hold starts. Re-read the list at
each hold start with `gh pr list --state open --json number,isDraft,autoMergeRequest`. At 01:50Z it was nine PRs:
livespec-dev-tooling#3660, #3478, #3421, #3288, #2315, #2307, #1399, #1373 and #1299. Three of those are factory-bot
pin bumps (#3478, #2315, #2307). PRs that open during the window count too. Draft factory PRs (#3658, #3516, #3299,
#3285) cannot merge and are left alone. The release-please PR is held for the whole freeze, not per hold.

**How.** Order matters:

1. Add the `do-not-merge` label to each PR. `auto-enable-merge.yml` re-enables auto-merge on `opened`, `reopened`,
   `ready_for_review`, `synchronize` and `unlabeled` events, and `--disable-auto` alone does not hold (note 004 §7).
2. Then run `gh pr merge <n> --disable-auto` on each.
3. Record the list.

Restore: for the recorded PRs only, remove the label, then run `gh pr merge <n> --auto --rebase`.

**Who.** The coordinator (legacy-coordinator-agent) disarms and restores, as it did for the four holds on 2026-11-06
(9 to 11 PRs each, coordinator 18:14:39Z, 18:25:35Z, 21:07:59Z, 21:11:31Z). The plan owner's part:

- request each hold by message, with its purpose and planned length;
- send "hold released" when the hold's last master run is green.

**Ceiling: 45 min per hold.** At the ceiling, the coordinator restores without waiting. The plan owner then restarts
that attempt from re-arm (note 004 step 5 onward, next generation), which writes nothing destructive.

### 7.3 Every repository affected

- **livespec-dev-tooling (master).** It receives the three expedited merges, two observer reverts, the four holds and
  the release freeze. The push-gate question:
  - `check-master-ci-green` reads the `ci-green` check run on master's HEAD commit. It treats `queued`, `in_progress`
    and `pending` as non-blocking (`livespec_dev_tooling/checks/master_ci_green.py:81,160-161,401-403`), and refuses
    only a concluded failure on HEAD. VERIFIED in code.
  - **If the revert fires as designed:** HEAD is attempt 1's commit, with `ci-green` pending, for about 1.5 to 3 min.
    Then HEAD is the revert commit, pending for about 12 min, then green. Attempt 1's red `ci-green` concludes on a
    commit that is no longer HEAD. **No other seat's push gate refuses at any point.** INFERRED from that code.
    Confirm it in P.1 by reading which commit the check queries.
  - **If the revert does NOT fire:** attempt 1's `ci-green` concludes failure on HEAD at about T(merge) + 12.4 min.
    From then until a rollback commit becomes HEAD, every dev-tooling seat's pre-push refuses, factory janitor pushes
    included. The rollback in 7.4 is timed to land before T(merge) + 12 min, so that window should not open.
  - Phase 5's revert of attempt 2 follows a green run, so it is a pending period only, with no red. Attempts 2 and 3
    are expected green.
- **Release freeze (same repository).** The `incident-ci` job installs the LATEST dev-tooling release. A release cut
  mid-sequence would do two things. It would make later PR runs exercise a tag other than `DT`, which breaks the
  record's single build identity. And if cut between attempt 1's merge and its revert, it would ship the planted
  defect. `release-dispatch.yml` fans out `sibling-released` to every `livespec-sibling` repository, which opens
  pin-bump PRs across the fleet.

  So, from the cut of `DT` until the 8.2 replay is posted, the release-please PR carries `do-not-merge`, and the
  coordinator keeps it disarmed. The freeze covers the repayment merge too; release once the replay is posted.
- **livespec-orchestrator-beads-fabro.** It ships P0-3, mnny4v and the `ORCH` release, all ordinary normal-gate work.
  The live sequence has no master effect there. While dev-tooling is frozen there is no dev-tooling pin bump PR.
- **Sibling repositories** (the `livespec-sibling` topic, including livespec, livespec-overseer and
  livespec-driver-codex). They are affected only through a dev-tooling release. The freeze prevents that.
- **gmktec factory.** C1, C2, the repayment run and one dispatcher loop restart. Ordinary dev-tooling dispatch stays
  under legacy-dispatcher-agent's existing canary hold; this note asks for nothing beyond it.
- **vps.** One role apply (GO-2) and two observer restarts (GO-8).
- **livespec-dev-tooling repository settings.** The recovery App installation and the master ruleset (GO-1).

### 7.4 Rollback for each outward-facing step

| Step | Failure it guards against | Rollback | Who | When |
|---|---|---|---|---|
| GO-1 App and ruleset | The ruleset blocks ordinary merges, or the bypass is wider than one App | Corrected 2026-11-07: `ci-green` is held by ruleset 26758787 since the 17:19:41Z classic flip. First restore the classic requirement (PATCH `required_status_checks` contexts `['ci-green']`), then delete the ruleset or remove the bypass entry, and suspend the App installation. Deleting the ruleset alone leaves master with no required check. | maintainer | immediately on any ordinary merge refused by the ruleset |
| GO-2 role apply | Observer fails to start or refuses its installation | Re-apply the role with the previous values (`v1.184.2`, reader `v0.295.1`, `required_jobs: [ci-green]`). The state file under `/var/lib/livespec-incident/` persists across applies. | plan owner (`ansible`) | before any arm; no live incident depends on it yet |
| GO-3 holds | A hold outlives its purpose, or the plan session dies mid-hold | Coordinator restores the recorded PRs (7.2) | coordinator | at the 45 min ceiling, or at once on "hold released" |
| GO-4 attempt 1 merge, **revert does not fire** | Principal down, callback missed, bind race lost (risk 2), or the action stuck `pending` | Server-side revert of attempt 1's COMPLETE landed patch through the forge (the GitHub revert of the merged PR, which is web-flow signed). Admin-merge it: the coordinator switches `enforce_admins` off and on, as at 17:47Z and 22:03Z on 2026-11-06. The red-green-replay range gate admits a web-flow-signed revert that restores the parent bytes (`docs/server-side-revert-exemption.md`); never use a skip variable. | plan owner opens the revert; coordinator merges it | trigger at the leaf failure + 5 min with no principal revert commit on master and no `completed` observer action. Target: merged before T(merge) + 12 min, so HEAD never shows a red `ci-green`. |
| GO-4, revert does not fire (consequence) | A7 is not proved | Stop the sequence. File the cause. Re-run phase 3 on a NEW item: this item's chain has a merged, failed attempt the observer did not act on. | plan owner | after rollback |
| GO-5 automatic revert | The inverse touches more than the incident patch (an expected-head compare-and-swap miss) | Diff the revert against the exact inverse of the landed patch. Restore any unrelated change through a normal PR cherry-pick. Never force-push master. | plan owner | at once, during the same hold |
| GO-6 attempts 2 and 3 merges | Their master run fails unexpectedly | The observer reverts them as for attempt 1. If it does not, use the GO-4 manual rollback, with the same trigger and the same owners. | as GO-4 | as GO-4 |
| GO-8 observer restart | The unit does not come back, or comes back without the bound registration | `systemctl start`. If the registration is gone, treat any following leaf failure with the GO-4 manual rollback. A12 is then not proved. | plan owner (`sudo` on vps) | within 1 min of the restart |
| GO-8 dispatcher restart | The repayment run is orphaned or double-dispatched | Cancel the duplicate through the server API (`POST /api/v1/runs/{id}/cancel`, `.ai/factory-restart-cancels-runs.md`) and keep the original | gmktec factory seat | on detection |
| GO-9 redelivery | It produces a second effect | No rollback is needed for the observer, because the action id is immutable. If a second revert commit appeared, revert that revert by a normal PR, and A12 fails. | plan owner | on detection |
| GO-10 repayment dispatch | A run fails, or produces a PR that does not merge | The ordinary failed-run decision (the drain-backlog skill). The item stays in repayment phases, and master is unaffected, because the repayment merges only on full checks. | factory seat and plan owner | normal cadence |
| GO-11 premature-closure probe | A probe CLOSES the item (mnny4v not serving) | Reopen the item through the ledger to its prior lifecycle status. Record the finding. Stop phase 7: A12 is unproved, so roll out mnny4v properly first. | plan owner | at once |
| Release freeze | A release slips out mid-sequence | Close or disarm each sibling's `bump-pin` PR for that tag. If attempt 1's defect shipped, cut a corrective release after the revert. Phases already run against `DT` stay valid, but re-run any later PR run that installed the new tag. | coordinator and plan owner | on detection |

---

## 8. Open questions and risks

1. **P0-1 is real new capability.** It means new code plus a maintainer-provisioned App and ruleset. The alternative
   is a carrier-map event that re-words or human-attests A7, A8 and A11. That is a change to the maintainer's own
   assertions and is theirs alone to make; note 001 §"Speed, risk and policy decisions" chose the scoped principal.
   Not recommended.
2. **Bind race (3.9).** The released design binds after the merge. A leaf that fails before the bind is ignored. The
   scripted bind plus the about 90 s margin of `check-metadata-batch` should hold. If P.3 shows that leg finishing
   faster, use the per-file-coverage plant.
3. **A10 depends on factory behaviour.** A worker that never notices B2 sends the item to acceptance rework. That is
   still inside the follow-up PR, but it adds a factory run.
4. **Replay of one-time events** (section 1). If the replayer refuses re-observation, a second incident run by the
   replayer roughly doubles phases 3 to 7.
5. **Reader validation of the reopen carrier under v0.295.1** (P0-8). INFERRED; rolling the reader removes the
   question.
6. Side observation, not blocking: master carries `EXPEDITED_INCIDENT_RESPONSE flag:` markers for closed items, for
   example `livespec_dev_tooling/_incident_ci_plan.py:3` (egy3ri), `_incident_observer_store.py:37-38` (47ij37,
   dln3ac) and `_green_token_evidence.py:50,207` (xluwqj). Closure rule 8 of note 001 says "all markers removed". The
   A9 marker check is scoped to ITEM, so this does not affect the sequence. The completeness reviewer will likely
   ask about it.
7. **The recovery principal's 15 s call timeout** (phase 3). The observer calls the installed principal through
   `ProcessInverseForge` (`livespec_dev_tooling/incident_inverse_service.py`, `timeout_seconds: int = 15`), so a
   slow inverse merge can time out while the forge operation is still in flight, and the observer cannot tell a late
   success from a failure. The principal makes a repeated `publish` safe: it resolves the recorded commit rather than
   minting a second revert (`incident_recovery_principal.py`, "EXACTLY ONE REVERT PER ACTION"). Phase-3 runbook line:

   "On a publish timeout, re-send publish with the same recorded commit and wait; a timeout is UNKNOWN, not a failed revert. Do not escalate it."

   Mitigation: attempt 1's planted defect stays small, so its inverse is a minimal revert well under the 15 s budget
   (coordinator ruling 2026-11-07 ~03:06Z).
