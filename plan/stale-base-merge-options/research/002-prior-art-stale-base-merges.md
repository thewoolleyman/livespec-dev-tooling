# 002 — Prior art: up-to-date branches, merge queues, merge trains and stale-base merges

Written 2026-11-12 ~18:3xZ by the plan seat of `stale-base-merge-options` (epic livespec-dev-tooling-xowhol). Sources were
read directly, plus a `--status all` scan of four ledger tenants (livespec-dev-tooling, livespec,
livespec-orchestrator-beads-fabro, livespec-overseer). The scan's limits are listed in §"What was not read".

**How quotes are marked.** A passage in quotation marks attributed to "the maintainer" is the maintainer's own words as an
agent record quoted them. Every other description of a maintainer decision is marked **(paraphrase)**: the record states
the decision without quoting the maintainer. The ledger's `author` field cannot tell these apart, because it reads "Chad
Woolley" or "thewoolleyman" on every record.

## The short version

- The fleet has decided this question four times. It went from **`strict` required** (May) to **`strict` off and no merge
  queue** (June). It went on to **a merge queue** in one repository (August, never carried out) and then to
  **self-healing instead** (October).
- Each decision accepted the same failure on purpose: two pull requests, each green on an older base, break master
  together. Seven instances are on record, today included:
  - overseer-yo7m (2026-08-21);
  - overseer-6s3pk6 / overseer-mws8 (PLR0915);
  - dw7dzd (PR 2452 vs zdqnr2);
  - dfixhe (PR 2506 vs 2504);
  - ggoyiq (an LLOC ceiling);
  - livespec-dev-tooling#4224 (2026-11-12 ~01:15Z);
  - livespec-dev-tooling#4339 (2026-11-12 16:09Z).

  Note 003 M4 bounds the unrecorded ones.
- The October decision, the master-health reconciler, is ratified (livespec v224) and partly built. It runs in ONE
  repository (livespec). It does not run in livespec-dev-tooling or the orchestrator, which carried 65% of fleet merges
  over 2026-10-15..11-12 (note 003, M1).
- GitHub's merge queue is unavailable while the repositories are owned by a personal account. The maintainer said so on
  2026-11-12, twice, in capitals.
- **Facts recorded beside that exclusion, not a recommendation.**
  - GitHub documents the merge queue as available to PUBLIC repositories owned by an ORGANIZATION; only private
    organization repositories need Enterprise Cloud. All 10 fleet repositories are public.
  - Moving them into an organization has costs:
    - repository URLs, which GitHub redirects;
    - plugin marketplace names, which must be re-registered on every host;
    - a new org-owned GitHub App, because the fleet App is private and installs only on its owner's account;
    - re-registering the ARC runners;
    - re-projecting secrets;
    - the GHCR image namespace.

  Note 004 measures these.
- Only paraphrases survive for the June, August and October rulings. The maintainer's own words are recorded only from
  2026-10-14 on (the self-healing statement) and for the two 2026-11-12 merge-queue statements.

## Timeline

### 2026-05: `strict` required, and kept satisfied by a bot

- **2026-05-10, livespec `livespec-x0x`** (closed). `auto-update-branches.yml` left pull requests stuck BEHIND. It was
  fixed with cron and `workflow_run` triggers (af76e696). The agent-written description says "personal-account repo (no
  GitHub Merge Queue available; that's an org-only feature)". `livespec-abl` the same day is the companion
  auto-enable-merge (`--auto --rebase`).
- **2026-05-24, livespec `livespec-6du`** (closed). The update-branch pushes used `GITHUB_TOKEN`, so CI never ran on them,
  and "master's strict required_status_checks leaves the PR permanently BLOCKED". It was fixed with an App token
  (2409ccfb).
- **2026-05-29, livespec spec v096**
  (`SPECIFICATION/history/v096/proposed_changes/ci-merge-gate-branch-protection.md:31`). The first merge-gate rule
  MANDATED `strict`: branch protection "MUST require branches be up to date before merging".
