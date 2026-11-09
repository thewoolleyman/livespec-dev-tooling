# Second rehearsal incident: procedure to capture what the first exercise left partial

Research note for epic livespec-dev-tooling-bqnzcm. Written 2026-11-09 between about 23:00Z and 23:59Z, read-only. No
ledger, forge, host or service was written to draft it. This is the procedure. Nothing in it has been run.

Marking: **VERIFIED** means read in code on `origin/master` 36e39ec4, in a released tag, in the ledger or on the forge;
the source is given. **INFERRED** means derived from verified facts and not exercised.

Sources:

- the epic's 14-bullet Definition of Done, read from the ledger;
- the epic's comments, in particular the PLAN TICKs of 2026-11-09 20:37Z and 22:22Z, the 19:38Z RESUME HANDOFF and the
  15:28Z DESIGN DEVIATION;
- note 006 (the first exercise's procedure) and the session's assertion-to-proof map of 2026-11-09 ~23:00Z;
- the ledger records of wtsntu, 6xyc42, nofeol, thhgeg, fdquen, q6eyrr, ariayn, hlxbsv and fkd7sx;
- livespec-dev-tooling `origin/master` 36e39ec4, and releases v1.189.1 and v1.190.0;
- livespec-orchestrator-beads-fabro tags v0.309.2 to v0.311.1, and `~/.claude/plugins/installed_plugins.json`;
- `.ai/fabro-dispatch-diagnosis.md`, `.ai/independent-host-replay-identity.md` and `.ai/coordinator-duties.md`.

Item ids below drop the `livespec-dev-tooling-` prefix when they are this tenant's (`wtsntu` means
livespec-dev-tooling-wtsntu). `ITEM` is the rehearsal's new incident item. `e62ss6` is the first exercise's item, now
closed at chain generation 31.

---

## 0. Summary

1. **The first exercise left eight assertions partial or uncaptured:** A1, A2, A3, A6, A9, A12, A13 and A14 (section 1).
   e62ss6 is closed, so its probe windows have passed. A second incident on a new item is the only way to observe the
   missing behaviour live. The coordinator accepted that on 2026-11-09, and the plan Proof of Done capture waits for it.
2. **The rehearsal is one incident with three expedited attempts, one regression revert and one factory repayment**, the
   same skeleton as note 006. It adds four things that the first exercise never had:
   - a master that is RED for an unrelated reason when the incident starts (A1);
   - incident commits run without `--local`, plus one timeout deferral (A2, A13);
   - a merge-time refusal for missing focused evidence (A3);
   - a repayment that runs with no hand riders, followed by closure probes that refuse for the right reason (A9, A12).
3. **The incident is a real open defect, fkd7sx: the fleet `gh` failure classifier reads any 5xx digit run as a server
   error** (section 4). The defect, the planted coverage gap, the regression and the deferred-proof finding are all
   ordinary, realistic shapes inside one small module. The red master comes from a semantic merge conflict between
   two small, normal, tests-only pull requests that are green on their own. That is the commonest way a fleet master
   goes red with green pull-request CI.
4. **Eleven preconditions gate the start** (section 3). Eight are open work: wtsntu, 6xyc42, nofeol, thhgeg, fdquen,
   q6eyrr and iezdmk, plus a NEW carrier for A3 enforcement, which nothing provides today and nobody has filed. Two are
   a dev-tooling release and an orchestrator registration move, and the last is an owner hold on fkd7sx:
   - this project's orchestrator install reads v0.309.2, which lacks bd-ib-cxxmnm and bd-ib-iwksr3 (VERIFIED);
   - the observer serves v1.188.1, which lacks q6eyrr and thhgeg.
5. **Six assertion parts cannot be captured by a rehearsal, or only partly, or only with a host change no one has
   agreed to** (section 10):
   - a CI run in which GitHub never created a required leg (the live half of nofeol);
   - the "ambient environment" half of A6, unless the master runner set is given the flag;
   - the fleet-wide reading of A13;
   - a related regression surfacing on master rather than on another pull request (possible, but not planned);
   - a failure set with more than one failing leaf (A8), on the current gate classification;
   - re-observation of the manual reproduction itself (A3).
6. **Estimate:** 12 to 18 h of live work after the preconditions, of which the attended incident is 6 to 9 h. Master
   merges are held for about 4 h 30 m in five or six spells. The longest, H1, covers the deliberate red master and lasts
   60 to 90 min.

---

## 1. What the rehearsal must capture

The column "e62ss6" restates the assertion-to-proof map's verdict. The column "Rehearsal" names the observation this
procedure adds. Step numbers refer to section 6.

| # | e62ss6 | What the rehearsal adds | Steps |
|---|---|---|---|
| A1 | partial: master HEAD was never red | ITEM's first expedited commit and push are admitted while master HEAD's `ci-green` is a concluded failure, and in the same minute a normal push is refused by `check-master-ci-green` | T.4, 1.2-1.4 |
| A2 | partial: attempt 4 only; every gate-run used `--local`; no timeout | Every incident commit and push without `--local`. One expedited commit under CPU contention records at least one `deferred-timeout`. No `::: just` aggregate line, and no gates Job for the staged tree | 1.3, 1.4, 2.3 |
| A3 | proven for attempt 4; no enforcement | `/arm` refuses a head with no focused-evidence record, then refuses an incomplete record that has no operator disposition, then accepts once both are recorded | 1.6-1.8 |
| A4 | proven | Re-observed on three expedited PR runs under nofeol's stricter `ci-green` | 1.10, 2.6, 5.6 |
| A5 | proven | Re-observed: the marker sits beside each attempt's changed code and tests | 1.3 |
| A6 | partial: labels and markers only | Every master run of an incident merge runs the full graph with `incident-ci: selected nothing`. Optionally (6.4), one normal master run with both flags injected into the master runner set's job environment and both flags set as repository variables (wtsntu) | 1.11, 2.7, 5.8, 6.4 |
| A7 | proven | The first failing leaf of attempt 1's master run triggers the principal's revert, while the webhook is answered 2xx inside 10 s (q6eyrr) | 1.12 |
| A8 | proven, with caveats | Re-observed. The collect step runs on the sanctioned path, with no hand tree tag | 1.15-1.16, 2.1 |
| A9 | partial: marker removal needed riders; PR validation incomplete | A factory repayment with NO rider removes the marker (bd-ib-cxxmnm), runs full PR CI that nofeol's `ci-green` vouches for, and is dispatched with a scrubbed environment | 7.1-7.8 |
| A10 | proven, with caveats | The factory finds and fixes B2 in the repayment PR; `record-deferred-finding` records it; the reopen probe is refused, and the refusal is quoted from the CLI | 7.5-7.6 |
| A11 | proven (operator-triggered) | Re-observed, with a probe PR on a real regression input | 4.1-4.6 |
| A12 | partial: no (iv), no principal restart, no correct closure refusal | (iii) webhook redelivery; an observer restart DURING recovery, with the fence held and exactly one revert (q6eyrr, thhgeg); (iv) a gmktec dispatcher loop restart mid-repayment; `close-work-item`, the `accept:` valve and `reconcile-merged` each refuse on the repayment obligation, before the repayment merges and before its master CI is green; closure succeeds after | 1.13-1.14, 2.5, 7.3, 7.4, 7.9-7.11 |
| A13 | partial: no delegation, no 7.10, no label removal (G4) | Context crosses the gate-runner launcher without `--local`. Label removal on a real expedited PR re-runs CI with every member executed (6xyc42). A normal `just check` at an expedited head reuses no expedited report. `ci-green` refuses a missing required leg (see section 10 for the part a rehearsal cannot reach) | 1.3, 5.7, 6.2 |
| A14 | not captured | `read-history` and `context ITEM` show every attempt, PR, merge and revert SHA, CI run, omission, focused evidence, deferred spec debt, deferred finding and the repayment proof | 8.1 |

