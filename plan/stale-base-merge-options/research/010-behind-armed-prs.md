# 010 — Armed PRs stalled behind a strict up-to-date rule

Written 2026-11-15 by a helper for the stale-base-merge-options seat (hetzner-xubuntu), at the request of
legacy-coordinator-agent. All times are UTC on 2026-11-15 unless a date is given. Nothing on GitHub was changed: no
branch was updated, nothing was merged, no setting was touched.

The question: in hetzner-xubuntu-info, two PASS-graded PRs with auto-merge armed (#170 and #178) sat unmerged at
`mergeable_state: behind`. The cause is "require branches to be up to date" (`strict`) plus a burst of merges. GitHub
auto-merge never updates a branch, so each one needed a hand update. This note measures where `strict` is on, how often
an armed PR stalls behind it, and which of those repositories the org move's merge queue will cover.

## 1. Which repositories require up-to-date branches

Scope: the 10 fleet repositories and the 12 adopters in livespec's `.livespec-fleet-manifest.jsonc` (`homelab` is
`mi-homelab/homelab`; every other repository is under `thewoolleyman`).

Three reads, all at 06:21-06:22Z:

- **R1, one batched GraphQL query** (`data/behind-armed/protection_query.graphql.txt`, cost 5) for each repository's
  classic `branchProtectionRules` (`requiresStatusChecks`, `requiresStrictStatusChecks`) and its rulesets with
  `includeParents: true` (each `REQUIRED_STATUS_CHECKS` rule's `strictRequiredStatusChecksPolicy`).
- **R2, the classic REST read** `repos/<o>/<r>/branches/<default>/protection/required_status_checks` (`.strict`) for
  every repository where R1 showed a classic strict flag, plus livespec-dev-tooling as a control and homelab.
- **R3, the effective-rules read** `repos/<o>/<r>/rules/branches/<default>` for all 22. It returns every active
  ruleset rule that applies to the branch, organization rulesets included, so it covers mi-homelab's org rulesets.
  The direct `orgs/mi-homelab/rulesets` read was refused: this token lacks `admin:org`.

| Repository | Default | Effective strict | Source |
|---|---|---|---|
| thewoolleyman/hetzner-xubuntu-info (private, adopter) | master | **ON** | Classic protection: `strict: true`, contexts `ci-green` (R2). No ruleset. |
| The other 21 | master or main | off | See below. |

The other 21 are off for one of four reasons:

- **Ruleset with strict off, and classic status checks disabled** (livespec, livespec-orchestrator-beads-fabro,
  livespec-overseer). R1 shows a stored classic `requiresStrictStatusChecks: true`, but `requiresStatusChecks: false`.
  R2 answers 404 "Required status checks not enabled", so the classic flag is inert. The effective rule is the
  `master-incident-recovery-bypass` ruleset (27138240, 27138252, 27138269), whose required-checks rule has
  `strict_required_status_checks_policy: false` (R3). **Latent:** re-enabling classic required status checks on any of
  these three would bring `strict` back silently.
- **Ruleset with strict off, classic strict off** (livespec-dev-tooling, ruleset 26758787).
- **Classic protection with `strict: false`, no ruleset that requires checks** (livespec-runtime, the three drivers,
  livespec-console-beads-fabro, livespec-orchestrator-git-jsonl, openbrain, dolt-server, resume, homelab). resume's one
  ruleset (18639747) requires only linear history.
- **No protection and no rules** (vps-info, poweredge-xubuntu-info, gmktec-xubuntu-info, hp-xubuntu-info, fabro-hosts,
  otel-collector, local-llm). None of these allows auto-merge.

So **one repository requires up-to-date branches: hetzner-xubuntu-info.** It has done so since at least 2026-11-06:
its own note `plan/bootstrap-credentials-and-onboarding/research/021-app-key-receiver.md` (commit a049bde,
2026-11-06T06:21Z) records "strict required check `ci-green`".

Side observation (not pursued): `strict` there is outside the fleet's v126 posture. dev-tooling's
`branch_protection_alignment` fails `strict_enabled`, but hetzner-xubuntu-info's `just check` does not run that check.
Its justfile only does `import? 'dev-tooling/branch-protection.just'`. Whether the adopter baseline is meant to carry
strict-off is not established here.

## 2. How often an armed PR sits behind (hetzner-xubuntu-info only)

### (a) Now

- **Read at 06:21:52Z**, one batched GraphQL query over all 22 repositories' open PRs (`mergeStateStatus`,
  `autoMergeRequest`). **0 armed PRs were `BEHIND` in any repository.** In hetzner-xubuntu-info, 2 of 4 open PRs were
  armed: #170 and #178. Both read `CLEAN`, so both had already been updated by hand: #178 at 06:20:06Z and #170 at
  06:20:34Z.
  - `mergeStateStatus` is computed lazily. On a first read most PRs in the busy repositories read `UNKNOWN` (70 of 76 in
    livespec-dev-tooling). That does not matter for this question: outside hetzner-xubuntu-info, being behind does not
    block a merge.