- **2026-06-11/12, dev-tooling `livespec-dev-tooling-b6y`** (closed). The fleet copy of `auto-update-branches.yml` was
  propagated "under strict protection", using GraphQL `updatePullRequestBranch(REBASE)`, because the REST update-branch
  endpoint makes merge commits.

### 2026-06-22: `strict` off fleet-wide; no merge queue, no auto-rebase driver (livespec v126-v128)

- livespec `SPECIFICATION/history/v126/proposed_changes/merge-gate-drop-strict.md` and `-revision.md` (commits 27405002,
  53e5edd6, 39c33ac5; livespec PR #521). The revision reads "Maintainer has decided the GitHub strict
  (require-branches-up-to-date) branch-protection setting must be OFF family-wide" **(paraphrase)**.
- The reasons it gives:
  1. Under `gh pr merge --auto`, `strict` makes GitHub MERGE master into a behind branch. That breaks
     `required_linear_history` and buries the Red-Green-Replay trailers under a trailerless tip.
  2. Rebase-merge already replays every pull request onto the current tip, "so `strict` adds no correctness guarantee".
  3. The one case `strict` catches, a semantic conflict with the newer tip, "is accepted and caught by CI on `master`
     after the merge".
  4. It rejects a merge queue ("GitHub merge queues are organization-only") and "a hand-rolled serialized auto-rebase
     driver", which "would trade robust per-PR `gh pr merge --auto` ... for a fragile central loop that can orphan,
     mis-order, or wedge PRs".
- v128 retired `auto-update-branches.yml`: "strict=false + auto-enable-merge rebase-merge-on-current-tip + post-merge CI
  is the robust replacement".
- That text is today's livespec `SPECIFICATION/non-functional-requirements.md` §"CI as a merge gate (branch protection)",
  lines 1320-1322.
- Enforcement landed in dev-tooling the same day:
  - dev-tooling spec v016 `branch-protection-strict-off.md`;
  - e5cb8f44a, the `strict_enabled` failure in `branch_protection_alignment`;
  - f0badc9e1, the fleet row that flags `strict`;
  - 2e896ff57, wire-fleet-member's protection PUT with `"strict": False`. That is now
    `livespec_dev_tooling/fleet/_reconcile.py:222`, with the row check at `livespec_dev_tooling/fleet/_rows_github.py:224`;
  - a5fa4b0be, which removed the updater workflow.

  The ruleset half is `livespec_dev_tooling/checks/_branch_protection_rulesets.py`.
- **Live state, read 2026-11-12 ~18:2xZ.** On livespec, livespec-dev-tooling, livespec-orchestrator-beads-fabro and
  livespec-overseer, the master ruleset carries `required_status_checks` with `strict_required_status_checks_policy:
  false`, plus `required_linear_history`, `non_fast_forward` and `deletion`. The repositories have
  `allow_auto_merge: true`, `allow_update_branch: false`, rebase-merge only, and `owner.type: User`.

### 2026-07: the `merge_group` trigger removed

- livespec `livespec-3lev.5` and dev-tooling `ci.yml` (42f6a194a; comment now at `.github/workflows/ci.yml:93-98`) dropped
  the dead `merge_group` trigger, because "no merge queue is configured ... Re-add it WITH hosted routing only if a merge
  queue is adopted".
- The same comment is in the orchestrator's `ci.yml:57-60` and the overseer's `ci.yml:116-121`.

### 2026-08: the overseer incidents, and a merge queue chosen but never enabled

- **2026-08-05, livespec `livespec-h22nve`** (agent notes). "master protection has strict=false ... That is exactly why
  livespec PR 1960 could carry green checks dated 2026-08-03 against a master that had since moved." Turning `strict` on
  "would force a rebase and a fresh full CI run on every PR"; "NOT proposed here".
- **2026-08-21, overseer `overseer-yo7m`.** Two pull requests merged 87 s apart (7ee2962 x 590ac9d) and turned master red
  for about 70 minutes. The record calls it a "semantic merge conflict". It was cleared by the server-side revert PR 1446.
  `overseer-hgq4wi.33` was filed the same day: "Nothing ever tests the MERGED tree: no merge queue and no base-move
  re-test". It names (a) a merge queue plus `merge_group` and (b) base-move re-testing.
- **2026-08-22, `overseer-hgq4wi.33` comments** (agent analysis).
  - 17:53Z: in a 100-merge sample, the median substantive gap was 304 s against a ~290 s suite, and 23% of gaps were
    90 s or less.
  - 18:59Z: it names (c) `strict=true` and recommends rejecting it: "the update-branch treadmill ... (c) costs more than
    (a) and delivers less".
  - A second instance is in `overseer-6s3pk6` / `overseer-mws8`: a PLR0915 statement-budget red from two pull requests
    "each green against an older master, red together".
- **2026-08-23 04:01Z, `overseer-hgq4wi.33`.** "MAINTAINER DECISION RECORDED ... CHOSEN: REMEDY (a) — ENABLE A GITHUB
  MERGE QUEUE. REJECTED: remedy (b)." The record calls itself "verbatim in substance" **(paraphrase)**. The successor is
  `overseer-tdfe.22`. The queue was never enabled; the account cannot have one.

### 2026-10-14/15: self-healing instead (plan red-master-self-healing, epic livespec-dev-tooling-zcp5vb)

- **The maintainer's statement** (charter `plan/red-master-self-healing/research/001-charter-red-master-self-healing.md`,
  lines 3-5): "Yes, I like the self-healing" ... "it should be: if progress is being made, but still with a hard cap on
  it (for example, 2 hours). After that, a revert is done unconditionally, as long as it can be proven (or likely
  expected) that the revert will actually fix the failure." ... "Okay, this sounds like a good approach. Make a detailed
  plan for it with a definition of done."
