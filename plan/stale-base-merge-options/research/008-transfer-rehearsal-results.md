# 008 — Transfer rehearsal results (work item livespec-dev-tooling-x5p7o5)

Written 2026-11-14 by the stale-base-merge-options seat (hetzner-xubuntu). This note records the run that note 006 designed.
It uses note 006's row numbers, and all times are UTC on 2026-11-14.

R is `livespec-transfer-rehearsal` (id 1458062618). C is `thewoolleyman/livespec-transfer-rehearsal-caller`.

- **Transfer:** R was moved to livespec-ai at 22:45:40Z with the maintainer's token.
- **No-fix reads:** 22:46-22:52Z.
- **Fixes and the "fixable" reads:** 23:04-23:08Z.
- **§4 tests:** 23:08Z.

## 1. Results by row

| # | Survives with no fix? | Fixable, and how | Evidence |
|---|---|---|---|
| 1 | **No.** C's run at 22:51:59Z ended with 0 jobs: workflow resolution failed for the old-name reusable-workflow refs. | Yes: point every `uses:` at the new owner. | Note 006 §6 applies: dev-tooling's held PR plus its release land BEFORE any other repository's CI runs. |
| 2 | **No.** `bypass_actors` was reset to `[]` on BOTH master rulesets (27276514 and 27282313); Integration 5656677 was gone. | Yes. Add livespec-ai-incident-recovery (App 5761967, `always`) to EVERY master ruleset. | With the twin on 27276514 only, its push was refused at 23:04:18Z by 27282313's required `ci-green` check. With the twin on both, its contents-API push landed as f043268d at 23:06:36Z (rule-suite 5123294124, `bypass`). The maintainer's direct push was refused with HTTP 409 at 23:04:32Z. |
| 3 | Yes. The secret, the variable, and the environment with its own secret all survived. | — | Read at ~22:47Z. |
| 4 | Yes. Hook 711940222 stayed active. | — | Push delivery 3854083516054634496 at 23:04:51Z carried `repository.full_name` = `livespec-ai/livespec-transfer-rehearsal`. |
| 5 | Yes, once the org fleet App's secrets were set. | Set `APP_ID` and `APP_PRIVATE_KEY` from `GITHUB_APP_ID_ORG` and `GITHUB_PRIVATE_KEY_ORG`. The single-line PEM is rewrapped to 64 columns before upload. | Run 43651446208 opened release PR #2, authored by `livespec-ai-factory-bot`. After the merge (8448109d), run 43651519797 created tag `livespec-transfer-rehearsal-v1.0.1` and release 445658105. |
| 6 | UNREHEARSED. There is no data-only ARC route. | — | Item livespec-dev-tooling-xyi5vu. |
| 7 | Partly. Updating by the OLD registered name still fetches through the redirect, for both Claude (23:06:53Z) and Codex (23:07:02Z). | Yes. Remove the old registration, then add by the new name. Both CLIs key a registration by the manifest's `name`, so the two cannot coexist. Adding by the new name beside the old one was refused at 23:07:08Z (Claude: the source does not match its `extraKnownMarketplaces` entry) and at 23:07:24Z (Codex: already added from a different source). | After the remove and re-add, `rehearsal-noop` installed from `livespec-ai/livespec-transfer-rehearsal` in both CLIs at 23:08Z. |
| 8 | The org half is proven: the fleet-image-mirror run 43645720921 published 3 sandbox tags with equal digests. The old-name half was left UNREHEARSED by ruling. | — | Item yqpwy3 stays open for the halt-time re-run. |
| 9 | Yes. PR #1 stayed armed (REBASE). | The org fleet App re-armed it: `enablePullRequestAutoMerge` at 23:05:22Z, enabled by `livespec-ai-factory-bot`. | Merge-on-green was NOT measured, because nothing in R posts `ci-green`. |
| 10 | Passes as designed. | — | livespec-ai owner check succeeded at 22:46:34Z; thewoolleyman owner check failed at 22:46:47Z. |
| 11 | Yes, until the old name is reused (§2). Old-name api, raw and https clone resolve, and the web answers 301 to the new name. | — | Read at ~22:50Z. |