A1 to A14 are each re-observed, so the phase-8 record can cite this one incident for all fourteen on one build, with
e62ss6 as corroboration (section 8).

---

## 2. Lessons from the first exercise that change the procedure

Each item below was measured in the first exercise. The source is the epic comment or handoff named.

1. **The deferred-spec plant of note 006 §3.2 no longer reaches master.** Since oqpw6t, `check-targets.txt` classes 75
   gates `fast`. They include `check-heading-coverage`, `check-heading-coverage-debt-register`, `check-no-todo-registry`
   and `check-check-coverage-incremental` (VERIFIED, `check-targets.txt` at 36e39ec4). The incident hook runs every
   fast gate locally (`incident_local_gates.select_gates`), so a missing heading-coverage row is refused at commit.
   Members that are omitted on the PR AND slow locally are only `check-per-file-coverage` and `check-coverage`, so a
   plant that must pass the hook and the expedited PR and fail on master has to be a per-file coverage gap or a
   failing test (section 4.3). `check-coverage` is skipped by its own `if:` when per-file coverage fails, so the failure
   set will again hold one failing leaf; section 10 states this limit.
2. **Deferred spec work is a recorded debt, not a spec edit in the attempt.** The repayment screen holds a dispatch whose
   Definition-of-Done bullets the spec does not state (DESIGN DEVIATION, epic `01a1c0ed-2404`). So the incident's
   deferred spec work is "the spec does not yet state the rule". Its repayment is a propose-change plus a revise
   stating every bullet, merged before the repayment dispatch (6.4). It is not left for the screen to find.
3. **Read the identity from `read-current` before every authority call.** Never take it from a handoff. On 11-09, gen
   29's operation was `…#deferred-finding:01M70H7Z7P41A0A2GDVVVCPNWB` and not `…#repayment-active`, and `read-current`
   refused the latter with `identity-mismatch` (PLAN TICK `01a1c267`).
4. **Keep records out of the session scratchpad.** The 99fb14bc scratchpad, with its H4, arm4 and merge4 helpers and
   the query JSON, was deleted when that session ended (PLAN TICK `01a1c207`). Use the durable directory
   `~/.local/state/livespec-rehearsal-007/` and post every load-bearing JSON to ITEM as a comment.
5. **A replayer must publish detached and wait for its own `post.exit`.** Two replays lost their publish when codex
   ended its turn (19:38Z handoff, REPLAYS). Section 8 gives the two-turn shape.
6. **Every test module reaches 100% coverage on itself before any Red.** iwksr3's first Green was refused by one dead
   line in its own test module (PLAN TICK `01a1c207`). Run `pytest --cov` on the test module with the implementation
   applied before the Red commit. This applies to every hand lane in section 3, to P_a and P_b (section 4.2) and to the
   probe PR.
7. **Open every PR as `--draft --label do-not-merge` and assert `autoMergeRequest == null` before any reopen or
   ready.** #3854 auto-merged before its review fixes (11:44Z handoff). Release PR #3764 merged with `do-not-merge`
   because auto-merge was armed before the label (note 006 P.6). A release freeze is a draft release PR AND auto-merge
   disabled.
8. **Push the named branch.** The hook requires the local ref to equal `target_ref`, so `git push origin HEAD:refs/…`
   is refused (07:16Z handoff). Between commit and push, `commit-transition` advances the attempt's head (note 006
   3.3).
9. **A comment that reads as a hold holds the item at petri's screen** (`.ai/fabro-dispatch-diagnosis.md`). Word every
   wait as a wait. Use the word "hold" only for the owner hold on fkd7sx (P.2).
10. **Never rebase a factory PR you may need to resume.** Never treat a server-resumed run as fresh. Read its server
    log first (`.ai/fabro-dispatch-diagnosis.md`).

---

## 3. Preconditions: what must be merged, released and serving before T0

"Serving" means read from the serving component, not from git: the observer manifest's `release` and `reader_release`,
this project's `installed_plugins.json` entry, and the gmktec dispatcher's own loop record. A precondition is met only
when its column reads true on the serving component.

| # | Item | State, 2026-11-09 ~23:30Z (VERIFIED, ledger and forge) | Must be | Load-bearing for |
|---|---|---|---|---|
| C1 | **wtsntu**: master and factory follow-up gates refuse on an inherited flag | active (factory); no PR | merged; in `DT` | **A6** (the ambient-environment clause cannot hold without it); **A13** (a normal body under an inherited flag); the repayment run's gates (A9) |
| C2 | **6xyc42**: label events re-run CI | blocked; hand lane livespec-dev-tooling#3911 (additive part; the reusable-matrix half moved to hlxbsv) | merged (a workflow takes effect on merge) | **A13 G4**: label removal on a real expedited PR (5.7) |
| C3 | **nofeol**: `ci-green` passes a run with a never-created leg | ready; hand lane livespec-dev-tooling#3931; `approval:workflow-edit-additive` set 23:15Z | merged | **A9**: the repayment PR's `ci-green` vouches for every leg; **A4** non-regression (the omission path still passes); **A13** PR boundary |
| C4 | **q6eyrr**: the observer answers the webhook only after the principal finishes | active (factory, rework rider: the principal must run behind the fence) | merged; in `DT`; observer rolled to `DT` | **A7** (2xx inside 10 s while the revert still lands); **A12 (iii)** redelivery; **A12** observer restart during recovery with the fence held |
| C5 | **thhgeg**: the principal hard-codes `master` | ready; spec v173 revised (9de6ab8c) | merged; in `DT`; observer rolled; its own scratch-branch host proof captured BEFORE T0 | **A7** (moved bullet 2, by coordinator ruling) and **A12** (principal restart journaled once, H2 by ruling). The rehearsal leaves the target branch unset, so the principal targets `master` |
| C6 | **fdquen**: rollback-conflict never reaches the chain | active (factory) | merged; in `DT`, and in `ORCH` if its writer needs an orchestrator action; reader rolled | **A7** and **A11** by coordinator ruling. Its host bullet (a rehearsal overlap) is captured on thhgeg's scratch branch, NOT on master in this rehearsal |
| C7 | **iezdmk**: five authority clients carry different ceilings | active; livespec-dev-tooling#3929 merged 23:40:53Z as 5bdc3b9b; confirm at acceptance that the 3x-ceiling rider is met (ceiling at least 3x the slowest measured read) | accepted; in `DT` | No assertion. Risk: in the e62ss6 window the slowest reads were a 49 s reader pass and a 41 s `/provenance` read, against 45 s ceilings (19:38Z handoff). This rehearsal's chain will reach 25 to 35 generations. Without C7, stop at the first read over 35 s (P.4) |
| C8 | **NEW A3 enforcement carrier** (to be filed by the plan owner) | none: no code refuses a merge for missing focused evidence. `grep focused` finds no consumer in the observer, `incident-ci` or the orchestrator (VERIFIED) | filed, ratified if the tier screen asks, merged; in `DT`; observer rolled | **A3** enforcement (1.6 to 1.8). Recommended shape below |
| C9 | **Orchestrator `ORCH` ≥ v0.311.1** registered for livespec-dev-tooling AND for the gmktec factory's dev-tooling dispatch | project install reads 456712f1af12 = v0.309.2, which lacks bd-ib-cxxmnm (ca79256c5, 486722447) and bd-ib-iwksr3 (b26c3dc2) (VERIFIED with `git merge-base --is-ancestor`) | registered in both places; dispatcher loop restarted on it | **A9** (marker removal with no rider); **A12** (`reconcile-merged --pr` reaches the obligation); 5b0474c1d (stdin receipt, unreleased) rides along if cut |
| C10 | **One dev-tooling release `DT`** cut after C1 to C8 merge; observer role re-applied at `DT` with `incident_observer_reader_release: ORCH` | role default still `v1.188.1` and reader `v0.304.0` (VERIFIED, `ansible/roles/incident_observer/defaults/main.yml`) | serving | The single build identity of the phase-8 record. `incident-ci` installs `releases/latest`, so `DT` must be latest for the whole window |
| C11 | **fkd7sx is not dispatched** before T0 (section 4.1) | ready, factory route | owner hold recorded by the plan owner, with petri told | The incident itself. If it was fixed first, use the fallback in 4.6 |