- **Rulings** (same charter, §"Maintainer rulings (conversation, 2026-10-14)") **(paraphrase)**:
  - "Repositories are PERSONAL: GitHub merge queue is unavailable and is not a goal."
  - "`strict` plus an eager rebase-updater: REJECTED — up to N² CI runs per merge burst kills factory throughput."
  - "A serialized merge train: REJECTED — loses parallelism, and deadlocks exactly when master is broken."
  - "Parallel merges and today's CI volume stay. The remedy is to make red master SELF-HEALING."
  - Non-goals: "No merge queue; no `strict`; no serialized merge train; no extra CI on the happy path."
- **Measurements in that charter**, taken 2026-10-14:
  - orchestrator master CI: median 6.4 min, p90 10.5 min (n=26);
  - merges in 24 h: orchestrator 46 (peak 6/h), dev-tooling 14, overseer 20, livespec 4.

  Since then, dev-tooling went from 14 to 54.2 merges a day (about fourfold) and the orchestrator from 46 to 60.3
  (about 1.3x). The 10-14 figures are a single 24-hour snapshot, and the newer ones are 28-day means (note 003, M1).
- **Ratification.** livespec v224 (livespec PR #2841, 6b2cb040, 2026-10-15) ratified the revert-by-default reconciler with
  a progress-bounded fix-forward claim and a 2-hour hard cap. It is now livespec NFR lines 1324-1334, which end: "This
  rule introduces no merge queue, no `strict`, no serialized merge train, and no additional CI on the happy path."
- **2026-10-20.** `overseer-tdfe.22` was closed as superseded by zcp5vb: "The maintainer ruled on 2026-10-14 that a merge
  queue is OUT (repos are personal)" **(paraphrase)**.

### 2026-10 to 2026-11: further instances, and the reconciler's partial rollout

- Semantic-conflict instances in agent records:
  - `dw7dzd` (PR 2452 vs zdqnr2);
  - `dfixhe` 10-16 (PR 2506 vs 2504);
  - `ggoyiq` 10-22 (an LLOC ceiling crossed by two branches together);
  - livespec-dev-tooling#4224 on 2026-11-12 ~01:15Z (merged on a head built before the #4177 revert).
- Where the reconciler stands:
  - The reusable workflow landed 2026-10-31 (c6c424818). The incident-observer step landed 2026-11-10 (bdec0e63b,
    d26176749).
  - livespec carries the shim (`master-health-reconcile.yml`, 90dfef1e, 2026-10-31). It is the only fleet member that
    does.
  - livespec-dev-tooling: `livespec-dev-tooling-okij46` "Arm the master-health reconciler in livespec-dev-tooling" is
    BLOCKED. Its proofs PR livespec-dev-tooling#4076 is a held draft that "lands only when option A lands (or the
    master-push group is removed)".
  - The orchestrator is under the same hold.
  - The ruling behind both holds is in `.ai/coordinator-duties.md` §10, "Superseded master runs" (the maintainer,
    2026-11-09; "OK B'"). Master pushes keep only the newest pending run, and "Neither repository adopts the reconciler
    before A lands unless B's setting is removed first". Option A has the reconciler re-run a cancelled master run
    before naming a culprit. **No work item for option A was found in the dev-tooling or livespec ledger.**
  - The children "watch the watcher" `4xrhck` and the drill `yilv6p` sit at pending-approval (since 11-06). `reslr6` (arm
    the conformance row) is pending-approval. livespec `livespec-d5c2mf`, "The master-health reconciler is installed in no
    fleet repository", is `ready` and stale: livespec has it.
  - The epic zcp5vb is `backlog`, and its last handoff (2026-10-19) waits on `approval:workflow-edit` for dw7dzd. That
    gate is stale too, because dw7dzd's workflow landed on 10-31.

