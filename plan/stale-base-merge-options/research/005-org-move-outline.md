# 005 — The org move: inventory, halt procedure, cutover outline, draft Definition of Done, maintainer calls

Written 2026-11-12 ~19:5xZ by the plan seat (epic livespec-dev-tooling-xowhol), after the maintainer chose the org move
(scope event ~19:3xZ). **This is PREPARATION ONLY.** The cutover waits for priorities 1 and 3 on the coordinator's
priorities-record (6tgd2z, ~19:4xZ) to land and for the halt to quiesce the fleet:
1. expedited-incident-response-flag (livespec-dev-tooling-bqnzcm);
2. central-credential-service;
3. bootstrap-credentials-and-onboarding (hxi-vxsmdv).

The halt announcement is the coordinator's.

Scope: the 10 `fleet` entries of livespec's `.livespec-fleet-manifest.jsonc`. Every adopter stays where it is (note 004).

## 1. Inventory of URL-bound artifacts (read 2026-11-12 ~19:4xZ)

### GitHub-side artifacts (gh API, per repository)

| Repository | Webhooks | Actions secrets | Variables | Rulesets (bypass) | Release Please | Environments, deploy keys, Pages |
|---|---|---|---|---|---|---|
| livespec | 0 | 4: APP_ID, APP_PRIVATE_KEY, HONEYCOMB_GITHUB_CI_INGEST_KEY_LIVESPEC, ANTHROPIC_API_KEY_LIVESPEC_E2E | 2 | master-incident-recovery-bypass (Integration 5656677) | config + manifest | none |
| livespec-dev-tooling | **1** → `vps.perch-rudd.ts.net:10000` (incident observer) | 4: APP_ID, APP_PRIVATE_KEY, HONEYCOMB_…, LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN | 8 (runner labels, incident-observer URLs) | master-incident-recovery-bypass (5656677) | config + manifest | none |
| livespec-orchestrator-beads-fabro | 0 | 3 | 2 | master-incident-recovery-bypass (5656677) | config + manifest | none |
| livespec-overseer | 0 | 3 | 1 | master-incident-recovery-bypass (5656677) | config + manifest | none |
| livespec-console-beads-fabro | 0 | 5: + BEADS_CI_WRITER_SSH_KEY, BEADS_DOLT_PASSWORD | 2 | — | config + manifest | none |
| livespec-driver-claude / -codex / -pi, livespec-orchestrator-git-jsonl, livespec-runtime | 0 | 3 each | 1 each | — | config + manifest | none |

- **Every repository carries APP_ID and APP_PRIVATE_KEY** for the private, user-owned fleet App. Those secrets are
  replaced by the org App's (note 004 item 1).
- **Integration 5656677** is the bypass actor in four repositories' `master-incident-recovery-bypass` rulesets. That is
  the expedited-incident-response recovery App. If it is user-owned and private, it too needs an org-owned replacement,
  and its four rulesets need the new actor id. Phase 1 step 2 reads its owner and records the answer on the epic, and the
  §3 cutover blocker follows from that answer.
- **The incident observer's webhook** points at a tailnet host. It transfers with the repository, but its
  shared secret and the observer's expected-repository checks are owner-bound. One of those checks is note 004's
  silent-break line, `scratch_preflight.yml`.

### Runner, image and plugin artifacts

- **ARC scale sets** (`githubConfigUrl` in `ci-runner/**/values-*.yaml`): 15 registrations name fleet repositories
  (livespec-dev-tooling 6; the other nine 1 each) plus `thewoolleyman/fabro`, which stays out. Each gets a new URL and is
  re-converged. The ARC controller's GitHub credential must be authorized on the organization. An org-level scale set
  becomes possible, and is a design choice, not a requirement.
- **Container images.** `ghcr.io/thewoolleyman/livespec-fabro-sandbox:*` is used by every repository's `ci.yml`, by the
  orchestrator's Fabro `workflow.toml` and by sandbox-driver-kubernetes. The images publish under the organization after
  the move.
