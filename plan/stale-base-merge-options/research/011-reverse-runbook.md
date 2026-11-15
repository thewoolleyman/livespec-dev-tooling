# 011 — Reverse runbook: undoing the org cutover

Written 2026-11-15 ~09:20Z (date -u) by the stale-base-merge-options seat. It answers Astra pre-transfer review finding
7, ruled "before step 1" by throughput-plans-coordinator at ~09:15Z. Note 009 §6 said only "transfer back". Rehearsal
rows 2-3 (note 008) show why that is not enough:

- a transfer resets every ruleset's `bypass_actors` to `[]`;
- secrets and variables survive the transfer, so after step 4 they hold the ORG App's credentials;
- after step 6, workflows carry `uses: livespec-ai/...` refs, and the reverse redirect does not resolve those.

This note is the full reverse sequence. All times are UTC (`date -u`).

## When it applies

Roll back only before Phase 4, while each old name `thewoolleyman/<repo>` is unoccupied. Nobody creates a repository
under a fleet repository's old name (note 009 §6). After Phase 4, first disable the merge-queue requirement
(note 009 §6), then follow this note.

The halt stays on throughout. Phase 5 (lift) does not start until every read-back below passes for every reversed
repository.

## Recorded pre-cutover state (taken 2026-11-15 ~09:18Z, before the halt)

Runner-routing repository variables. These are restored in step R6. At the halt they are set to `["ubuntu-latest"]`
(Astra finding 1).

| repository | variable | value |
|---|---|---|
| livespec | CI_COVERAGE_RUNNER_LABELS | `["livespec-local-ci-k3s"]` |
| livespec | CI_RUNNER_LABELS | `["livespec-local-ci-k3s"]` |
| livespec-dev-tooling | CI_COVERAGE_RUNNER_LABELS | `["livespec-dev-tooling-k3s"]` |
| livespec-dev-tooling | CI_INCIDENT_RUNNER_LABELS | `["livespec-dev-tooling-k3s"]` |
| livespec-dev-tooling | CI_PYTHON_RUNNER_LABELS | `["ubuntu-latest"]` |
| livespec-dev-tooling | CI_RUNNER_LABELS | `["ubuntu-latest"]` |
| livespec-dev-tooling | CI_RUNNER_LABELS_MASTER | `["livespec-dev-master-k3s"]` |
| livespec-driver-claude | CI_RUNNER_LABELS | `["livespec-driver-claude-k3s"]` |
| livespec-driver-codex | CI_RUNNER_LABELS | `["livespec-driver-codex-k3s"]` |
| livespec-driver-pi | CI_RUNNER_LABELS | `["livespec-driver-pi-k3s"]` |
| livespec-orchestrator-beads-fabro | CI_COVERAGE_RUNNER_LABELS | `["livespec-orchestrator-k3s"]` |
| livespec-orchestrator-beads-fabro | CI_INCIDENT_RUNNER_LABELS | `["livespec-orchestrator-k3s"]` |
| livespec-orchestrator-beads-fabro | CI_RUNNER_LABELS | `["livespec-orchestrator-k3s"]` |
| livespec-orchestrator-beads-fabro | CI_RUNNER_LABELS_MASTER | `["livespec-orchestrator-master-k3s"]` |
| livespec-orchestrator-git-jsonl | CI_RUNNER_LABELS | `["livespec-orchestrator-git-k3s"]` |
| livespec-runtime | CI_RUNNER_LABELS | `["livespec-runtime-k3s"]` |
| livespec-console-beads-fabro | CI_RUNNER_LABELS | `["livespec-console-beads-k3s"]` |
| livespec-overseer | CI_RUNNER_LABELS | `["livespec-overseer-k3s"]` |

Master rulesets, each carrying Integration 5656677 (the personal-account recovery twin, mode `always`) before the
cutover:

| repository | ruleset id | name |
|---|---|---|
| livespec | 27138240 | master-incident-recovery-bypass |
| livespec-dev-tooling | 26758787 | master-incident-recovery-bypass |
| livespec-orchestrator-beads-fabro | 27138252 | master-incident-recovery-bypass |
| livespec-overseer | 27138269 | master-incident-recovery-bypass |