### 2026-11-12: the merge queue ruled out again, and this plan opened

- **01:56:09Z, coordinator epic livespec-dev-tooling-6tgd2z, scope event.** The maintainer: "I DON'T HAVE A TEAM ACCOUNT I
  CANNOT USE THE MERGE QUEUE, IVE TOLD YOU THIS MANY TIMES". Standing rule written there by the coordinator: never
  propose GitHub merge queue; for "green apart, red together", offer only "branch protection's require-up-to-date
  (strict), or our own tooling re-testing the rebased result before or after merge".
- **02:01:48Z, regression-guard audit row 5** (coordinator helper). "No guard at any tier covers the
  semantic-merge-conflict class." It recommends re-testing the rebased result before a `merge-hold:on` lift for factory
  pull requests, and `strict` "if hand-merged PRs keep recurring". Owner: red-master-self-healing. Handoffs at 02:20Z,
  02:43Z and 04:09Z list "Whether to turn on require-up-to-date (strict) on dev-tooling master" as a maintainer question.
- **15:32Z to 17:40Z, today's incident.**
  - livespec-dev-tooling#4330 (4793883d8) merged 15:32:26Z.
  - livespec-dev-tooling#4339 (b9838b28c) was opened 15:02Z. Its head 33f42cffc does NOT contain 4793883d8. It merged
    green on that stale base at 16:09:03Z.
  - The first red master verdict came at 16:52:20Z (run 43257840402 on 6201dcdb2). Runs on b9838b28c and 254743e7f were
    cancelled by the B' master-push group.
  - The roll-forward livespec-dev-tooling#4357 (8b3d63404) merged 17:40:49Z. Its master run 43271983614 was still in
    progress at 18:28Z, so master had been red for 1 h 36 min and counting.
  - Factory runs failed on the red master meanwhile.
  - dev-tooling has no reconciler shim, so nothing acted automatically.