**C8, recommended shape.** `/arm` refuses `incident-focused-evidence-absent` unless ITEM carries a focused-evidence record
whose tree equals the arm's head tree. It refuses `incident-focused-evidence-undisposed` when that record's outcome is
`incomplete` and no operator risk disposition for that record digest is recorded. Reasons:

- `/arm` is the last point before an expedited merge, because the expedited PR policy applies only while an arm stands.
  A refused arm leaves only the normal full policy, which needs no focused evidence.
- The refusal is immediate, so it costs no PR run.
- SPECIFICATION/spec.md:46 binds expedited merges to "the specific pre-merge obligations", and contracts.md §"Expedited
  incident execution" says "Incomplete focused evidence MUST remain recorded risk with an operator disposition". Refusing
  an arm that has neither the evidence nor the disposition is therefore conformance, not new policy (CLAUDE.md, "An
  unratified filter inside a check is conformance").

The disposition writer can be a `--risk-disposition TEXT` on `incident_focused_evidence_entry` that publishes on the same
channel.

**Not preconditions.**

- **ariayn** (the reconciler consults the observer) is replaced for this window by the reconciler pause in section 5.1.
- **hlxbsv** (the reusable-matrix omission): this repository's `ci.yml` does not call `reusable-check-matrix`.
- **zapgpu** (automatic collection): the manual `collect` path works (A8 on e62ss6).
- **3wcldx**: the coordinator's reading of A13 is pending (PLAN TICK `01a1c267`); see section 10.
- **osyzv6** gates the archive, not the rehearsal.

Each of them must still close or move out before the archive, as note 006 §8.3 and the proof map say.

**Sequencing.**

- C1 to C8 run in parallel, as hand lanes or through petri.
- C10 follows the last dev-tooling merge.
- C9's registration moves are the coordinator's to sequence. A project-scope `ensure-plugins` here moves this project's
  factory build too (CLAUDE.md, `.ai/factory-span-receiver.md`). Ask legacy-coordinator-agent; do not run it unasked.
- The release freeze (section 5.6) starts at the cut of `DT`.

---

## 4. The incident, the trigger and the plants

### 4.1 The incident: fkd7sx, a real defect

`livespec_dev_tooling/fleet/_read_failure.py` classifies `gh` stderr through `_STATUS_KINDS` (VERIFIED, lines 55 to 59
at 36e39ec4):

- `rate_limited`: `\b(?:HTTP\s*)?429\b|rate limit|…`
- `not_found`: `\b(?:HTTP\s*)?404\b|not found`
- `server_error`: `\b(?:HTTP\s*)?5\d{2}\b`

The `HTTP` prefix is optional, so a body such as `GraphQL: Could not resolve to an issue or pull request with the number
of 512.` reads as `server_error`, and `_gh_runner` and `_credential_preflight` retry it as a transient. fkd7sx records
this (filed 2026-11-09 by fleet-flaky-tests, the same class as orchestrator bd-ib-3d2c5y). It is small, real,
behavioural, has a production consequence (a permanent failure retried as a transient) and has a natural edge-case
family. It is a better rehearsal than a planted fiction.

**ITEM**, filed with `IA file-incident` at 1.1, carries this Definition of Done:

- **B1.** `classify_gh_failure` returns a kind other than `server_error` for `gh` stderr whose only 5xx digit run is not
  an HTTP status, such as `… with the number of 512.`
- **B1c (control).** It still returns `server_error` for every form in which `gh` relays a real HTTP 5xx:
  - `gh: Bad Gateway (HTTP 502)`;
  - `HTTP 503: Service Unavailable`;
  - git's `fatal: unable to access '<url>': The requested URL returned error: 502`, which `gh repo clone` and `gh pr
    checkout` pass through.
- **B2 (the deferred-proof plant, A10).** The same rule holds for the 429, 403 and 404 alternatives: a digit run that is
  not an HTTP status never yields `rate_limited`, the secondary-limit kind or `not_found`.

When ITEM is filed, mark fkd7sx `duplicates` ITEM and close it as superseded. Release its owner hold in the same act.

### 4.2 The trigger T: a red master from a semantic merge conflict

The red master must be unrelated to ITEM, real and reachable with no protection bypass. Two small, normal, tests-only
pull requests do this:

- **P_a** renames a shared test helper to a clearer name and updates every importer that exists at its base.
- **P_b** adds a missing test for existing behaviour, in a module P_a does not touch, and imports the helper by its old
  name.

Each PR's full CI is green on its own base. The ruleset requires only `ci-green`, with strict status checks off (VERIFIED
2026-11-09 in nofeol's context), so both rebase-merge cleanly. On master, `check-types` (pyright covers `tests/`) and the
suite fail. This is the fleet's commonest green-PR, red-master mechanism. Commit c7a761929 in the orchestrator
("repoint six heading-coverage rows at tests that exist") is that class.

- Both are `chore(tests)` changes with no product `.py`, so no Red-Green ritual applies. They still go through the
  normal hooks, a review and full PR CI.
- P.3 picks the helper. Its acceptance criteria: at least two importers; nothing under `livespec_dev_tooling/fleet/`, so
  T's failure can never be confused with ITEM's; P_b's test is worth keeping.
- **T is resolved through the normal red-master path:** a web-flow server-side revert of P_b (the GitHub revert of its
  merged PR). It touches no product `.py`, so the range gate has nothing to judge. Its PR CI is green, and it merges as
  any PR does. The master-health reconciler would ordinarily do this; it is paused (section 5.1), so the plan owner does
  it by hand. P_b re-lands correctly after the rehearsal.

### 4.3 The attempts and the plants

| Attempt | Content | Where it fails | Why only there |
|---|---|---|---|
| 1 | B1: the 5xx alternative requires the marker (`\bHTTP\s*5\d{2}\b`). The marker comment sits beside the regex and the new test. **Plant P1**: a defensive fast path for empty stderr, with no test, which returns the same kind the regex path returns. B2 is left alone; the 429, 403 and 404 alternatives keep the optional prefix. | master `check-per-file-coverage`, about 10 to 16 min into the run | Per-file coverage is slow locally (deferred by the hook) and omitted on the expedited PR. Focused evidence measures the touched file below 100% and records `coverage incomplete`. The operator records the risk disposition C8 demands (1.8). |
| 2 | Attempt 1 plus a test for P1's branch, built from the complete failure set of attempt 1's run. B1c's git form is still wrong. B2 is unchanged. | green on master | The responder's focused tests cover B1c's first two forms only. |
| R | The probe PR (phase 4) adds `test_a_git_returned_error_502_relayed_by_gh_is_a_server_error`. | the probe PR's `check-per-file-coverage` (the suite) | Before the incident the bare `502` matched, so the probe test passes on pre-incident code. It fails on attempt 2. This is a regression of behaviour that worked, so it takes the A11 revert path. |
| 3 | Attempt 2 plus a `returned error: 5\d{2}` alternative, plus the probe test. | green on master | |
| repay | Factory: removes the marker; adds a Red test for B2 (`… number of 429.` is not `rate_limited`, which fails on master); fixes B2. | none | B2 is wrong only by the Definition of Done. Every line is covered and no test fails, so neither the expedited PR nor master sees it. That is the A10 shape. |

Between attempt 2's merge and its revert, master carries a real, low-impact regression: a git 5xx relayed by `gh` is not
retried by the fleet `gh` runner. That window is about 30 to 60 min under hold H4. It is part of what makes the
rehearsal real.

### 4.4 Deferred spec work

The spec states none of B1, B1c or B2 today (INFERRED: fkd7sx references `## Cross-repo coordination automation
surface`, which predates the defect). The attempts edit no spec file. Record the debt at 1.9:

- the obligation is a spec statement of B1, B1c and B2;
- it is repaid by propose-change topic `a-gh-failure-status-needs-its-http-marker` and a `--only-topic` revise, merged at
  6.4 before the repayment dispatch.

That merge is also the normal master run that 6.4 uses for the A6 ambient probe.

### 4.5 Proving the plants offline (P.3)

Before T0, in a scratch worktree from master that is never pushed:

1. Apply P_a and P_b on their bases, then merge both. Require `just check-types` and the suite to fail on the combined
   tree, and each to pass alone.
2. Apply attempt 1. Require:
   - every fast gate passes;
   - `incident_focused_evidence`'s coverage reports `_read_failure.py` below 100%, on exactly P1's lines;
   - `just check-per-file-coverage` fails on P1 alone.
3. Apply attempt 2. Require the full `just check` to pass, and the probe test to fail on attempt 2 and pass on master's
   pre-incident code.
4. Apply attempt 3. Require the full check to pass with the probe test included.
5. Write B2's Red test. Require it to fail on attempt 3's tree.
6. Run `just check-file-lloc` on every touched file. Attempt 3 of e62ss6 failed that fast check on a 252-line file.

Post the five patch files and the measured results to ITEM's epic as one comment before T0. If master has moved under
the classifier, keep the shapes in 4.3 and re-derive the patches.

### 4.6 Fallback incident

If fkd7sx has been fixed before T0, use any open defect that meets all of these:

- small and behavioural;
- in a module with per-file coverage;
- has an edge-case family that gives a B2 the expedited fix can leave wrong while fully covered;
- has a pre-incident behaviour that a natural fix can break, which gives the regression R.

The 4.5 proof applies unchanged.

---

## 5. Operational constraints written into the procedure

### 5.1 Pause the master-health reconciler, and tell ci-runtime-and-cost first

The observer and the ordinary reconciler share no action ownership until ariayn's wiring lands. T's run and attempt 1's
run are each a red master that an ordinary reconciler pass would try to revert while the plan owner or the observer
already is. That is the double-revert hazard. The coordinator has no objection to the pause.

- **What there is to pause (VERIFIED at 36e39ec4).**
  - livespec-dev-tooling ships `reusable-master-health-reconcile.yml`, but no workflow in this repository calls it.
  - The callers found are livespec's `master-health-reconcile.yml` (it reconciles only livespec) and a reference in the
    orchestrator's `ci-root-uid.yml`.
- **At P.1,** re-read `gh workflow list -R thewoolleyman/livespec-dev-tooling`. If a `Master health reconcile` workflow
  exists by then, run `gh workflow disable` on it at T0 and `gh workflow enable` after the last hold. Record both on the
  epic.
- **The pause also covers hand actors.** Before T0, message the ci-runtime-and-cost seat (and legacy-coordinator-agent)
  the window, its holds and these rules. For livespec-dev-tooling master, between T0 and the repayment's green master
  run:
  - no master-lane cancel of any run. That covers the runs of P_a, P_b, the P_b revert, every incident attempt, every
    observer revert and the repayment, whatever the standing GO otherwise allows. A cancel of attempt 1's run destroys
    A8.
  - no failed-job re-run of any of those runs, by hand or by an infra re-run reconciler (khlrw3, cetyrq, ybnep5), except
    a job-creation outage the coordinator rules on. A re-run changes what `filter=latest` reports, and so the collected
    evidence.
  - no server-side revert of T by anyone but the plan owner.
- **When the window closes,** send "rehearsal window closed" to the same seats.

### 5.2 Dispatch only through petri

Every factory run goes through a ticket from the `petri-factory-on-gmktec` seat, including the repayment and any
precondition carrier routed to the factory. Never run `drive.py --action impl:` directly (`.ai/fabro-dispatch-diagnosis.md`).

### 5.3 The authority identity comes from `read-current`

- Before EVERY `IA` call, run `IA read-current --item ITEM` and build the call's identity arguments from its answer:
  - `attempt`, `owner`, `phase`, `operation` and `generation`;
  - after a `record-deferred-finding`, the operation reads `…#deferred-finding:<run>`.
- Keep the answer under `~/.local/state/livespec-rehearsal-007/gen-<N>.json`.
- `IA` is the registered build's `incident_authority.py`. Resolve it with `registered_plugin_root.py` after re-reading
  `installed_plugins.json`.
- Run IA calls under bash, because zsh does not word-split arrays.
- Build JSON arguments with `jq -cS`.

### 5.4 Replayers publish detached and wait for `post.exit`

- The phase-8 replayer launches its `post-plan-record` (and any `post-host-record`) as
  `setsid nohup sh -c '<post>; echo $? > <dir>/post.exit' >… 2>&1 </dev/null &`.
- It ends turn 1 without waiting.
- The briefing session waits for `post.exit`, then resumes the SAME codex session (`codex exec resume <id>`, same
  `env -u CLAUDE_CODE_SESSION_ID -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT` prefix).
- In turn 2 the replayer reads the exit code and the posted record itself.
- `.ai/independent-host-replay-identity.md` applies in full. In particular: the tag-ancestor rule against the
  auto-pulled primary, never masking `tmp/`, and re-running `reconcile-merged` from a normal shell when a pass died with
  its replayer.

### 5.5 Coverage before Red

Every hand lane in section 3, P_a, P_b and the probe PR run `pytest --cov` on their own test module, with the
implementation applied, and require 100% before the Red commit.

### 5.6 Release freeze and holds

- **The release freeze** runs from the cut of `DT` until the 8.2 replay posts: the release PR stays a draft, with
  auto-merge disabled and checked every 2 min by the coordinator. T's tests-only merges would otherwise ship nothing
  harmful, but attempt 2's regression must never ship.
- **Holds** follow note 006 §7.2, with one ruling asked of the coordinator: the 45-min ceiling is raised to 90 min for H1
  only, because H1 contains T's red period (section 9).
- **Records** go in the durable directory and on ITEM (lesson 4).

---

## 6. The procedure

Conventions follow note 006 §4. `[GO-n]` refers to section 7.

### Phase P: pre-flight (no live effect), T0 − 2 h to T0

- **P.1** Verify C1 to C11 on the serving components (section 3). Read:
  - the observer manifest's `release`, `reader_release` and `required_jobs`, with `sudo` read-only;
  - `installed_plugins.json`, and `registered_plugin_currency.py` here;
  - the gmktec dispatcher's build from its loop record;
  - `gh workflow list` (5.1);
  - the ruleset (only `ci-green` required, strict off, the recovery App the only bypass);
  - that `ci.yml` has no master `concurrency` stanza yet. If B' has landed, confirm that commits with the incident
    trailer get their own group;
  - at `ORCH`, the order of checks in each closure route (`close-work-item`, the `accept:` valve, `reconcile-merged`
    and `complete-incident`). Write down the refusal each must give in windows (a) and (b) of 7.4 and 7.9. The codes in
    those steps are INFERRED from v0.311.1's refusal names (`incident-obligation-outstanding`,
    `incident-repayment-pr-unmerged`, `incident-completion-outstanding`, `IncidentClosureRefusedError`), not run.
