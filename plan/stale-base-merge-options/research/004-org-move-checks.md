# 004 — Two checks on moving the fleet into a GitHub organization

Written 2026-11-12 ~19:1xZ by the plan seat of `stale-base-merge-options` (epic livespec-dev-tooling-xowhol). The
maintainer asked for these two checks after the seat recommended moving the fleet to an organization, so that GitHub's
merge queue becomes available. Both checks are read-only. The maintainer has not chosen a direction yet.

## Context the maintainer confirmed

- The `mi-homelab` GitHub organization exists (created 2026-08-22).
- `homelab` already lives there as `mi-homelab/homelab` (private), with its own org-owned App `mi-homelab-factory-bot`.
- The homelab spec names that organization (`SPECIFICATION/constraints.md`, integration-identity bullet), and the
  Talos/Omni rollout docs make the transfer a recorded step.
- A separate `livespec` organization would take the 10 `fleet` entries of livespec's `.livespec-fleet-manifest.jsonc`.
  Every `adopters` entry stays out.
- All 10 fleet repositories are public (read 2026-11-12 ~19:0xZ), so all 10 would get GitHub's merge queue on a free
  organization plan. Only private organization repositories need Enterprise Cloud (GitHub docs, "Merging a pull request
  with a merge queue").

## Check 1 — every `thewoolleyman` reference, sorted by what a transfer does to it

**Method.** `git grep -I -n -E` over each repository's tracked files at its local master. The regex matches
`thewoolleyman/<one of the 10 fleet repos>` or a quoted bare `"thewoolleyman"`. It excludes `*.lock`, `**/history/**`,
`plan/archive/**` and `archive/**`. The 10 fleet repositories and 16 outside repositories (the adopters, plus fabro,
petri, the 1Password wrapper and sandbox-driver-kubernetes) were scanned. Each match was sorted by path and line pattern.
Script: this seat's scratchpad `classify.py`, not committed.

| Category | What a transfer does | Fleet repos | Outside repos |
|---|---|---|---|
| D. docs, spec, plans, `.md` | Nothing breaks; GitHub redirects the links | 8,775 | 39 |
| E. tests and fixtures | Nothing breaks unless the code under test changes owner. The 130 bare `"thewoolleyman"` literals in the orchestrator are all here | 345 | 0 |
| F. URLs and `gh api` / `--repo` arguments | Redirect for git and REST; update for hygiene | 46 | 3 |
| B. Actions `uses: thewoolleyman/livespec-dev-tooling/...@vX` | See "reusable workflows" below | 91 | 0 |
| C. config data: `.claude/settings.json` marketplace `repo:` entries, `.livespec.jsonc`, Fabro `workflow.toml` | **Must change** | 233 | 53 |
| H. bare owner constants (`OWNER = "thewoolleyman"`, `FLEET_OWNER`, manifest `"owner"`, `EXPECTED_APP_OWNER`) | **Must change**. `auto-enable-merge.yml`'s `user.login` allowlist names a PERSON, so it stays valid | ~50 outside tests (180 total, including test fixtures) | 3 |
| A. equality checks on the full name | **Silent break**: the comparison stops matching and nothing errors | 9 (2 real) | 0 |
| G. other code and workflow lines | Review; mostly the GHCR image name and plugin install commands | 201 | 14 |

### The items that actually break, or need work outside the code

1. **The fleet GitHub App.** `thewoolleyman-factory-bot` is private: `GET /apps/thewoolleyman-factory-bot` answers 404.
   GitHub installs a private App only on the account that owns it. The organization therefore needs its own org-owned
   App, the same pattern as `mi-homelab-factory-bot`. That means a new App id and key, re-projected secrets in every
   repository through the 1Password environment, and `dolt-server`'s `EXPECTED_APP_OWNER` updated.
2. **Container images.** CI jobs and the factory's `workflow.toml` pull `ghcr.io/thewoolleyman/livespec-fabro-sandbox:*`,
   and so does `sandbox-driver-kubernetes`. Those packages belong to the user account. A repository in the organization
   cannot publish there with its own `GITHUB_TOKEN`. The image namespace moves to `ghcr.io/<org>/...`, or the old images
   stay readable while new ones publish under the organization.
3. **Plugin installs.** 22 repositories name the fleet marketplaces in `.claude/settings.json` (10 fleet, 12 outside). So
   do the per-host Claude installs, the host-wide Codex `config.toml` registrations, and
   `livespec-runtime/.github/scripts/ensure-codex-plugins.sh`. Every host re-registers.
4. **Two silent-break equality checks:**
   - livespec `.github/workflows/reusable-spec-pr-merge-policy.yml`, which tests
     `startswith("thewoolleyman/livespec/.github/workflows/reusable-spec-p...")`;
   - dev-tooling `ansible/roles/incident_observer/tasks/scratch_preflight.yml`, which tests
     `incident_observer_repository == 'thewoolleyman/livespec-dev-tooling'`.

   The other seven are test assertions.
5. **The manifest `"owner"` and the owner constants.** These are livespec's manifest, `FLEET_OWNER` in
   `livespec_dev_tooling/incident_fleet_host.py`, `OWNER` in `_git_identity_audit_report.py`, livespec's
   `fleet-runner-inventory.py`, the orchestrator's `materialized_workflow_toml_size.py` and dolt-server's `.livespec.jsonc`.
   The release fan-out and the fleet-conformance checks build every repository path from them.
6. **ARC runner scale sets.** They register per repository, so they re-register under the organization. Organization-level
   scale sets become possible.
7. **Honeycomb.** The `github-ci` `repo` attribute changes value at the move, so per-repository history splits at that
   date.

### Reusable workflows (`uses:`)

GitHub's transfer documentation says that when a transferred repository had more than 100 Actions uses in the week before
the transfer, GitHub permanently RETIRES the old owner/name pair. That protects old `uses:` references against takeover.
livespec-dev-tooling's reusable workflows are called from all 10 repositories on every CI run, so they would qualify.
Whether old `uses:` references then RESOLVE through the redirect is not stated in GitHub's docs. A community report says
they do. Treat them as must-update: the bump-pin automation already rewrites these lines on every release, so one release
after the move updates all 91.

**Check 1 verdict: no blocker.** About 300 functional lines change across 26 repositories, plus 4 out-of-repository moves
(a new org App, the GHCR namespace, host plugin re-registration and ARC re-registration). It is one coordinated cutover,
done in the stop-the-line style.

## Check 2 — may `merge_group` CI run on our self-hosted runners?

**What forbids it today.**
- `livespec_dev_tooling/checks/self_hosted_routing.py` puts `merge_group` in `_FORBIDDEN_TRIGGERS`. Those are "fork-reachable
  or privileged non-PR events that must never reach a gating self-hosted job". It is a fail-by-default security guard with
  no severity lever.
- `ci.yml:93-98` repeats the rule: "Re-add it WITH hosted routing only if a merge queue is adopted."
- The policy under both is livespec NFR §"Fork-exclusion precondition". Self-hosted capacity may carry a merge gate "ONLY
  while no workflow originating from a fork of that repository can execute on it", enforced by the strictest fork-PR
  approval tier. Read live 2026-11-12: livespec-dev-tooling's `approval_policy` is `all_external_contributors`.

**Why `merge_group` is riskier than `pull_request`.**
- A `merge_group` run executes the queued PRs' code in the BASE repository's trusted context, like a `push`, with secrets.
- A fork PR's own `pull_request` run gets no secrets and needs approval to run at all.
- So a fork PR that a write-access user puts into the queue would run fork code on our hosts WITH secrets. The approval
  gate does not cover that event.

**Whether the fleet can admit it safely.**
- The exposure needs someone with write access to enqueue a fork PR.
- Auto-merge is armed only for PRs authored by `thewoolleyman`, or by the factory bot for release PRs
  (`auto-enable-merge.yml`), so the factory never enqueues a fork PR.
- A guarded design is possible: a first job checks through the API that every PR in the merge group is a same-repository
  branch by an allowlisted author, and routes the run to hosted runners otherwise.
- That changes a security guard that has no lever by design. It needs a livespec propose-change to the Fork-exclusion
  precondition plus a dev-tooling check change, and **it is the maintainer's security call**.

**If queue CI stays on hosted runners instead.**
- Hosted minutes are free for public repositories.
- A free organization runs at most **20 concurrent hosted jobs, shared by every repository in it**. One full fleet CI run
  is 11 to 18 jobs (Honeycomb `dq5Vp19xjc8`, jobs per run). So at most one queue batch tests at a time across
  dev-tooling and the orchestrator together.
- The replay in note 003 assumed one batch at a time PER repository, so the shared cap adds latency that was not modelled.
- Our full suite's wall-clock on hosted runners was **not measured**: Honeycomb's `ci.runner.kind` is populated on too
  few spans to tell. It is the one number this check could not supply.

**Check 2 verdict: no blocker, but a choice.** Either admit `merge_group` on self-hosted runners behind a
same-repository and allowlisted-author guard (a security-policy change), or run queue CI on hosted runners under the
shared 20-job cap with unmeasured latency.

## What this changes in the recommendation

Neither check found a blocker, so the org move stays the recommendation. Two parts are the maintainer's to settle:

1. The new org-owned App and the GHCR namespace move. Both are outward-facing and involve secrets.
2. Hosted queue CI versus a guarded self-hosted `merge_group`.

The seat would recommend the guarded self-hosted route. The hosted route puts the busiest repositories' merges behind a
20-job cap shared with every other organization repository.
