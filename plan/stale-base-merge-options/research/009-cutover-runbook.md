# 009 — Org cutover runbook and go/no-go list

Written 2026-11-15 by the stale-base-merge-options seat (hetzner-xubuntu). It applies note 005 §2-§3 as amended by the
rehearsal (note 008) and the coordinator's rulings of 2026-11-14/15 (epic livespec-dev-tooling-xowhol). Note 005 still
owns the halt procedure and the phase outline; this note fixes the ORDER and the CHECKS for the window. All times are UTC.

## 1. Window

- **Scheduled:** Mon 2026-11-16 16:00-20:00Z. The coordinator announces the halt, and the go/no-go call is at 12:00Z the
  same day.
- **Pull-in:** if every held PR (work item nwzkto) is green, apart from its classified owner-bound checks, by
  Sun 2026-11-15 12:00Z, the seat proposes Sun 16:00Z instead (condition C). The coordinator decides.

## 2. Go/no-go list (read at 12:00Z; every item must be GO)

1. The quiet check (`research/data/org-move/quiet_check.py.txt --halt-at <announcement>`) exits 0, with ghosts reported
   by id only.
2. The rehearsal result note is merged: note 008, livespec-dev-tooling#4726.
3. gf5g2x (guarded merge_group routing plus the merge-queue rules in branch_protection_alignment) is merged AND released
   in livespec-dev-tooling.
4. Every held PR is green, apart from checks named in its body with their note-005 class (owner-equality, live read by
   org/repo, org-ref `uses:` not yet resolvable).
5. The image mirror has been re-run with the halt-time pins, and every pinned image is present at `ghcr.io/livespec-ai`
   (yqpwy3). At the halt, run `python3 -I plan/stale-base-merge-options/research/data/org-move/image_pins.py.txt
   --out /tmp/image-pins-need.txt` from the livespec-dev-tooling checkout. If it reports any NEED, dispatch
   `gh workflow run mirror.yml -R livespec-ai/fleet-image-mirror -f images="$(cat /tmp/image-pins-need.txt)"`, then
   re-run the script until it exits 0. Its exit status is the signal: it is 1 on any NEED, NEW-ABSENT or
   NEW-UNREADABLE line. Read any NEW-* line before calling GO. The 13 test-fixture strings known on 2026-11-15
   print as KNOWN-FIXTURE and do not fail it. The baseline on 2026-11-15 ~01:3xZ was exit 0, with 43 of 43 real pins
   present, after mirror runs 43659542203 and 43660558376.
6. The org App secrets are verified through `GET /app` for livespec-ai-factory-bot (5761962) and
   livespec-ai-incident-recovery (5761967). DONE 2026-11-14.
7. Hosted minutes fit. GO on cost, accepted 2026-11-15 ~00:0xZ (§5).
8. dev-tooling master is green and no incident is open (condition B, note 008 §4). Otherwise NO-GO.

## 3. Sequence

Phase 2, the halt (note 005 §2): freeze, drain, then the quiet check. Two additions:

- **Preserve before any cancel** (coordinator-duties §10). legacy-dispatcher-agent executes this factory half, not this
  seat. Before ANY live factory run is cancelled:
  - its committed tree is on a ref on origin, verified with
    `git ls-remote origin refs/heads/needs-human/<dispatch-id>`, using the DISPATCH id, never the run id;
  - that ref has a non-empty diff against its merge-base with origin/master.

  The cancel goes through the factory server's `POST /api/v1/runs/{id}/cancel`, never `fabro rm --force`
  (`.ai/factory-restart-cancels-runs.md`). The record of cancelled ids stays with legacy-dispatcher-agent, which
  re-dispatches each one SEEDED from its preserved ref in Phase 5.
- During the halt, set each fleet repository's `CI_RUNNER_LABELS` variable to `["ubuntu-latest"]`. The personal-account
  ARC registrations stop serving after the transfer, and repository variables survive a transfer (rehearsal row 3).

Phase 3, the window. These are steps 1 to 5. Take them for ONE repository at a time, in this order: livespec-dev-tooling,
livespec, then the other eight.

1. **Transfer** with the maintainer's token:
   `POST /repos/thewoolleyman/<repo>/transfer`, with `new_owner: livespec-ai`.
2. **Visibility read-back (hard check):** `gh api repos/livespec-ai/<repo> --jq .visibility` must read `public`. If it
   does not, stop. Hosted CI is free only on public repositories (§5).
3. **Recovery bypass on EVERY master ruleset, with read-back.** The transfer resets every ruleset's `bypass_actors` to
   `[]` (rehearsal row 2). Add Integration 5761967, mode `always`, to each ruleset whose target includes master, one
   mutation per call, then read each one back. One bypass on `master-incident-recovery-bypass` alone is not enough: with
   the twin on one ruleset only, the other ruleset's required check still refused its push.
4. **Install the org Apps and re-project their secrets.** Install the org Apps on the repository, then set `APP_ID` and
   `APP_PRIVATE_KEY` from `GITHUB_APP_ID_ORG` and `GITHUB_PRIVATE_KEY_ORG`. The single-line PEM is rewrapped to 64
   columns before upload (rehearsal row 5).
5. **Webhook read-back.** The observer webhook stays listed and active, and the next delivery names `livespec-ai/<repo>`
   (rehearsal row 4).

After all 10 repositories are transferred:

