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
  run and never its jobs. Every cancel was refused: `gh run cancel` returned 409 "completed", and force-cancel returned
  409 "not queued yet". The per-run record is the comment on this epic at 2026-11-13T00:47:15Z.

  **The ghost rule** comes from legacy-coordinator-agent's rulings (b) and (i), as the coordinator clarified them in its
  grade of livespec-dev-tooling#4427. The ruling (i) record is the comment at 2026-11-13T01:55:48Z. A run is a ghost
  when all four of these hold:
  - its status is `queued`, NOT `pending` or `waiting`, because a concurrency group holds those runs and they will run;
  - `updated_at == created_at`;
  - it was created before the halt announcement (`--halt-at`);
  - it was created more than 24 h before the check runs.

  Its job count does not matter. That covers livespec-runtime 32215471962, which has one job on `ubuntu-latest`, and
  whose `updated_at` and `created_at` are both 2026-08-19T04:21:33Z. The quiet check reports each ghost with its id
  and never deletes it. A run younger than 24 h counts as active whatever its job count, so the rule still fails closed
  for anything recent.
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
- no gate Job for the repository is unfinished in the cluster's `gates` namespace.

Fleet-wide, it also checks that no unfinished gate Job matches no fleet repository, and that each `--image` is present
under `ghcr.io/<org>`. A Job is unfinished unless it carries a `Complete` or `Failed` condition, so a suspended Job or a
Kueue Job not yet admitted still counts.

It fails closed, and the script exits 0 only when the fleet is quiet. These count as NOT quiet:
- a read it cannot take;
- an error of any kind;
- a runs listing whose rows still disagree with GitHub's `total_count` after three reads, or that reaches the API's
  1,000-result cap;
- a PR listing that fills its page.