## 2. The namespace-retirement leg (note 006 §4)

- **The old name was NOT retired.** C's 10-minute schedule had made more than 100 Actions uses of R in the week before the
  transfer. Even so, `POST /user/repos` with name `livespec-transfer-rehearsal` SUCCEEDED at 23:08:24Z (stub id 1458264596).
  So "more than 100 Actions uses" did not trigger retirement here. Whatever GitHub actually counts, this leg reached a
  lower bound, not the threshold.
- **Reusing the name steals the redirect, permanently.** Once the stub existed,
  `repos/thewoolleyman/livespec-transfer-rehearsal` resolved to the stub, not to R. Renaming the stub did not give the
  redirect back: the old name then redirected to the renamed stub (23:08:3xZ).
- **The rollback works while the old name is free.** After the stub was renamed, R transferred BACK to thewoolleyman at
  23:08:40Z. It kept id 1458062618, and the org name now redirects to it.

## 3. What changes note 005

- **Row 1** applies note 006 §6 as written. The cutover lands dev-tooling's held PR plus its release FIRST after the
  transfers, and the halt covers that gap.
- **Row 2** adds a step. Immediately after each transfer, and before that repository's held PR, add the recovery twin as a
  bypass actor on EVERY master ruleset of the repository, then read each one back. One bypass on
  `master-incident-recovery-bypass` alone is not enough.
- **Row 7** means the hosts re-register inside the window: remove the old registration, then add by the new name, on
  every host. Old-name updates keep working through the redirect meanwhile, so this cannot break a host mid-window. It
  only has to be done before old-name references are retired.
- **§2** keeps note 005's rollback: a transfer back works while the old name is unoccupied. It also adds a standing rule:
  **nobody creates a repository under any fleet repository's old `thewoolleyman/<name>` after the move.** Doing so
  silently and permanently breaks every old-name reference the 12 adopters still hold, and blocks the rollback.

## 4. Condition B — dev-tooling master red, or an incident, during the window

Decision: **pause at the step boundary.** EXPEDITED_INCIDENT_RESPONSE is used only for a production defect that cannot wait
for the window to finish, and only on a repository whose recovery bypass has been re-pointed and read back (row 2).

- **Before Phase 3 step 1** (nothing transferred yet), a red dev-tooling master or an open incident is a NO-GO. The halt
  holds and nothing transfers until master is green and the incident is closed. Recovery runs on today's personal-account
  path.
- **Inside Phase 3**, finish the step in progress, then stop. Never leave a transfer, a bypass re-point or a held-PR
  landing half-done. A repository already transferred is fixed forward by the twin's bypass push. A repository not yet
  transferred is fixed through the existing personal-account path. The next step starts only once master is green.
- **How it is proven:** row 2 proves the twin's bypass push lands on a transferred repository. The full
  EXPEDITED_INCIDENT_RESPONSE chain (incident CI and provenance) has NOT been run on an org-owned repository. It calls
  dev-tooling reusable workflows, which row 1 shows stop resolving under the old name. So until dev-tooling's held PR and
  its release land, only the bypass push is proven for a mid-window fix, and the halt is not lifted before they land.

## 5. Cleanup state

- **C's schedule:** workflow 418541851 (`call-rehearsal.yml`) is `disabled_manually`.
- **Marketplace registrations on hetzner-xubuntu:** both point at the new name, and `rehearsal-noop` is installed. They
  are removed when R is archived.
- **Repositories for the maintainer to delete:** the name-reuse stub, `thewoolleyman/livespec-transfer-rehearsal-namereuse-stub`
  (id 1458264596), plus R and C, after this note merges. The seat's token has no `delete_repo` scope.