The other six repositories carried no repository ruleset. Re-read the ruleset list after a transfer back, because ids
are not guaranteed to survive.

Other pre-cutover values: the incident_observer `owner_id` for the fleet repositories is 158 (thewoolleyman). The fleet
manifest's `owner` is `thewoolleyman`. Repository `APP_ID` / `APP_PRIVATE_KEY` came from the personal factory App
thewoolleyman-factory-bot (App 3668528).

## Reverse sequence

Take one repository at a time, in REVERSE order of the forward transfers: the other eight, then livespec, then
livespec-dev-tooling last. Skip any step whose forward step never ran on that repository.

R1. **Old name free (hard check).** `gh api repos/thewoolleyman/<repo> --jq .full_name` must read
    `livespec-ai/<repo>`, meaning the redirect still points at the org. If it reads `thewoolleyman/<repo>`, a stub
    has taken the name: STOP. Rename or delete the stub first (note 008 §2).

R2. **Transfer back** with the maintainer's token: `POST /repos/livespec-ai/<repo>/transfer` with
    `new_owner: thewoolleyman`.

R3. **Visibility read-back:** `gh api repos/thewoolleyman/<repo> --jq .visibility` must read `public`.

R4. **Recovery bypass on every master ruleset, with read-back.** For each ruleset whose target includes the default
    branch, add Integration 5656677, mode `always`: one mutation per call, then read each one back. Remove
    Integration 5761967 (the org twin) if it is still listed. A twin on one ruleset only is not enough (rehearsal row
    2).

R5. **App credentials back to the personal App.** The seat sends the repository name to central-credential-service. It
    re-projects `APP_ID` and `APP_PRIVATE_KEY` from the personal factory App (3668528):
    - the key is rewrapped to 64 columns;
    - it is JWT-checked with `GET /app` returning id 3668528 before upload;
    - the secret names are read back, and no value is printed.
    On livespec-overseer, also re-check that `ADOPTER_APP_ID_THEWOOLLEYMAN` / `ADOPTER_APP_PRIVATE_KEY_THEWOOLLEYMAN`
    are still present.
    **Do not advance this repository past R5 until that read-back arrives.**

R6. **Runner variables restored** from the table above, then `gh variable list` read back. If ARC registrations for the
    personal account were deregistered meanwhile, leave `["ubuntu-latest"]` and record it instead.

R7. **Workflow and identity refs.** If any held PR from step 6 merged in this repository, revert it on the forge with a
    server-side revert. That route is reconciled with the red-green range gate (CLAUDE.md "The server-side revert").
    Land the revert on green CI, using the old-owner `uses:` refs at their pre-cutover tags, which resolve again once
    the repository is back. For livespec-dev-tooling, also revert any pin bump that moved callers onto a post-cutover
    dev-tooling release.

R8. **Fleet manifest.** If livespec#3237 (`owner: livespec-ai`) merged, revert it. Keep livespec#3251
    (`adopter_owner`), which is correct under either owner.

R9. **Incident observer.** If the in-window `owner_id: 356397670` change converged, set the fleet repositories back to
    158 and converge again. Verify one authenticated incident publication from a reversed repository.

R10. **Webhook read-back.** The observer webhook is still listed and active, and the next delivery names
     `thewoolleyman/<repo>`.

After every repository is reversed:

R11. **Marketplaces and adopters.** If step 7 ran, on every host REMOVE the `livespec-ai/...` marketplace registration
     and ADD the old name, for both Claude and Codex. If step 8 ran, revert the 12 adopters' `.claude/settings.json`.

R12. **Recovery drill** on livespec-dev-tooling with the personal twin. Its push lands, and the maintainer's direct
     push is refused.

R13. Lift the halt (note 009 Phase 5). legacy-dispatcher-agent re-dispatches the preserved runs, seeded.

## Owner per step

- The seat: R1-R4, R6-R8, R10, R11, R12.
- central-credential-service: R5.
- The seat with the incident observer converge: R9.
- legacy-dispatcher-agent: R13.
- legacy-coordinator-agent announces the lift.