- **Re-read at 06:22:09Z and 06:26:44Z.** #170 merged at 06:22:39Z. That moved master under #178, which needed a
  SECOND hand rebase at 06:25:15Z and merged at 06:26:43Z. Two armed PRs updated by hand 28 s apart leapfrog: whichever
  lands first sends the other behind again.

### (b) The last 7 days

**Method.** Window: PRs merged from 2026-11-08T06:23Z to the read at 06:23:43Z, plus open PRs. Four GraphQL pages
(`data/behind-armed/timeline_query.graphql.txt`, cost 91 each, read 06:23-06:24Z) fetched all 177 of the repository's
PRs. Each page carries:

- `timelineItems` of type `AUTO_MERGE_ENABLED_EVENT`, `AUTO_REBASE_ENABLED_EVENT`, `AUTO_SQUASH_ENABLED_EVENT`,
  `AUTO_MERGE_DISABLED_EVENT`, `HEAD_REF_FORCE_PUSHED_EVENT`, `PULL_REQUEST_COMMIT` and `MERGED_EVENT`;
- the `ci-green` check run's `completedAt` on each commit, including a force push's `beforeCommit`.

`data/behind-armed/stall_scan.py.txt` did the scan.

- **Arming.** A PR counts as armed if it has any auto-merge enable event. This repository arms with REBASE or SQUASH,
  which GitHub records as `AutoRebaseEnabledEvent` / `AutoSquashEnabledEvent`, not `AutoMergeEnabledEvent`. A first pass
  that asked only for `AUTO_MERGE_ENABLED_EVENT` found 0 armed PRs.