- **P.2** Record the owner hold on fkd7sx. Tell petri it is reserved for the rehearsal.
- **P.3** Run the offline plant proof (4.5) and post it.
- **P.4** Read timing. Make 7 timed `bd show` calls and one observer reader pass against a fresh chain, and project the
  reader time to gen 35. With C7 merged, the ceilings must exceed 3x the projection. Without C7, the stop rule is any
  read over 35 s.
- **P.5** Calibrate the timeout deferral for 2.3. In a scratch worktree, run the 75 fast targets through the normal
  parallel dispatcher under `systemd-run --user --scope -p CPUQuota=<Q>%`. Choose the largest Q at which 1 to 3 of the
  slowest fast gates exceed 60 s while `check-lint` and `check-format` stay under it. Note the gates. If
  `systemd-run --user` is unavailable, use a `cgcreate` scope with the same quota.
- **P.6** Confirm webhook delivery: `workflow_job` reaches the Funnel `/callback`, and recent deliveries answer 2xx or
  403 (a 403 on `queued` and `in_progress` is by design).
- **P.7** Read the observer's retained arm id. It becomes attempt 1's `expected_arm_id`.
- **P.8** Send the window notices (5.1). Get [GO-T] and the maintainer's consent to the deliberate red master.
- **P.9** Prepare P_a and P_b as draft PRs with `do-not-merge`, each with full PR CI green on its own base, reviewed and
  NOT merged. Pre-stage attempt 1's patch in `~/.local/state/livespec-rehearsal-007/`.