- **Plugin marketplaces on this host (vps).**
  - `~/.claude/plugins/known_marketplaces.json` names 4 fleet marketplaces: livespec, livespec-driver-claude,
    livespec-overseer and livespec-orchestrator-git-jsonl. The last is pinned to a commit.
  - `installed_plugins.json` holds 117 per-project install records across 10 plugin ids.
  - `~/.codex/config.toml` has 5 fleet `source = "https://github.com/thewoolleyman/…"` entries.
  - Every other host with Claude Code or Codex carries its own copy: hetzner, gmktec, hp, poweredge, gamingpc and the
    macbook.
  - The committed `.claude/settings.json` marketplace `repo:` entries are in 22 repositories (note 004, category C).
- **Honeycomb.** No dataset is named after the account (`github-ci`, `metrics`, `llm-spend`, `codex-app-server`,
  `ci-runner-pool`). The `github-ci` `repo` attribute carries `owner/name` and changes value at the move. Saved queries
  and boards that filter on it need the new value or an `in` list.
- **Unaffected:** beads tenants (named by repository, not owner), the 1Password environment layout (only the App secrets
  inside it change) and adopter repositories (they only repoint their marketplace entries).

## 2. The halt procedure (what freezes, what drains)

The coordinator announces it. These are the contents. Order: freeze inflow, drain, verify quiet.

**Freeze (stop new work entering):**
1. **Factory dispatch.** No new `impl:` dispatch on any factory (hp, gmktec/petri, vps). Do not hold the fleet cap at 0
   waiting for runs to end (`.ai/factory-restart-cancels-runs.md`). Instead, cancel live runs through
   `POST /api/v1/runs/{id}/cancel`, record each id for re-dispatch after the cutover, and push nothing further.
2. **Seats.** Every plan seat stops opening pull requests, and drain-backlog engines stop launching.
3. **Automation that writes to GitHub:**
   - Release Please and release fan-out: no release in flight; let the in-flight one finish first;
   - `bump-pin-from-dispatch`, `pin-freshness`, `release-lane-watch`;
   - the livespec master-health reconciler shim (it acts on schedule);
   - host timers that push or comment: the janitor, the drain engines, and the coordinator's tick writes, which pause.
4. **Merging.** Merges stop once the drain below finishes. Any PR not merged by then is labelled `do-not-merge` so
   `auto-enable-merge.yml` cannot re-arm it.

**Drain (finish or park what is in flight):**
- Every open PR in the 10 repositories is either merged green or parked with `do-not-merge` and a ledger note.
- Master CI is green, with a completed verdict, in all 10 repositories.
- No workflow run is in progress or queued in the 10 repositories (`gh run list --status in_progress` / `queued` empty).
  **Ghost runs never drain, and GitHub will not cancel them.** Measured 2026-11-13 ~00:3xZ: 31 runs had sat in `queued`
  for more than 24 hours. Four are `Bump pin from sibling dispatch` runs from 2026-08-19, in livespec-driver-claude,
  livespec-driver-codex and livespec-runtime. The other 27 are CI, Auto-enable merge and Master health reconcile runs
  from a 2026-11-11 20:18Z-20:52Z burst, in seven of the 10 repositories. 30 of the 31 have ZERO jobs: GitHub created the
  run and never its jobs. Every cancel was refused. `gh run cancel` returned 409 "completed", and force-cancel returned
  409 "not queued yet" (per-run record: comment on this epic, 2026-11-13T00:47:15Z). By legacy-coordinator-agent's ruling
  (b), the quiet check excludes a run that is `queued` with zero jobs, never updated since creation, and created before
  the halt announcement (`--halt-at`). It reports such a run as `ghost` with its id, and nothing is deleted. A queued
  run that has any job still counts as active, and so does a `pending` run held by a concurrency group.
  **Older than 24 h with a job (ruling (i), legacy-coordinator-agent, received 2026-11-13 ~01:5xZ).** livespec-runtime 32215471962
  (`Bump pin from sibling dispatch`, 2026-08-19) has one job, queued on `ubuntu-latest`. It refuses cancel like the
  ghosts, and it had not started in 86 days. The ghost rule therefore also covers a `queued` run that was never updated
  after creation, was created before `--halt-at`, and is more than 24 h old, whatever its job count. Nothing is
  deleted, and nothing is excluded by id. `--self-test` checks the boundary rows: just over 24 h (ghost), exactly 24 h
  and just under (active), plus the zero-job, updated, after-the-halt and `pending` cases. A live run at ~01:5xZ with
  `--halt-at` set to that minute reported exactly the 31 measured runs as ghosts.
