# 006 — Transfer rehearsal design (note 005 Phase 1 step 5)

Written 2026-11-14 by the stale-base-merge-options seat (hetzner-xubuntu), at the coordinator's direction of
2026-11-13 ~23:3xZ (epic livespec-dev-tooling-xowhol). This note is the DESIGN only. The run is work item
livespec-dev-tooling-x5p7o5, and its results go in a later note.

The rehearsal moves two throwaway repositories, not a fleet repository. Its job is to settle every "verify" in note 004
and every assumption note 005 rests on before a real repository moves. A row that fails here changes the cutover plan.
It is not a cutover defect.

## 1. Preconditions

The run needs all of these. The seat may seed the repositories (§2) before the first two exist, because seeding touches
only the personal account.

1. **The org fleet App and the recovery App's org twin exist** (note 005 Phase 1 step 3, maintainer ask c), and both are
   installed on livespec-ai with access to the rehearsal repository. Rows 2, 5 and 9 need them.
2. **The org settings from Phase 1 step 1 are set** (maintainer ask a), so the transferred repository inherits the
   settings the fleet will get. The settings are fork-PR approval for all outside contributors, the Actions policy and a
   read-only default `GITHUB_TOKEN`.
3. **A credential that can publish to `ghcr.io/livespec-ai`** (maintainer ask d). Only row 8's org half needs it.
4. **One ARC listener slot on the CI node, and the coordinator's go-ahead.** Row 6 registers a scale set on the shared
   cluster. If the coordinator declines, row 6 runs as a read of the ARC docs and is marked UNREHEARSED, never as a pass.

## 2. What gets created

- **R:** `thewoolleyman/livespec-transfer-rehearsal`, a public repository. It is transferred.
- **C:** `thewoolleyman/livespec-transfer-rehearsal-caller`, a public repository. It stays on the personal account, the
  way the 12 adopters do. It is the outside reference that the fleet's redirect dependence is measured from.

Both repositories carry a README that names this plan and says they are disposable. Neither holds a real secret: every
secret value is a random string generated for the rehearsal.

## 3. Rows: seed, observe, pass condition

Each row is read BEFORE the transfer (the baseline) and again AFTER. "Survives" means the post-transfer read matches the
baseline with no manual step.

| # | Seeded in R (or C) | Observation after the transfer | Feeds |
|---|---|---|---|
| 1 | A reusable workflow in R at a tag `v1`. C calls it three ways: `@v1`, `@<sha>` and `@master`. | C's next run of each call resolves, or fails at workflow resolution. Read the run's `referenced_workflows`. | note 004 "Reusable workflows"; note 005 Phase 3 step 6 |
| 2 | A `master` ruleset with an Integration bypass actor: 5656677 before the transfer. | After the transfer, read `bypass_actors`. Re-point it to the org twin. The twin pushes one commit to `master` and it lands. The maintainer's token is refused a direct push. | §4 assertion 6; Phase 3 step 3 |
| 3 | One Actions secret, one Actions variable and one environment with its own secret. | `gh secret list`, `gh variable list` and the environment list name all three. A workflow step prints the length of each secret. | Phase 3 step 2 |
| 4 | A repository webhook to a request-capture endpoint, with a ping. | The hook is still listed and active. A push delivers, and the delivery's `repository.full_name` is noted. | Phase 3 step 4 (the observer webhook) |
| 5 | A Release Please config plus workflow, using an App token. | After the org fleet App is installed on R, one releasable commit opens the release PR, and merging it tags. | Phase 3 step 6 (the dev-tooling release) |
| 6 | An ARC scale set registered at R's personal-account URL, `min-runners: 0`. | Whether a queued job still reaches the old registration. Then re-register at the org URL (repository-level, then once at org level) and one job runs. | Phase 3 step 5 (the 15 registrations) |
| 7 | `.claude-plugin/marketplace.json` with one trivial plugin, plus a Codex marketplace manifest. Register both on hetzner-xubuntu by the old name. | `claude plugin marketplace update` and the Codex equivalent, by the OLD registered name: does each still fetch? Then register by the new name and install. | §4 assertion 8; Phase 3 step 7 |
| 8 | A tiny image at `ghcr.io/thewoolleyman/livespec-transfer-rehearsal:probe`, linked to R by its `org.opencontainers.image.source` label. A workflow in R pulls it with `GITHUB_TOKEN`. | Does the pull still work after the transfer, with no package-settings change? If not, grant R access and retry. Then publish `ghcr.io/livespec-ai/livespec-transfer-rehearsal:probe` and pull it from R. | note 005 Phase 1 step 4, step 7's "old image" window |
| 9 | An open PR in R, armed for auto-merge, with `ci-green` pending. | After the transfer, is the PR still armed, does it merge on green, and does the factory App's `enable-auto-merge` job still work under the org App? | step 7's held PRs |
| 10 | An owner-equality step: a workflow job that asserts its `job_workflow_ref` starts with `<owner>/livespec-transfer-rehearsal/`. | It passes with the owner set to `livespec-ai` after the transfer, and fails with `thewoolleyman`. This is the proof step 7 names for the owner-bound check class. | step 7's "what proves each PR good" |
| 11 | Old-name reads from C and from a shell: `git clone`/`fetch` over https and ssh, `raw.githubusercontent.com/thewoolleyman/livespec-transfer-rehearsal/master/README.md`, and `gh api repos/thewoolleyman/livespec-transfer-rehearsal`. | Each one resolves (record the redirect status) or fails. | §4 assertion 7's premise: the redirects hold until the old name is reused |