### Phase T: the trigger and the red master (A1), inside hold H1

- **T.1** [GO-3] Hold H1 starts: the coordinator disarms auto-merge on every open PR (note 006 §7.2).
- **T.2** [GO-T] Mark P_a ready and rebase-merge it, then P_b immediately after.
- **T.3** On P_b's master run, `check-types` fails a few minutes in, and `ci-green` concludes `failure` at the end (13 to
  17 min, measured range 12.4 to 16 min on uncontended runs). Do not cancel, re-run or revert it yet.
- **T.4** Once `ci-green` has CONCLUDED failure on master HEAD, run the A1 control:
  - in a scratch worktree, make a normal one-line docs commit on a scratch branch and push it;
  - require `check-master-ci-green` to refuse it, naming HEAD's failed `ci-green`;
  - record the time and output. Nothing reaches the forge.

### Phase 1: attempt 1 while master is red (A1, A2, A3, A5, A7, A8, A12 i to iii)

- **1.1** File ITEM with `IA file-incident`: B1, B1c and B2 (4.1), the open claim token, and the genesis declaring every
  path the three attempts and the repayment will touch in `original_paths`: `_read_failure.py`, its test module and the
  probe test. Mark fkd7sx `duplicates` ITEM.
- **1.2** Create the worktree with `just worktree-create incident/<ITEM>-attempt-1` and apply the pre-staged patch.
  Run `just check-file-lloc`.
- **1.3** **The expedited commit through the detached runner, without `--local`** (A1, A2, A5, A13):
  - Run `mise exec -- just gate-start -- env EXPEDITED_INCIDENT_RESPONSE=1 LIVESPEC_INCIDENT_AUTHORITY_QUERY=<gen query>
    LIVESPEC_INCIDENT_LOCAL_OPERATION=<distinct> mise exec -- git commit -F <msg>`. Pass the message file by path; `-F -`
    loses stdin under the runner. The message carries `Factory-Override: EXPEDITED_INCIDENT_RESPONSE flag: <ITEM>`.
  - Run a BACKGROUND `gate-wait`, then read the VERDICT line.
  - Capture:
    1. the gate-run record's `venue` and `venue_reason`;
    2. the hook output and the `record-local-gates` receipt: `expedited-local-partial`, 75 fast gates executed in
       parallel, each well under 60 s, and the deferred list with its reasons;
    3. zero `::: just` target lines in the gate-run output;
    4. `kubectl --kubeconfig /etc/ci-runner/gates.kubeconfig get jobs -n gates -l livespec.gate/tree-hash=<staged
       tree>`, which must be empty;
    5. `check-master-ci-green` deferred as `not applicable … requires green-master-ci`, while HEAD's `ci-green` is a
       concluded failure.
  - **Delegation control, the same minute:** `just gate-start -- just check` in the 1.2 scratch worktree with the
    flags unset. Require the selector to choose the cluster venue and a gates Job to appear for that tree. Then end it
    with `gate-wait`'s interrupt. The control shows the delegated venue is live, and that incident mode did not take it.
- **1.4** `commit-transition` head-advance, then the push through the runner, without `--local`, with the same captures
  (pre-push receipt). Push the named branch `git push origin incident/<ITEM>-attempt-1`.
- **1.5** The P_b revert:
  - The plan owner opens the web-flow revert of P_b (the GitHub "Revert" on the merged PR).
  - It merges on its own PR CI.
  - Its master run must be green before 1.10.
  - From the moment it merges, HEAD is pending, so other seats' pushes stop being refused.
- **1.6** Open a draft PR with `do-not-merge` from the attempt branch, and bind it (pr-bound). [GO-3 continues under H1,
  or opens H2 if H1 was released after 1.5's green.]
- **1.7** **A3 refusal 1:** `/arm` before any focused evidence is recorded. Require `incident-focused-evidence-absent`,
  naming the head tree.
- **1.8** **A3 refusal 2, then acceptance:**
  - Run `python -m livespec_dev_tooling.incident_focused_evidence_entry` with the manual reproduction:
    - procedure: `classify_gh_failure` on the 512 body and on `gh: Bad Gateway (HTTP 502)`;
    - expected: not `server_error`, then `server_error`;
    - observed: as measured;
    - `--verdict passed --related-test tests/livespec_dev_tooling/fleet/test_read_failure.py`.
  - The record reads `incomplete` (P1).
  - `/arm` again. Require `incident-focused-evidence-undisposed`.
  - Record the operator disposition: "P1 is a defensive fast path with no test; risk accepted for the incident; owed by
    attempt 2 or the repayment".
  - `/arm` a third time. Require acceptance with `expected_arm_id` from P.7.
- **1.9** Record the deferred spec debt (4.4) on ITEM, with the obligation named.
- **1.10** Add the label and block. GET until `merge_commit_sha` sits on the frozen base, then reopen once. The expedited
  PR run must show:
  - `incident-ci` in mode `expedited-repair`;
  - the six coverage and spec members `omitted-by-incident-policy`;
  - `ci-green`, with nofeol's leg reader, passing over legs that all exist and succeed (A4, A13 PR boundary, nofeol
    bullet 2).