- **~18:0xZ, 6tgd2z scope event.** The maintainer: "FOR THE MILLIONTH TIME, I DO NOT HAVE AN ENTERPRISE ACCOUNT AND CANNOT
  USE GITHUBS MERGE QUEUE".
- **~18:1xZ, this plan's founding scope event.** The maintainer: "Anyways, yes, I want you to start a plan that
  investigates the impact of up-to-date branches and other options, such as implementing manual merge queues or
  third-party tools. I know I've already discussed this many times. There's already some prior discussion and art on
  this. That plan should start by looking for it and summarizing it."
- **~18:2xZ** (relayed by the coordinator). The maintainer: "new stale base merge options should be a high priority, since
  we keep hitting it. But it needs discussion with me on direction. Put it somewhere appropriate below the top 2 now,
  expedited and the centralized credential."
- **~18:1xZ, to this seat.** The maintainer: "USE HONEYCOMB TO GET YOUR METRICS WHERE POSSIBLE".

## The decisions, in order

| # | When | Decision | Recorded as | Where |
|---|---|---|---|---|
| 1 | 2026-05-29 | `strict` REQUIRED; a bot keeps pull requests up to date | spec text | livespec v096 |
| 2 | 2026-06-22 | `strict` OFF; semantic conflicts accepted and caught on master; no merge queue; no serialized auto-rebase driver | paraphrase | livespec v126-v128; dev-tooling v016 + code |
| 3 | 2026-08-23 | overseer only: enable a GitHub merge queue (never possible on a personal account; superseded 10-20) | paraphrase | overseer-hgq4wi.33 / tdfe.22 |
| 4 | 2026-10-14 | self-healing instead: no merge queue, no `strict` plus eager updater, no merge train | verbatim statement + paraphrased rulings | zcp5vb charter; livespec v224 |
| 5 | 2026-11-12 | never offer GitHub's merge queue (no team or Enterprise account) | verbatim | 6tgd2z 01:56Z and ~18:0xZ |
| 6 | 2026-11-12 | open this plan; high priority, below the top two; direction to be discussed with the maintainer | verbatim | xowhol; 6tgd2z priorities-record |

## Where the records disagree

- **What exactly was rejected about `strict`.** The coordinator's 18:02Z handoff says "NEVER offer a merge queue or strict
  ... strict REJECTED by livespec v126". The 10-14 charter rejects "`strict` plus an eager rebase-updater" specifically,
  for its N² CI cost. The 01:56Z standing rule and the 17:57Z scope event list `strict` as a live option. v126 itself
  rejected `strict` for a mechanical reason: GitHub's merge-commit update under auto-merge. That reason does not apply to
  a rebase-based updater, which the May bot already was. This plan therefore treats `strict` with a rebase updater as an
  option to MEASURE and present, because the maintainer asked for "the impact of up-to-date branches" by name. The open
  maintainer call is whether the earlier rejections stand.
- **Is the reconciler "the decided baseline"?** It is ratified, but it runs nowhere that the incidents happen. The B'
  ruling holds it out of the two busiest repositories until option A exists, and option A has no work item.

## Coordinator-duties text not yet on master

- 8f1323da0 ("never propose GitHub merge queue") is on PR livespec-dev-tooling#4247, OPEN with ci-green success.
- eb429f2d2 is on local branch `coord-top5-ccs-20261112` only.
- Master's `.ai/coordinator-duties.md` carries no merge-queue limit yet.

## What was not read

- **Orchestrator ledger comments.** The full-text scan timed out at the server. Only the term queries "merge queue",
  "merge_queue", "merge_group" and "auto-rebase" ran, and 17 candidate items were read one by one.
- **Broad terms.** "strict", "red master" and "serializ" were filtered by merge context, not read exhaustively, because
  pyright strictness and JSON strict parsing flood them.
- **The maintainer's own words for decisions 2, 3 and 4's rulings.** They were not found anywhere; only paraphrases
  survive.