- No gate Job is on the ARC runners.
- No release is mid-flight.
- Every image the held PRs pin is present at `ghcr.io/<org>/<name>:<tag>` (Phase 1 step 4).

**Quiet check (the gate to start the cutover):** all of the above read live by one script,
`plan/stale-base-merge-options/research/data/org-move/quiet_check.py.txt`. Run it as
`python3 -I quiet_check.py.txt --halt-at <announcement UTC> [--org <org> --image <name>:<tag> ...]`. For each fleet repository it checks five things:
- every open PR carries `do-not-merge` with auto-merge off;
- the latest `ci.yml` run on master completed with success;
- no run is active;
- no merged PR still carries `autorelease: pending`;
- no gate Job is active in the cluster's `gates` namespace.

It also checks that each `--image` is present under `ghcr.io/<org>`. Any read it cannot take counts as NOT quiet, and
it exits 0 only when the fleet is quiet. The seat reports its output to the coordinator. A live run (2026-11-13
~00:3xZ, the fleet working normally) read NOT QUIET in all 10 repositories, as expected. That run is saved beside
the script.

## 3. Cutover outline

**Phase 0 — maintainer calls (§5), before anything else.**

**Cutover blocker (coordinator, 2026-11-12 ~20:0xZ): the recovery App's org twin.** The recovery bypass actor is
Integration 5656677, in the `master-incident-recovery-bypass` rulesets of livespec, livespec-dev-tooling,
livespec-orchestrator-beads-fabro and livespec-overseer. A PRIVATE user-owned App cannot be installed on an
organization. So, unless Phase 1 step 2 records that 5656677 can be installed there (a public App, or one the organization
owns), no repository transfers until an org-owned twin exists. The expected answer is that the twin is required: the incident
plan's 19:36Z item on this epic records 5656677 installed on the personal account. The twin must be installed on the
organization, and the rehearsal must prove that a transferred repository's ruleset bypass resolves to it. A bypass
that does not survive the transfer would remove incident recovery DURING the move, which is exactly when the maintainer
wants expedited incident response available.

**Phase 1 — preparation, while priorities 1-3 run (no repository moves):**
1. The maintainer creates the organization with these settings:
   - fork-PR approval at `all_external_contributors`;
   - an Actions policy;
   - member repository-creation off;
   - default `GITHUB_TOKEN` read-only.
2. **Read the recovery App's owner and record the answer.** Run
   `gh api /apps/thewoolleyman-incident-recovery --jq '{owner: .owner.login, type: .owner.type}'` (the slug the incident
   plan recorded), plus the App's settings page for its public or private flag, and record both as a scope event on this
   epic. This is not measured yet. On 2026-11-12 the coordinator's `gh api user/installations` returned 403, and at 21:17Z
   the seat's `/apps/<slug>` read returned 404 and then hit the token's rate limit. A private App owned by the user
   account cannot be installed on an organization, so that answer makes the §3 twin REQUIRED.
3. Create a private, org-owned fleet App, installable only on the organization, as the homelab constraint requires for
   `mi-homelab-factory-bot`. Create the recovery App's org twin as well, unless step 2 recorded that 5656677 can be
   installed on the organization. Keys go into the 1Password environment.
4. **Publish the images under the organization.** The organization exists from step 1, so publish (or mirror)
   `livespec-fabro-sandbox` and every other fleet image at `ghcr.io/<org>/<name>`, at each tag the held PRs pin. Make
   each package readable by the repositories that pull it. The quiet check (§2) reads "image present at
   `ghcr.io/<org>`" for each one.