- **1.11** [GO-4] Remove `do-not-merge`. Rebase-merge. The merge script binds within seconds (2 s poll), then runs `IA
  record-merge`. The master run logs `incident-ci: selected nothing (push event: the normal complete policy is the
  gate)` and runs every job (A6).
- **1.12** **A7:** `check-per-file-coverage` fails on P1 (about 10 to 16 min in). The delivery is answered 2xx in under
  10 s; read GitHub's delivery log for the status and duration (q6eyrr).
- **1.13** **Observer restart during recovery (A12, q6eyrr, thhgeg)** [GO-8]:
  - A script tails the observer journal. On the line recording the pending action for that delivery, it runs `sudo
    systemctl restart` on the observer unit at once, while the principal is still publishing.
  - Require all of these:
    - the unit is back within 1 min;
    - the observer resumes the action holding the repository fence;
    - exactly ONE revert commit by `thewoolleyman-incident-recovery[bot]` lands, with `git diff <attempt-1 merge>^
      <revert>` empty;
    - the recovery journal shows one publication;
    - `/arm` is free afterwards with no `/reconcile`.
  - If `/reconcile` was needed, use it and record that it was.
  - If no revert lands by leaf failure + 5 min, use note 006's GO-4 manual rollback and record A12 as not proven here.
- **1.14** **(iii)** [GO-9] Redeliver the failing-leaf delivery through the hooks deliveries API. Require a 2xx in under
  10 s, the body `existing immutable action; no duplicate effect`, and no second revert.
- **1.15** Do NOT cancel attempt 1's run. Wait for `completed`, then run the chain and collection steps, as the
  controller account through the installation:
  1. `IA reopen-regression` from `master-observation`;
  2. `IA record-revert-receipt`;
  3. `collect --revert-sha <sha> --expected-graph <file>` (note 006 3.12).
  The expected graph lists the registration's leaves by name, under hudte3's reading: every leaf among the required
  jobs.
- **1.16** Record any step taken outside the sanctioned path, for example a tree tag. The plan expects none.

### Phase 2: attempt 2, corrected from the complete evidence (A2 timeout, A8, A12 i)

- **2.1** Stage the repair: the test for P1's branch. Run `git write-tree`, then `propose-correction` with
  `--next-head-sha <base> --staged-tree <tree>` and attempt 2's reserved branch as `--target-ref`.
- **2.2** [GO-3] H2. Record the master base.
- **2.3** **Timeout deferral (A2):**
  - Commit through the runner, without `--local`, under `systemd-run --user --scope -p CPUQuota=<Q from P.5>%`.
  - Require at least one `deferred-timeout` result whose reason reads `local gate deadline reached under N-way
    concurrency`, with a duration near 60 s.
  - Require the commit to be admitted, because a timeout is a deferral.
  - Require every gate that completed to have passed.
  - If none timed out, repeat at the push with a lower Q. A timed-out gate that the expedited PR retains still runs
    there, so a deferral never hides a fast check.
- **2.4** Head-advance and push the named branch, without the quota.
- **2.5** Focused evidence; the record is complete this time. Draft PR, bind, `/arm` with `expected_arm_id` = attempt 1's
  arm. **(i)** [GO-8] Restart the observer unit after the arm and before the merge. The authenticated `/admitted` read
  answers 202 before and after.
- **2.6** Label, block and reopen once. Expedited PR run (A4).
- **2.7** [GO-6] Merge, bind and `record-merge`. Green master (A6). Before that run completes, run `IA enter-repayment
  --master-run <run>`. Require `incident-repayment-master-ci-outstanding`, and quote the CLI output verbatim on ITEM
  (A9 causal half).
- **2.8** Release H2.

### Phase 3: enter repayment on attempt 2

- **3.1** After attempt 2's run is green: `IA enter-repayment --master-run <run> --target-ref refs/heads/feat/<ITEM>`
  records `repayment-admission`. This is what k5teti's reopen applies to.

### Phase 4: the related regression on another PR (A11)

- **4.1** Open the draft probe PR with `do-not-merge`. It adds R's test. Its full normal CI fails exactly that test, in
  the suite leg.
- **4.2** Record the attribution: probe PR number, run id, failing job and test, and attempt 2's landed commit.
- **4.3** [GO-3] H3, then `IA reopen-regression` (surface `pull-request`) records phase `reverting` with `repayment_required:
  true`.
- **4.4** [GO-5] `POST /recover` with the reopened-chain receipt. The principal reverts attempt 2 exactly (patch-id equal
  to the inverse). Master stays green: the revert restores attempt 1's revert tree, which has no P1 and no B1.
- **4.5** **Fence (k5teti):**
  - `IA advance-repayment` on the superseded repayment refuses `incident-repayment-stale-observation`.
  - A closure probe (`close-work-item`) refuses `incident-repayment-superseded`.
  - Quote both CLI outputs on ITEM. These are CLI calls, not library calls (the proof map, item 13).
- **4.6** Keep the probe PR open. Its test moves into attempt 3, and the PR is closed unmerged after 5.8.

### Phase 5: attempt 3, label removal (A11, A13 G4)

- **5.1** `correct-attempt` on the same item. Stage attempt 3 (4.3), including the probe test.
- **5.2 to 5.5** Commit and push through the runner, without `--local`. Focused evidence (complete). Draft PR, bind,
  [GO-3] H4, `/arm`.
- **5.6** Label, block and reopen once. Expedited PR run (A4).
- **5.7** **G4 (6xyc42):**
  - Remove the `expedited-incident-response` label. The incident-label workflow cancels or re-runs CI on the head.
    Require the new run's `ci-green` to report every member EXECUTED, with the omission step skipped.
  - Then re-add the label, and require the expedited aggregate to come back on the same head.
  - If the label change invalidated the arm (INFERRED: "head and mode changes MUST invalidate stale verdicts"), re-arm
    with `expected_arm_id` = the invalidated arm, and record that.
- **5.8** [GO-6] Merge, bind and `record-merge`. Green master (A6). Close the probe PR unmerged.
- **5.9** Release H4.

### Phase 6: normal-validation probes and the deferred spec debt (A13, A6)

- **6.1** Re-enter repayment: `IA enter-repayment --master-run <attempt-3 green run> --target-ref
  refs/heads/feat/<ITEM>`.