## 4. The namespace-retirement leg

GitHub retires an old owner/name pair permanently when the repository had heavy Actions use in the week before the
transfer (note 004 quotes "more than 100 Actions uses"). livespec-dev-tooling will cross that threshold, and an
unexercised R would not. So the rehearsal crosses it on purpose:

- C carries a `schedule` workflow, every 10 minutes, that calls R's reusable workflow (row 1) and R's action at `v1`.
  That is 144 uses a day on hosted runners, which cost nothing for public repositories. It runs for 48 hours before the
  transfer.
- After the transfer, test two things:
  - **Old-name reuse.** Try to create a new repository named `thewoolleyman/livespec-transfer-rehearsal`. It should be
    refused if the name was retired.
  - **The rollback.** Transfer R BACK to thewoolleyman. Record whether GitHub allows it while the name is retired. This
    is the only rollback note 005 offers before Phase 4. If the transfer back is refused, the rollback line in note 005
    becomes "none after Phase 3 step 1", and the maintainer hears that before the halt.

If GitHub's actual threshold proves to be a different measure, such as action clones, the note records what was counted
and marks the leg as reaching a lower bound, not a pass.

## 5. Run order

1. Seed R and C (rows 1-11). Read every baseline. Start C's schedule.
2. Wait 48 hours for the retirement leg. Rows 6 and 7 are registered in this window.
3. Confirm the preconditions in §1.
4. Transfer R to livespec-ai with the maintainer's token (`POST /repos/thewoolleyman/livespec-transfer-rehearsal/transfer`,
   `new_owner: livespec-ai`).
5. Read every row again with no fixes. This is the "survives" column.
6. Apply each fix the cutover would apply: install the Apps, re-project secrets, re-point the bypass, re-register ARC
   and the marketplaces, grant package access. Read every row again. This is the "fixable" column.
7. Run the §4 tests: old-name reuse, then the transfer back.
8. Record the results as a research note with one row per table entry: survives / fixable (and how) / blocked. Add a
   scope event on the epic that names any row which changes note 005.

## 6. What changes note 005, by row

| Row result | Change to the cutover |
|---|---|
| 1: an old `uses:` ref fails | Phase 3 must land dev-tooling's held PR plus a release BEFORE any other repository's CI runs, and the halt covers that gap. |
| 2: the twin's bypass push is refused | No real repository transfers. This blocks the cutover (note 005's recovery blocker). |
| 7: the old marketplace name stops resolving | Every host re-registers inside the halt window, not after it. |
| 8: the old image pull fails after transfer | Step 7's held PRs must pin `ghcr.io/livespec-ai` images, and the halt cannot end until they land. |
| 9: auto-merge is dropped by the transfer | Each held PR is re-armed by hand in Phase 3 step 6. |
| §4: the transfer back is refused | The rollback line changes, as §4 says. |

## 7. Cleanup

The seat's token has no `delete_repo` scope. After the result note merges, the seat archives R and C, and the maintainer
deletes them. C's schedule is disabled at step 7 of §5, so it cannot keep running against an archived repository. The ARC
scale set and the marketplace registrations from rows 6 and 7 are removed by the seat at the same time. Their removal is
listed in the result note.