6. **Land the held PRs.** livespec-dev-tooling goes first, followed by its release. Until that release exists, an
   old-name `uses:` ref does not resolve and other repositories' CI cannot run (rehearsal row 1). Then livespec (the
   manifest `owner`), then the other eight through the pin bump. Each PR must be fully green before it lands.
7. **Re-register the marketplaces on every host:** REMOVE the old registration, then ADD it by the new name, for both
   Claude and Codex. The two cannot coexist (rehearsal row 7). Old-name updates keep working through the redirect in
   the meantime, so no host breaks mid-window.
8. **Re-point the 12 adopters'** `.claude/settings.json`.
9. **The recovery drill on livespec-dev-tooling** (DoD assertion 6): the twin pushes one commit to master and it lands;
   the maintainer's token is refused.

Phase 5: lift the halt. legacy-dispatcher-agent re-dispatches the cancelled runs SEEDED from their preserved refs.
Watch master health for 24 hours.

**Phase 4 (the merge queue) is OUT of Monday's window.** Phases 2, 3 and 5 stand on their own. The maintainer has
ruled where the single full-suite run that guards master runs. That is call 3 of note 005 §5, recorded verbatim on this
epic in comment 27 at 2026-11-13T14:45:12Z: "3. The answer is obviously option A because this gives us control over the
capacity and speed I am not accepting contributions to this currently so I'm not concerned about the security risks
right now".

Option A is `merge_group` CI running the FULL suite on the guarded self-hosted runners, with every path to master going
through the queue. Its precondition is self-hosted runners registered at the organization, and those do not exist
until ARC is restored at livespec-ai (xyi5vu, §5). So Phase 4 starts after xyi5vu: require the merge queue on
livespec-dev-tooling and the orchestrator, run the semantic-conflict drill, and run one factory dispatch end to end (note
005 §3). The queue's build concurrency is a tuning value the seat sets from note 003's measurements, starting at 2 or
more, and reports. Requiring the queue on hosted runners on Monday would contradict option A.

## 4. If master goes red or an incident opens mid-window (condition B, accepted)

Pause at the step boundary, as note 008 §4 says.

- **Before step 1 of the first repository:** NO-GO.
- **Inside Phase 3:** finish the step in progress, then stop. Fix a transferred repository forward only through the
  twin's bypass push. Fix a repository not yet transferred through the personal-account path.
- **No halt lift** before dev-tooling's held PR and release land.

## 5. Hosted CI after the transfer (condition A, accepted 2026-11-15 ~00:0xZ)

Measured over workflow runs created 2026-11-07 to 2026-11-13: 15,854 runs and 72,884 jobs across the 10 repositories.

- **Cost: GO, with no end date.** All 10 repositories are public. Standard GitHub-hosted runners are free on public
  repositories and do not reduce included compute
  (docs.github.com/en/billing/concepts/product-billing/github-actions). The livespec-ai Actions budget reads $0 with
  `prevent_further_usage: true` (`GET /organizations/livespec-ai/settings/billing/budgets`).
  - Fleet demand averages 30,099 job-minutes a day, with a maximum of 43,982 on 11-13, and 76% of it already runs
    hosted.
  - If the repositories were private, Team's included compute would last about 0.1 day. That is why step 2's visibility
    read-back is a hard check.
- **Concurrency: queues at peak, accepted.** The Team limit is 60 concurrent standard hosted jobs
  (docs.github.com/en/actions/reference/limits).
  - The fleet peaked at 99 concurrent jobs, at 2026-11-12T18:49:43Z.
  - It ran more than 60 for 17 minutes in the week, and more than 40 for 449 minutes.
  - Excess jobs queue; they are not billed. This is a throughput regression until ARC returns.
- **Two jobs that never run hosted:** `macbook-m4-max-homelab-worker-k3s` (dev-tooling) and
  `self-hosted,livespec-orchestrator` (orchestrator-beads-fabro), about 81 minutes a week together. Their held PRs route
  them through `CI_RUNNER_LABELS`, or name them as queued until ARC returns.
- **The window runs with the factory halted,** so dev-tooling's held-PR release does not queue behind factory load.
- **ARC at the org (xyi5vu)** is off the critical path. The target is to have it back INSIDE the week after the cutover.
  The ask is with the maintainer through the coordinator: a new org App, `livespec-ai-arc`, created at
  `https://github.com/organizations/livespec-ai/settings/apps/new`. It needs repository Administration read/write and
  organization Self-hosted runners read/write, webhook off, installable only on livespec-ai. Its key is imported
  single-line into the livespec 1Password environment as `GITHUB_ARC_APP_ID_ORG` / `GITHUB_ARC_PRIVATE_KEY_ORG`.

## 6. Standing rule and rollback

- **Nobody creates a repository under any fleet repository's old `thewoolleyman/<name>`** (ADOPTED by the coordinator,
  2026-11-14). Reusing a name steals the old-name redirect permanently and blocks the rollback (note 008 §2).
- **Rollback before Phase 4:** transfer back to thewoolleyman. The rehearsal proved this works while the old name is
  unoccupied (note 008 §2). **After Phase 4:** disable the merge-queue requirement.

## 7. After the cutover

- Delete the rehearsal repositories in one batched step: the name-reuse stub, R and C (note 008 §5).
- Remove the rehearsal marketplace registrations on hetzner-xubuntu.