5. **Rehearsal on a throwaway repository** (`thewoolleyman/livespec-transfer-rehearsal`). Seed it with:
   - a reusable workflow called from a second throwaway;
   - a ruleset with an Integration bypass;
   - an Actions secret and a variable;
   - a webhook;
   - a Release Please config;
   - an ARC registration;
   - a Claude marketplace and a Codex marketplace pointing at it;
   - a workflow that pulls an image from `ghcr.io/thewoolleyman/…`. Record whether the transferred repository can still
     pull the OLD package name, and grant the transferred repositories package access to it. Between a transfer and its
     held PR landing, master CI and the factory's `workflow.toml` still name the old image.

   Transfer it, then record which of these survive the transfer and whether the old `uses:`, git and marketplace
   references still resolve. Then test whether it can be transferred BACK: the namespace-retirement rule may forbid
   reusing the old name. This settles every "verify" in note 004 before a real repository moves.
6. **Specification first:**
   - a livespec propose-change replacing v126's "no merge queue" with "merge queue on organization-owned repositories";
   - the manifest `owner` change;
   - a Fork-exclusion amendment if `merge_group` runs on guarded self-hosted runners;
   - the matching dev-tooling spec changes (`self_hosted_routing`, `branch_protection_alignment`, the `merge_group`
     trigger).

   Each is revised and ratified before its code.
7. **Draft PRs, held unmerged**, one per repository, carrying the code and config changes:
   - note 004's ~300 lines, the owner constants and the two silent-break comparisons;
   - `.claude/settings.json` marketplaces;
   - GHCR names;
   - `merge_group` plus routing;
   - ARC values.

   **These PRs cannot be fully green before the halt.** They run in thewoolleyman-owned repositories until the transfer,
   so an owner-bound check fails by construction. The checks that MAY be red before the transfer, and why:
   - **Owner-equality checks.** livespec's `reusable-spec-pr-merge-policy.yml` prefix test now expects
     `<org>/livespec/.github/workflows/…`, but the run's `job_workflow_ref` still says `thewoolleyman/…`. Any test or
     check that compares a changed owner constant (`FLEET_OWNER`, `OWNER`, `EXPECTED_APP_OWNER`, the manifest `"owner"`)
     with the live repository's owner fails the same way.
   - **Live reads by `<org>/<repo>`.** These include the fleet audit reading the manifest by owner and name, the
     git-identity audit and branch-protection alignment. Each one 404s, because no repository exists at the org name
     yet.
   - **Anything that calls a reusable workflow or action at `<org>/livespec-dev-tooling/…@vX`.** That ref does not
     resolve until the transfer and the dev-tooling release in Phase 3.

   Image pulls from `ghcr.io/<org>` are NOT on this list, because step 4 publishes the images first. A pull that is red
   is a defect to fix before the halt.

   **What proves each PR good before the halt:**
   - every required check outside the three classes above is green on the PR;
   - the PR body names each red check, by job name, together with its class;
   - each owner-bound check is proven green against the rehearsal repository after that repository moves to the
     organization (step 5), by running the same check with the org owner against an org-owned repository.

   After the transfer, each PR must be fully green before Phase 3 step 6 lands it.

**Phase 2 — the halt (§2), announced by the coordinator.**

**Phase 3 — cutover window:**
1. Transfer the 10 repositories back to back.
2. Install the org App(s) on them, and re-project APP_ID and APP_PRIVATE_KEY in every repository.
3. Re-point the recovery rulesets' bypass actor if it changed.
4. Re-check the observer webhook.
5. Re-converge the 15 ARC registrations, and authorize the controller on the organization.
6. Land the held PRs in dependency order:
   - livespec-dev-tooling first: checks, reusable workflows and a release;
   - livespec (the manifest `owner`);
   - then the other eight, through the pin bump.
7. Re-register the marketplaces on every host, through the per-host ensure-plugins path: Claude `known_marketplaces`,
   `installed_plugins` and Codex `config.toml`.
