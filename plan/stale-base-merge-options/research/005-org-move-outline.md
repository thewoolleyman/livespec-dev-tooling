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
  and its four rulesets need the new actor id. **Verify which account owns 5656677 before the cutover.**
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
- No gate Job is on the ARC runners.
- No release is mid-flight.

**Quiet check (the gate to start the cutover):** all of the above read live by one script. The seat writes the script
during preparation and reports its output to the coordinator.

## 3. Cutover outline

**Phase 0 — maintainer calls (§5), before anything else.**

**Cutover blocker (coordinator, 2026-11-12 ~20:0xZ): the recovery App's org twin.** No repository transfers until the
recovery bypass actor has an org-owned twin, Integration 5656677 in the `master-incident-recovery-bypass` rulesets of
livespec, livespec-dev-tooling, livespec-orchestrator-beads-fabro and livespec-overseer. The twin must be installed on
the organization, and the rehearsal must prove that a transferred repository's ruleset bypass resolves to it. A bypass
that does not survive the transfer would remove incident recovery DURING the move, which is exactly when the maintainer
wants expedited incident response available.

**Phase 1 — preparation, while priorities 1-3 run (no repository moves):**
1. The maintainer creates the organization with these settings:
   - fork-PR approval at `all_external_contributors`;
   - an Actions policy;
   - member repository-creation off;
   - default `GITHUB_TOKEN` read-only.
2. Create a private, org-owned fleet App, installable only on the organization, as the homelab constraint requires for
   `mi-homelab-factory-bot`. Do the same for the recovery App if 5656677 is user-owned. Keys go into the 1Password
   environment.
3. **Rehearsal on a throwaway repository** (`thewoolleyman/livespec-transfer-rehearsal`). Seed it with:
   - a reusable workflow called from a second throwaway;
   - a ruleset with an Integration bypass;
   - an Actions secret and a variable;
   - a webhook;
   - a Release Please config;
   - an ARC registration;
   - a Claude marketplace and a Codex marketplace pointing at it.

   Transfer it, then record which of these survive the transfer and whether the old `uses:`, git and marketplace
   references still resolve. Then test whether it can be transferred BACK: the namespace-retirement rule may forbid
   reusing the old name. This settles every "verify" in note 004 before a real repository moves.
4. **Specification first:**
   - a livespec propose-change replacing v126's "no merge queue" with "merge queue on organization-owned repositories";
   - the manifest `owner` change;
   - a Fork-exclusion amendment if `merge_group` runs on guarded self-hosted runners;
   - the matching dev-tooling spec changes (`self_hosted_routing`, `branch_protection_alignment`, the `merge_group`
     trigger).

   Each is revised and ratified before its code.
5. **Draft PRs, held unmerged**, one per repository, carrying the code and config changes:
   - note 004's ~300 lines, the owner constants and the two silent-break comparisons;
   - `.claude/settings.json` marketplaces;
   - GHCR names;
   - `merge_group` plus routing;
   - ARC values.

   Each is green on CI before the halt.

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
7. Publish the images under the organization.
8. Re-register the marketplaces on every host, through the per-host ensure-plugins path: Claude `known_marketplaces`,
   `installed_plugins` and Codex `config.toml`.
9. Re-point the 12 adopters' `.claude/settings.json`.

**Phase 4 — the merge queue:**
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
- After the move, factory dispatch, release fan-out, pin bumps and the incident-recovery path each complete once
  against the organization's repositories, and master CI is green in all 10.
- On every fleet host, Claude Code and Codex resolve the fleet marketplaces at the organization's names.
- Merge-queue CI runs on the runners the maintainer chose, and the self-hosted routing check passes in all 10
  repositories.

## 5. Maintainer calls (needed before Phase 1)

1. **The organization's name.**
2. **Approve the outward-facing grants:**
   - a new private org-owned fleet App, plus a recovery App if 5656677 is user-owned;
   - publishing images under `ghcr.io/<org>`.
3. **Where `merge_group` CI runs:** guarded self-hosted runners (the seat's pick; a security-policy change) or
   GitHub-hosted runners (a free org's 20-job concurrency cap, shared by all its repositories; latency unmeasured).
4. **Confirm or edit the Definition of Done above.**
