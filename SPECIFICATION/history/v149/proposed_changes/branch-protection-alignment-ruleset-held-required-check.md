---
topic: branch-protection-alignment-ruleset-held-required-check
author: claude-opus-5-5
created_at: 2026-11-07T14:14:11Z
---

## Proposal: branch_protection_alignment reads the effective required-check set, including a ruleset-held check whose only bypass is a GitHub App

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The `branch_protection_alignment` check, the fleet `branch-protection` assert row and the fleet reconcile today read and write ONLY classic branch protection. livespec's incident policy requires the recovery principal to be authorized against every overlapping classic protection or ruleset rule, and GitHub never lets a ruleset bypass exempt an actor from a classic rule. So the incident recovery App can merge its inverse only when the all-green gate check is required by a repository ruleset that names the App as its sole bypass actor, rather than by classic protection. This proposal makes the ALIGNMENT gate read the default branch's EFFECTIVE required-check set (the union of classic protection's required checks and every active ruleset's required-status-checks rule for that branch), applies the strict-off rule to both sources, holds every contributing ruleset's bypass list to the same standard `enforce_admins` holds classic protection to (only GitHub App bypass actors), and forbids the fleet reconcile from writing a classic required check a ruleset already holds.

### Motivation

Plan expedited-incident-response-flag, carrier livespec-dev-tooling-7536jf (the live recovery principal). On 2026-11-07 the maintainer provisioned the recovery GitHub App (App ID 5656677) and approved a master ruleset (26758787) whose only bypass actor is that App. livespec-dev-tooling's master still carries classic protection requiring `ci-green` with `enforce_admins` on. GitHub aggregates classic protection and rulesets and a ruleset bypass covers only that ruleset's rules, and the principal publishes by moving the master ref directly, so the classic required check would refuse every incident inverse. The coordinator decided (R301) to move `ci-green` out of classic protection into the ruleset, which keeps `ci-green` required for every actor except the App. livespec `SPECIFICATION/non-functional-requirements.md` §"CI as a merge gate (branch protection)" already ratifies the direction under its incident-only precedence paragraph: recovery-principal authorization MUST be explicit, narrow and proven against every overlapping protection rule, ordinary actors including administrators MUST remain subject to their existing required checks, and `branch_protection_alignment` MUST recognize only the exact authorized incident shape. livespec `SPECIFICATION/contracts.md` §"Expedited incident response policy" requires recovery-principal authorization against every overlapping classic protection or ruleset, and forbids disabling ordinary protection. This repository's own §"`branch_protection_alignment` check" still names only classic protection's `required_status_checks` object, so without this revision the check would report the moved configuration as `unrequired_leg_without_aggregate_gate` (an empty classic required list) and the fleet `branch-protection` row would report `required-check set is empty`, and a later `wire-fleet-member` run would PUT `ci-green` back into classic protection and silently undo the move. The change MUST land, and be released, BEFORE `ci-green` is removed from livespec-dev-tooling's classic protection.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"`branch_protection_alignment` check":

1. Replace the opening sentence of the ALIGNMENT gate paragraph ("Two-direction comparison between master's required-checks list and `ci.yml`'s `matrix.target` job names, plus an `enforce_admins`-on and a `strict`-off assertion:") with:

   "ALIGNMENT gate (outcome 1 only). The gate compares the default branch's EFFECTIVE required-check set against `ci.yml`. The effective set MUST be the union of (a) classic protection's `required_status_checks.contexts` and (b) the `context` of every entry of every `required_status_checks` rule that an ACTIVE repository ruleset applies to the default branch, read from `repos/{owner}/{repo}/rules/branches/{branch}` (that endpoint returns only rules whose ruleset enforcement is active, each carrying its `ruleset_id`). Every rule below that speaks of the required-checks list MUST read the effective set. A classic `required_status_checks` object whose `contexts` list is empty is valid when the ruleset contribution supplies the all-green gate. The gate runs a two-direction comparison plus an `enforce_admins`-on assertion, a `strict`-off assertion and a ruleset-bypass assertion:"

2. Extend the `strict` bullet: the `strict`-off rule MUST apply to BOTH sources. A contributing ruleset rule whose `parameters.strict_required_status_checks_policy` is `true` MUST FAIL with the same `failure_mode` `strict_enabled`.

3. Add a bullet after the `enforce_admins` bullet:

   "- A ruleset that contributes a required check MUST bind every actor except GitHub Apps. For each distinct `ruleset_id` contributing to the effective set, the check MUST read `repos/{owner}/{repo}/rulesets/{ruleset_id}`, and every entry of its `bypass_actors` MUST have `actor_type` `Integration` (a GitHub App identity — the incident recovery principal's shape per livespec `SPECIFICATION/contracts.md` §"Expedited incident response policy"). Any other bypass actor — a repository role, an organization admin, a team, a user or a deploy key — MUST FAIL (exit `4`, one `fail` finding per offending ruleset, `failure_mode` `ruleset_bypass_not_app`): it is the ruleset analogue of `enforce_admins` off, letting the accounts that do the merging merge past a red required check. A contributing ruleset that cannot be read, or whose body carries no `bypass_actors` list, MUST FAIL (`failure_mode` `ruleset_unreadable`) and MUST NOT take the outcome-3 graceful skip, for the same reason `enforce_admins_unreadable` does not: the classic read that preceded it proves the admin scope. A rules read that fails for any reason other than a ruleset fact MUST be treated as the ruleset contribution being unreadable, never as an empty contribution, and MUST FAIL with `ruleset_unreadable`."

4. Extend the exit-code list's `4` branch with `ruleset_bypass_not_app` and `ruleset_unreadable`.

5. Add one paragraph after the CI-token caveat:

   "Fleet surfaces read the same effective set. The fleet `branch-protection` assert row (§\"Fleet surface — central conformance and reconcile\") MUST apply the same union, the same strict-off rule to both sources and the same ruleset-bypass rule, and MUST NOT report `required-check set is empty` when the ruleset contribution is non-empty. The reconcile mode's branch-protection write MUST read the member's effective set first and MUST NOT write into classic `required_status_checks.contexts` any check an active ruleset already requires on that branch; it MUST still write `enforce_admins`, `required_linear_history` and `strict` off, since the classic object it PUTs replaces the whole protection. This holds for every fleet member, not only one repository: a member that holds its all-green gate in a ruleset whose only bypass actors are GitHub Apps is aligned."

In `SPECIFICATION/scenarios.md`, add a scenario:

## Scenario: branch protection alignment accepts a required gate held by a ruleset whose only bypass is a GitHub App

```gherkin
Given a repository whose classic protection on the default branch enforces admins, keeps strict off and requires no status check
And an active repository ruleset on that branch requires the all-green gate job with strict off and names only a GitHub App as a bypass actor
When branch_protection_alignment runs with an admin-scoped token
Then the effective required-check set contains the all-green gate and the check exits 0.
And the same configuration with a repository-role bypass actor added to that ruleset fails with failure_mode ruleset_bypass_not_app.
And the same configuration with the ruleset's strict policy enabled fails with failure_mode strict_enabled.
And a ruleset read that fails fails with failure_mode ruleset_unreadable rather than skipping.
```