8. Re-point the 12 adopters' `.claude/settings.json`.

**Phase 4 — the merge queue:**

`.ai/coordinator-duties.md` §12 carries "never offer GitHub's merge queue". This phase does not breach it. The
maintainer chose the org move and the adoption of GitHub's merge queue, in the scope event on this epic at
2026-11-12T19:34:25Z ("OK, we are going to go with the org move"). The seat had presented the organization path because
the maintainer asked how option 3 compared with GitHub's merge queue.

1. Enable "require merge queue" on livespec-dev-tooling and the orchestrator, with build concurrency of 2 or more
   (note 003's sensitivity: a single lane is fragile on dev-tooling).
2. Run the semantic-conflict drill (assertion 4 below).
3. Run one factory dispatch end to end.

**Phase 5 — lift the halt.** Re-dispatch the cancelled runs, and watch master health and queue latency for 24 hours
against note 003's numbers.

**Rollback.** Before Phase 4, transferring back to the personal account is the rollback, if the rehearsal proves it
possible. After Phase 4, disable the merge-queue requirement; nothing else depends on it.

## 4. Draft Definition of Done (for the maintainer to confirm; replaces the session-derived "investigate" DoD)

- All 10 fleet repositories are owned by the new organization, and each `github.com/thewoolleyman/<repo>` URL redirects
  to it.
- Every adopter repository stays owned by its current account (thewoolleyman or mi-homelab).
- On livespec-dev-tooling and livespec-orchestrator-beads-fabro, master requires the merge queue, and a pull request
  armed for auto-merge lands on master only through the queue.
- Two pull requests that each pass CI alone but break CI together cannot both land: the queue ejects the second one,
  and master stays green.
- After the move, factory dispatch, release fan-out and a pin bump each complete once against the organization's
  repositories, and master CI is green in all 10.
- The recovery drill passes once on livespec-dev-tooling after its transfer. The recovery App's org twin (or 5656677, if
  Phase 1 step 2 recorded that it can be installed on the organization) pushes one commit directly to master through
  the `master-incident-recovery-bypass` ruleset. The commit lands. In the same drill the maintainer's own token is
  refused a direct push to master by the ruleset. The drill does not wait for a real incident.
- In the committed tree of each of the 10 fleet repositories at master, one committed grep counts 0 occurrences of
  `github.com/thewoolleyman/<fleet-repo>` and 0 of `ghcr.io/thewoolleyman`. The grep is
  `plan/stale-base-merge-options/research/data/org-move/old_owner_refs.py.txt`, run against each repository's
  `origin/master` tree. It grades configuration only, so it excludes every `history/` and `archive/` tree, live `plan/`
  research notes (counted separately as narrative links) and release-generated `CHANGELOG.md`. Baseline, 2026-11-13
  ~00:2xZ: 698 graded occurrences in 289 files, beside 659 informational bare `thewoolleyman/<fleet-repo>` slugs
  (`uses:` refs, marketplace `repo:` entries). Those slugs also lean on the redirect, and the maintainer may want them
  graded too. Any non-zero count means the move still depends on GitHub's redirects, which break
  the day someone reuses the old name.
- On every fleet host, Claude Code and Codex resolve the fleet marketplaces at the organization's names.
- Merge-queue CI runs on the runners the maintainer chose, and the self-hosted routing check passes in all 10
  repositories.

## 5. Maintainer calls (needed before Phase 1)

1. **The organization's name.**
2. **Approve the outward-facing grants:**
   - a new private org-owned fleet App, plus an org twin of the recovery App 5656677. The twin is required unless
     Phase 1 step 2 records that 5656677 can be installed on the organization; a private user-owned App cannot be, and
     that is the expected answer;
   - publishing images under `ghcr.io/<org>`.
3. **Where `merge_group` CI runs:** guarded self-hosted runners (the seat's pick; a security-policy change) or
   GitHub-hosted runners (a free org's 20-job concurrency cap, shared by all its repositories; latency unmeasured).
4. **Confirm or edit the Definition of Done above.**