- **6.2** **A13, step 7.10:** in a clean worktree at attempt 3's merged head, with both flags unset, run `just gate-start
  -- just check` without `--local`. Require:
  - the delegated venue;
  - every aggregate member executed, with per-file coverage running in full (about 10 min or more, not a cache hit);
  - no `expedited-local-partial` report read or accepted.
  Record the verdict whatever it is. The point is that nothing expedited is reused.
- **6.3** **A13, the wrapper boundary, normal half:** start from a shell with both flags unset. Run `env | grep -c
  EXPEDITED` through `with-livespec-env.sh` and require 0. The wrapper adds nothing; it was measured on 11-07 to pass
  both flags through when they are set.
- **6.4** **The spec debt and the A6 ambient probe:**
  1. File the propose-change in 4.4, then revise it `--only-topic` as the next free version. The plan claims the slot
     from the coordinator's revise queue.
  2. Optional [GO-A6]. Before its merge, inject both flags into the job environment of the
     `livespec-dev-master-k3s` runner set, which serves only livespec-dev-tooling master pushes (VERIFIED,
     `CI_RUNNER_LABELS_MASTER`):
     - `EXPEDITED_INCIDENT_RESPONSE=1`;
     - `EXPEDITED_INCIDENT_RESPONSE_REVERT=yes-please`, a deliberately malformed value.
     Inject them through a dedicated hook-pod-template revision referenced only by that set's values. Also set both as
     repository variables. Verify the mounted ConfigMap by its content sha, not the disk copy (CLAUDE.md, "Refreshing
     the disk copy…").
  3. [GO-3] H5: merge the revise. Its master run must run the complete normal graph green, with `incident-ci: selected
     nothing`.
  4. Remove the injection and the variables at once, and read both back.
  - **Rollback:** if the run fails because of the flags, that is wtsntu failing. Remove the injection, record the
    failure, and re-run the run's failed jobs under a coordinator ruling.
  - If GO-A6 is not given, merge the revise normally, and see section 10 for the clause.

### Phase 7: the factory repayment with no riders, closure probes, closure (A9, A10, A12)

- **7.0** Gate: `ORCH` is serving at gmktec for dev-tooling (C9). Read it from the dispatcher's loop record; a handoff
  does not count. The spec revise from 6.4 is merged.
- **7.1** `IA advance-repayment --to-phase repayment-ready --admission-complete` once admission leaves the item `ready`.
- **7.2** [GO-10] Ask petri for the repayment ticket.
  - **No rider of any kind** by the plan owner or the coordinator on ITEM from here until its merge. That covers REPAYMENT,
    RESTORE and SEED riders.
  - Capture the dispatch environment with `fabro dump` of the run, or the dispatcher's `scrub_incident_flags` record.
    Require neither flag present.
  - When the claim leaves ITEM `active` with assignee `fabro`, run `IA advance-repayment --to-phase repayment-active`.
- **7.3** **(iv)** [GO-8] While the run is active, ask the petri seat to restart the gmktec dispatcher loop for
  livespec-dev-tooling. Require:
  - the run and its claim survive;
  - there is no second dispatch;
  - the server log shows no resume that would make the run look fresh.
  Use `fabro logs … | grep -E 'Resuming Petri run|fencing a recorded sandbox'`.
- **7.4** **Closure probes, window (a): the repayment PR is not yet merged** [GO-11]. Run each with `ORCH` serving, and
  quote each reply verbatim on ITEM:
  - `dispatcher.py close-work-item` (or the close operation) on ITEM must refuse with `IncidentClosureRefusedError`,
    exit 5, naming the outstanding repayment obligation;
  - `drive.py --action accept:<ITEM>` must refuse with `incident-obligation-outstanding`;
  - `dispatcher.py reconcile-merged --item <ITEM> --pr <repayment PR>` must refuse on the unmerged repayment PR
    (`incident-repayment-pr-unmerged`).

  **A refusal on a lifecycle or carrier precondition does not count:** `incident-carrier-unbound`,
  `incident-repayment-carrier-mismatch`, or "item not in acceptance". e62ss6's only probe was that kind. If a route
  refuses that way, record it, and probe it again in window (b), where its precondition holds.
- **7.5** The factory run adds a Red test for B2 that fails on master and fixes it in the same PR, with the marker
  removed. Do not pre-record the finding. If the worker misses B2, acceptance grades the cumulative Definition of Done
  and sends rework into the same PR, which still meets A10.
- **7.6** When the run reports the B2 finding:
  - `IA record-deferred-finding`;
  - then `IA reopen-regression` on that finding. Require `incident-finding-deferred-proof-only`, exit 78, quoted.
  - Re-read the identity: the operation now ends `#deferred-finding:<run>` (lesson 3).
- **7.7** The repayment PR's normal CI runs every member. nofeol's `ci-green` must list every leg present and succeeded.
  `check-per-file-coverage` must run in full on the PR head (A9, A13 cache half).
- **7.8** The repayment merges on full checks. `git grep 'EXPEDITED_INCIDENT_RESPONSE flag: <ITEM>'` on master finds
  nothing, and no rider exists (A9).
- **7.9** **Closure probes, window (b): merged, master run not yet green.** That is 13 to 16 min, so script it.
  - `reconcile-merged --item <ITEM> --pr <repayment PR>` now selects the PR (iwksr3), reaches the completion valve and
    must withdraw and park, naming the repayment master-CI obligation.
  - `accept:` and `close-work-item` must refuse as in 7.4.
  - `IA complete-incident --master-run <in-progress run>` must refuse with `incident-completion-outstanding`.
- **7.10** After the repayment's master run is green, closure succeeds:
  1. the coordinator runs `reconcile-merged --item <ITEM> --pr <n>`;
  2. the plan runs `IA bind-repayment-acceptance --pr <n>`, naming the `repayment-<24hex>` attempt owned by `fabro`;
  3. the plan runs `IA complete-incident --master-run <id> --completion-json <attestation>`, which records `closed` with
     `outstanding []`.
  Then the ledger regrade.
- **7.11** Re-enable any reconciler disabled in 5.1. Send "rehearsal window closed".

### Phase 8: capture, replay, review

- **8.1** A14: `IA read-history --item <ITEM>` and `/livespec-orchestrator-beads-fabro:context <ITEM> --json`. Check that
  the following are reachable from ITEM alone, and record any that are not:
  - every attempt;
  - the PR, merge and revert SHAs;
  - the master run ids;
  - the expedited runs' omission lists;
  - the focused evidence and its disposition;
  - the deferred spec debt and its repaying revise;
  - the deferred finding;
  - the repayment PR and its proof.
- **8.2** Before the capture, record the phase-8 carrier-map scope event. It drops the moved work, adds C8 and the
  carriers the proof map names, and is the event the capture and the replay must both postdate (note 006 §1).
- **8.3** Capture one `host_captured` record with all 14 bullets, byte for byte, built on `livespec-dev-tooling DT`, with
  `ORCH` second. The steps cite ITEM for every assertion and e62ss6 as corroboration.
- **8.4** The independent replay follows 5.4. The replayer re-runs:
  - `gh run rerun` of the retained expedited and probe runs;
  - `read-current` and `read-history`;
  - the revert-tree diffs;
  - the focused tests at the recorded heads;
  - 6.2 at the recorded head.
  It re-reads the delivery log, the observer journal extract and the quoted refusals. It posts ONE `verified` record.
- **8.5** Completeness review, then archive preconditions (note 006 8.3).

---

## 7. Steps that need GO