A missing `gates` namespace is caught by a server-side dry-run secret create, because the gates credential may not
read namespaces. It reads the fleet list from GitHub at
`<owner>/livespec@master`, not from a local working tree. `--self-test` checks its pure rules: the ghost boundary
rows, gate-Job attribution and the manifest parse. The seat reports its output to the coordinator. A live run at 2026-11-13T02:42:29Z, with `--halt-at` set to that
time and the fleet working normally, read NOT QUIET in 8 of the 10 repositories, as expected. It reported all 31
measured runs as ghosts and found no unattributed gate Job. That run is saved beside the script.

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
- In the committed tree of each of the 10 fleet repositories at master, one committed grep counts 0 references to the old
  owner. The grep is `plan/stale-base-merge-options/research/data/org-move/old_owner_refs.py.txt` (`--old-owner`
  defaults to `thewoolleyman`; it is never read from the manifest, whose `owner` names the organization after the
  move). It counts four forms of reference:
  - `github.com/thewoolleyman/<fleet-repo>`, in https, ssh and API forms;
  - `raw.githubusercontent.com/thewoolleyman/<fleet-repo>`;
  - `ghcr.io/thewoolleyman/`;
  - bare `thewoolleyman/<fleet-repo>` slugs: `uses:` refs, marketplace `repo:` entries and `--repo` arguments. The slugs
    are graded at the coordinator's direction, because they lean on the redirect just as URLs do.

  It reads each repository's `origin/master` tree and fetches only with `--fetch`. It grades configuration, so it
  excludes `SPECIFICATION/history/`, the root `archive/`, everything under `plan/`, and `CHANGELOG.md` files. Live plan
  notes are counted separately as narrative links. Baseline, 2026-11-13 ~02:4xZ: 1,374 graded references in 541 files.
  Of those, 480 are URLs, 6 are raw URLs, 219 are ghcr references and 669 are slugs. Any non-zero count means the move
  still depends on GitHub's redirects, which break the day someone reuses the old name. Raw URLs to non-fleet
  repositories, such as `thewoolleyman/otel-collector` (10 in dev-tooling), stay out of the count, because those
  repositories do not move.
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

   **Measured evidence, 2026-11-13: a stale-base semantic conflict reached master (incident 3hilpy).** The maintainer
   directed, through legacy-coordinator-agent on 2026-11-13, that this finding be presented WHENEVER this plan brings the
   maintainer its decisions. The records are the seat's comment on this epic at 06:33:05Z and the coordinator's
   "MAINTAINER-DIRECTED FINDING" comment.
   - livespec-dev-tooling#4442 (exdkra, fba395aae) merged at 05:32:32Z. It added a test that monkeypatches
     `incident_ci_process.load_inventory`.
   - livespec-dev-tooling#4449 (z5cjph, da0264ace) merged 87 s later, at 05:33:59Z. It moved `load_inventory` into
     `incident_ci_inventory.py`. It was green on base db9f57be9, which predates #4442.
   - Master CI run 43372854805 failed. Only the full suite caught it: `check-per-file-coverage`, about 11,900 tests,
     exactly one failing. Incident 3hilpy fixes it forward.

   A merge queue would have ejected #4449 only if both of these hold:
   - (a) `merge_group` CI runs the FULL suite, including `check-per-file-coverage`, not a fast subset;
   - (b) every path to master goes through the queue: factory merges, auto-merge and human merges. Expedited incident
     pushes also need a stated rule, because the recovery App's bypass skips the queue.

   A merge queue does NOT fix the incident-CI runner-admission defect, livespec-dev-tooling-ehnjlt. The fix that item
   owes is that an expedited incident's incident-ci job is admitted ahead of ordinary PR traffic in the dev-tooling
   runner pool. That is a runner-pool scheduling question, and it stays its own item whichever way this call goes.

   **The mechanism, and the non-queue option: "require branches to be up to date" (`strict`).** This finding came from the
   expedited-incident-response-flag plan's composed-red note on livespec-dev-tooling-3hilpy, and legacy-coordinator-agent
   relayed it on 2026-11-13. livespec-dev-tooling's master ruleset (26758787, `master-incident-recovery-bypass`) requires
   only `ci-green`, with `strict_required_status_checks_policy: false` (read by the seat on 2026-11-13). So a PR that is
   green on an old base merges without the composed tree being tested. That is exactly how #4442 and #4449 turned master
   red 87 s apart. Turning `strict` on is the direct alternative to a queue. Note 003 option (a) measured it over 28 days,
   and this week's numbers make it worse.
   - **Cadence, 2026-11-06T07:51Z to 2026-11-13T07:51Z (gh API).** livespec-dev-tooling merged 726 PRs, 103.7 a day,
     with a peak of 132 in one day. The median gap between merges was 6.5 min, and 43% of gaps were 5 min or less. Note
     003's 28-day window had 54.2 a day and a 10.1 min median gap, so the rate has roughly doubled.
   - **What one re-test costs (the latest 1,000 successful PR `ci.yml` runs; the listing hit its 1,000 cap, so this is
     a sample, not the whole week).** Wall-clock p50 was 22.5 min and p90 67.0 min.
   - **`strict` with a lazy, one-at-a-time updater** (note 003's row 2; Kodiak's model). Every merge has to wait for a
     full re-test on the current master, so merges are serialized at one per CI run. That is at most 64 merges a day at
     p50 and 21 at p90, against demand of 103.7 a day. The line can never drain, and latency grows without bound.
   - **`strict` with an eager updater** (note 003's row 1). Each merge sends every open armed PR behind master to update
     and re-run in full. There were 15 armed non-draft PRs open at the time of reading, so the estimate is about 15 extra
     full runs per merge, or about 1,560 a day against today's roughly 104. That is around 15 times today's CI. Note 003
     measured 30 times over its 28-day window. It is the N² treadmill the maintainer rejected on 2026-10-14.
   - GitHub's own update-branch MERGES master into the branch, so `strict` also needs a rebase updater bot. That is why
     v126 turned `strict` off and `allow_update_branch` is false fleet-wide (note 003).

   **The seat's recommendation: do not turn `strict` on, in either shape.** At this week's rate the serialized line
   cannot keep up, and the eager shape multiplies CI roughly fifteenfold. A batching merge queue, the direction the
   maintainer chose (§3 Phase 4), tests the composed tree at one full run per batch. It is the only option measured here
   that stops stale-base reds at an affordable cost, and only under conditions (a) and (b) above. Nothing on the ruleset
   was changed; `strict` is the maintainer's call.

   For this call, condition (a) means each queued batch runs the full suite. On GitHub-hosted runners, that competes for
   the free organization's 20 concurrent jobs. On the guarded self-hosted lane, it runs at today's measured capacity
   (note 003).
4. **Confirm or edit the Definition of Done above.**