- **An update** is any head change after arming of one of two kinds:
  - a commit with two parents or a "Merge branch 'master'" headline (GitHub's update-branch merge);
  - a `HeadRefForcePushed` event (a rebase). For each one the script records whether the base parent moved.
- **The stall starts** at max(arming time, the `ci-green` success on the pre-update head). Only `ci-green` is required.
  So an armed PR that is green and does not merge is blocked only by being behind.
- **The stall ends** at the update.
- **Stall or catch-up.** An update less than 5 min after the stall start is counted as an arm-time catch-up, not a
  stall: the PR was already behind when it was armed, and the update came with the arming.

**Results.**

| Measure | hetzner-xubuntu-info |
|---|---|
| PRs merged in the window | 130 (by day: 4, 2, 2, 10, 12, 35, 49, 16 for 11-08 to 11-15); median gap 19.2 min |
| Armed PRs in the window | **41** (40 merged, 1 open at read); the first was armed on 11-13. The other 90 merges were never armed |
| Armed PRs that merged with no update | 22. Armed-to-merge median 1.3 min, p90 2.0, max 2.7 |
| Armed PRs with any update after arming | 19 (21 updates) |
| Arm-time catch-ups (< 5 min) | 12 updates on 11 PRs (#179, #169, #168, #145, #100, #94, #92, #91, #88, plus #162, #110 and #90 with no `ci-green` success on the old head) |
| **Behind stalls (>= 5 min)** | **9 stalls on 9 PRs** (22% of armed PRs): #170, #148, #172, #160, #168, #178, #164, #152, #88 |
| **Stall time** | **median 23.5 min, max 98.2 min (#170)**. All nine: 10.8, 10.9, 17.0, 20.6, 23.5, 34.7, 35.1, 45.1, 98.2. Total 296 min |
| Update to merge (re-test after the update) | 1.0-3.3 min, median about 1.9 min |
| Master push CI in the window | 130 runs of `CI`, all `success` (two pages of `actions/runs?branch=master&event=push`, read 06:25Z) |

Every stall ended in a hand update by `thewoolleyman`, which is the token every agent uses. Eight of the 21 updates were
rebases (force push, base moved); the rest were GitHub update-branch merges. No stall resolved on its own, because
nothing in the repository updates a behind branch. Arming survived the update in all nine cases: one enable event each,
except #148, which was disabled and re-armed once. #178's 20.6 min stall is its first one only; its second, after #170
landed, is not in the scan, which read before it happened.

The other 21 repositories: no armed-behind stall is possible, because no merge there requires an up-to-date branch
(§1). They were not scanned.

**Blind spots.**

- **The 90 never-armed merges are invisible.** An agent that updates a behind branch before merging by hand leaves no
  signal that separates the wait from its own work. The real behind cost is therefore larger than the 296 min.
- **Armed PRs exist only from 11-13.** The 7-day window holds about 2.5 days of armed traffic, so the 22% rate rests on
  41 PRs.
- **The stall start is an estimate.** It uses the latest `ci-green` success on the pre-update head. A PR whose old head
  never went green (3 updates) gets no stall time. If master moved after `ci-green` went green, the PR would merge
  first, so the estimate holds. It can overstate a stall when a non-required check or a human hold also held the PR;
  there is no sign of either here.
- **Rebases are not checked for new content.** A force push may carry new content along with the rebase. The script
  checks only that the base parent moved.
- **Merge-commit times are approximate.** A merge-commit update is timed by its `committedDate`. That equals the creation
  time for a GitHub-made update-branch commit, but is approximate for a local merge pushed later.
- **The 5 min threshold.** The cut between catch-up and stall is a judgment, not a measured boundary. The shortest stall
  is 10.8 min and the longest catch-up is 1.9 min, so any cut between those two gives the same split.

## 3. Coverage by the org move's merge queue

The merge queue (note 005 §3 Phase 4; note 009 §3) is required only on livespec-dev-tooling and
livespec-orchestrator-beads-fabro, after ARC at the org (xyi5vu). **Neither of those two has `strict` on.** The one
strict repository, hetzner-xubuntu-info, stays under thewoolleyman (note 005 §4: every adopter stays with its current
owner). **So the merge queue covers 0 of the 1 strict repository.**

**GitHub merge queue availability, VERIFIED 06:27Z** from the rendered page
`docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue`:
"Pull request merge queues are available in any public repository owned by an organization, or in private repositories
owned by organizations using GitHub Enterprise Cloud." (Note 003 recorded the same reading.) hetzner-xubuntu-info is
private and user-owned. So moving it to livespec-ai, which is on Team, would still not give it a queue. Only Enterprise
Cloud or making it public would. The same applies to `mi-homelab/homelab`: it is private and org-owned, and it is not
strict today. **The uncovered state is therefore permanent for hetzner-xubuntu-info, not interim.**

## 4. Recommendation for hetzner-xubuntu-info

**Keep `strict`, and add an eager, armed-only rebase updater.** Owner: the hetzner-xubuntu-info seat. It is a
`.github/workflows/` change in that repository; nothing changes in the fleet.

- **Why `strict` is affordable here when it was not on dev-tooling.** Notes 003 and 005 rejected `strict` for
  livespec-dev-tooling on two figures: 103.7 merges a day against 22.5 min p50 CI. A lazy line drains at most 64 a day,
  and an eager updater adds about 15 times today's CI. hetzner-xubuntu-info's figures are about 10 times smaller on
  each axis:
  - its peak is 49 merges a day;
  - its re-test after an update takes about 2 min;
  - it had 2-4 open PRs at a time today.

  An eager updater costs a few 2-minute runs per merge. A serialized line would drain about 700 merges a day. The N²
  objection does not apply at these numbers.
- **Why not drop `strict`.** Dropping it is the zero-machinery option, and it would match the fleet's v126 posture.
  But it gives up the one property this plan exists for: no stale-base semantic conflict reaches master (notes 002 and
  003; incident 3hilpy, note 005 §5). hetzner-xubuntu-info's master drives host provisioning, and 130 of 130 master runs
  were green this week. The repository gets no merge queue to fall back on (§3). For a repository whose CI is this
  cheap, buying correctness with stalls and then removing the stalls is the better trade.
- **The updater's shape.**
  - On `push` to master, for each open PR that is armed AND `mergeStateStatus == BEHIND`, call GraphQL
    `updatePullRequestBranch(updateMethod: REBASE)`.
  - Authenticate with the repository's App token, not `GITHUB_TOKEN`. A `GITHUB_TOKEN` push does not trigger CI, which
    was livespec-6du's 2026-05 failure (note 002).
  - Rebase, never merge. That matches the repository's rebase/squash arming and keeps history linear.
  - Update armed PRs only, so drafts and unarmed work cost nothing.
  - The 2026-05 fleet updater also left PRs stuck BEHIND (livespec-x0x). Run the new one with a measured exit check:
    0 armed `BEHIND` PRs older than one CI run.
- **If the seat prefers no new workflow**, the alternative is to drop `strict`, accept post-merge detection on master
  (the v126 position), and record that decision on the repository. That is a judgment for the repository's owner. This
  note's numbers favour the updater.

## 5. Monday's go/no-go list (note 009 §2)

**No change.**

- **No gating effect.** The only strict repository is an adopter that does not transfer. No cutover step touches its
  protection, and a stall costs throughput, not correctness. Phase 4, the only part of the plan that a merge queue
  touches, is already outside Monday's window.
- **One operational note for step 8.** Step 8 lands a `.claude/settings.json` re-point PR in each adopter. In
  hetzner-xubuntu-info that PR is subject to `strict`. If other merges land around it, it may need one hand update
  (`gh pr update-branch --rebase`) unless the updater exists by then. That is a step-8 execution detail, not a
  go/no-go item.

## 6. Calls spent

About 60 REST calls and 9 GraphQL queries (GraphQL cost about 440 points), read 06:20-06:27Z.