| GO | Step | Why | Who |
|---|---|---|---|
| GO-T | T.2: merge P_a and P_b knowing master goes red | A deliberate red master: other seats' pushes are refused from T.3 until 1.5 merges (about 30 to 60 min) | coordinator GO plus maintainer consent |
| GO-3 | Holds H1 to H5 (section 9) | Holds other people's merges; H1 up to 90 min | coordinator |
| GO-4 | 1.11: merge attempt 1 knowing P1 fails a master leaf | An incident merge that is meant to be reverted | coordinator, under GO-T's consent |
| GO-5 | 1.13 and 4.4: principal reverts on master | Unchecked writes by the recovery App | coordinator (covered by the GO-1 consent of note 006) |
| GO-6 | 2.7 and 5.8: merges on reduced PR checks | As the policy intends | coordinator |
| GO-8 | 1.13 and 2.5: observer restarts; 7.3: dispatcher loop restart | Host and factory mutation during live work | coordinator; 7.3 executed by the petri seat |
| GO-9 | 1.14: webhook redelivery | Re-sends a signed event to our own observer | coordinator |
| GO-10 | 7.2: repayment dispatch | Factory capacity | coordinator, through petri |
| GO-11 | 7.4 and 7.9: closure probes | Would close ITEM if `ORCH` were not serving; run only after P.1 confirms C9 | plan owner |
| GO-A6 | 6.4: flags injected into the master runner set and repository variables | A CI-node change that every livespec-dev-tooling master run in the window inherits | coordinator plus the CI-node owning seat; maintainer if the owner asks |

The P.5 CPU quota, the P.3 scratch worktree and the drafts with `do-not-merge` need no GO.

---

## 8. Phase-8 record notes

- **Build.** `release_tag` is `DT`, a git tag of this repository. List the observer at `DT` (reader `ORCH`),
  `incident-ci`'s `releases/latest` (which is `DT` under the freeze), the operator authority at `ORCH`, and the gmktec
  registration at `ORCH`. If any part ran another build, name it. e62ss6's record had to split the build four ways; this
  rehearsal is designed so that it need not.
- **What the replay re-executes, and what it re-reads.** As in note 006 §1. Say in the steps that the one-time events
  (the red master, the revert, the restarts, the closure windows) are re-read from the immutable record:
  - the forge's job and commit timestamps;
  - the delivery log;
  - the observer journal extract posted on ITEM;
  - the quoted CLI refusals.
- **State the limits in the record** (section 10), so the replayer grades what the record claims.

---

## 9. Window, holds and estimate

Measured inputs from note 006 §6 and e62ss6:

- master run: 12.4 to 16 min;
- expedited PR run: about 4.3 min plus reader time;
- normal PR CI: 15 to 46 min;
- arm with a frozen base: about 20 min;
- factory repayment: 1.5 to 4 h.

| Phase | Work | Duration | Hold |
|---|---|---|---|
| C1-C11 | Preconditions, in parallel | not estimable; three factory items, three hand lanes, one new carrier, two releases | none |
| P | Pre-flight, offline plant proof, timeout calibration, P_a and P_b PR CI | 2 to 3 h, before T0 | none |
| T | Merges, T's run to concluded failure, A1 control | 0.3 to 0.5 h | **H1** starts |
| 1 | ITEM, attempt 1 commit and push, the P_b revert's PR CI and master run, A3 refusals, arm, PR run, merge, revert, restart, redelivery, run completion, collect | 1.5 to 2 h | H1 up to 90 min: T.1 to the P_b revert's green, then H2 from 1.6 to the revert's run green (about 45 min) |
| 2 | Attempt 2 with the timeout deferral | 0.75 to 1 h | H2 continues, or H2' (about 25 min) |
| 3-4 | Repayment entry; probe PR CI (outside any hold), reopen, revert | 0.75 to 1.25 h | H3, about 20 min |
| 5 | Attempt 3 with G4 (a full PR CI inside the hold) | 1.25 to 2 h | H4, 60 to 90 min |
| 6 | 7.10 probe; spec propose-change and revise; optional A6 injection | 1 to 2 h | H5, about 25 min |
| 7 | Repayment, restart, probes, closure | 2.5 to 5.5 h | none |
| 8 | Capture, replay, review | 3 to 3.5 h | none |
| **Total** | after the preconditions, P to 8 | **12 to 18 h** | about 4 h 30 m of holds |

The release freeze runs from the cut of `DT` to 8.4.

Rollback for each outward-facing step follows note 006 §7.4, with these additions:

- **GO-T, the P_b revert does not merge** (for example, its PR CI flakes). Under coordinator-duties §2, give the flake
  its in-place test retry and file a root fix; never re-run the job. While it waits, master stays red, and only expedited
  commits move. If it is not merged by T.3 + 75 min, ask the coordinator to admin-merge the web-flow revert, as on
  2026-11-06. It touches no product `.py`.
- **1.13, the restart loses the recovery.** Use note 006's GO-4 manual rollback (a server-side revert of attempt 1's
  complete landed patch), then `/reconcile` the action. Record A12's restart half as not proven, and cite thhgeg's
  scratch-branch H2 record.
- **GO-A6, the injection leaks to another set,** or the hook-pod-template revision is shared. Remove it at once, and
  verify by content sha that every set references its previous revision.

---

## 10. Assertions a rehearsal cannot capture, or captures only partly

1. **nofeol's live half: a run in which GitHub never created a required leg.** Nothing can induce that on demand:
   - it needs a forge-side job-creation failure, the 2026-11-09 outage class;
   - editing `ci.yml` on a PR to drop a leg also changes what nofeol's reader derives from that same checkout, so the
     run passes.
   The rehearsal shows the other side: every expedited run passes the stricter `ci-green` (1.10, nofeol bullet 2), and
   the repayment's `ci-green` lists every leg (7.7). The never-created observation must come from nofeol's own host
   record, taken on a real outage run or by its replay over the recorded run 42673814418's job set. State this in the
   A13 proof.
2. **A6's "ambient environment".** No workflow maps a repository variable or the runner's environment into a master job.
   Every `ci.yml` job runs in a `container:`, whose environment comes from the hook pod template. Setting repository
   variables proves only that no path exists. The live clause is reachable only through 6.4's runner-set injection, a
   CI-node change behind GO-A6. Without it, A6's ambient clause rests on wtsntu's factory tests, plus a coordinator
   ruling that this suffices.
3. **A13's "installed fleet tooling", read fleet-wide.** A livespec-dev-tooling incident cannot show it. Measured on
   11-09: driver-codex, driver-pi and runtime have 0 fast gates, and members with no `check-targets.txt` run no gates.
   Either the coordinator reads A13 as "the installed boundaries of this repository", or 3wcldx stays load-bearing
   (PLAN TICK `01a1c267`).
4. **A11 "observed on master".** The rehearsal's regression surfaces on another PR, as e62ss6's did. A master-surface
   regression needs a second planted red after a green attempt, with another hold. That is possible, but not planned,
   because the DoD's "on master or another PR" is satisfied by either surface.
5. **A8's "complete failure evidence" across several failing leaves.** On the current build, the only members that pass
   both the hook and the expedited PR are the two coverage jobs, and `check-coverage` is skipped when per-file coverage
   fails (lesson 1). So the failure set again holds one failing leaf, and its completeness is shown by retaining the run
   to completion and collecting every job's conclusion, not by a second failing leaf.
6. **A3's manual reproduction** is a human act. The replay can re-perform the procedure and read the record, but cannot
   re-observe the original act.
