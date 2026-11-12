---
topic: the-incident-execution-resolver-does
author: claude-fable-5-1
created_at: 2026-11-12T10:55:43Z
---

## Proposal: Incident enablement is a record the independent controller holds, bound to the committed manifest identity and read by the execution resolver at every vantage

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The one incident enablement step's durable output becomes an enablement record held by the independently hosted released controller installation that serves the repository, in that installation's protected state, written only through the controller's control-credentialed route after the step's own fresh audit listed the repository ready, and bound to the repository, the committed manifest identity and the step's immutable operation identity. The controller serves the record through a read-only query route that re-authenticates the committed manifest identity against livespec core's default branch at every answer. The execution resolver at every vantage where incident mode resolves - the dev-host hooks, the incident CI entrance on the runner and the controller host's own arm, current and admitted entrances - reads that record after an incident flag has selected a non-normal mode and before it produces an incident context, and a record bound to another manifest identity reads as not enabled everywhere. This supersedes the dev-host-local file the step writes today, which the CI runner and the controller cannot read.

### Motivation

Work item livespec-dev-tooling-2xxnku (plan expedited-incident-response-flag, epic livespec-dev-tooling-bqnzcm; spec-change tier recorded 2026-11-10T23:59:33Z against spec v185, generalization target `## Expedited incident execution`; coordinator cut 2026-11-12 10:41Z). The ratified closing paragraph of that section says incident use MUST be enabled only through one enablement step that reads the audit's ready list. It does not say the execution resolver refuses an incident flag in a repository that step has not enabled, does not name an enablement record, does not bind that record to the manifest identity at resolution time, and does not require the record to be read at the dev-host, CI-runner and controller vantages. The carrier (review finding F7 on livespec-dev-tooling#3964) is that enablement must take EFFECT.

Today `just incident-enable` writes `~/.local/state/livespec/incident-enabled/<owner>__<repo>.json` on the dev host (`livespec_dev_tooling/incident_fleet_cli.py`). Incident mode resolves at three vantages (`incident_hook_entry.py` on the dev host, `incident_ci_entry.py` in a runner pod, the observer on the controller host), and two of them cannot read a dev-host file, so wiring the resolver to it would refuse every incident run outside the dev host. The question the proposal settles is WHERE the record lives so that every vantage can read it, bound to the committed manifest identity, written by nothing an agent can forge.

Candidates weighed from the code and docs:

- A dev-host-local file (today): unreadable by the runner pod and the controller. Rejected.
- A committed file in the governed repository: writable by any pull request, and the fleet bot arms auto-merge on every pull request within seconds, so a factory worker or a repair branch can land or carry it; the hook and the CI runner read a candidate tree that the repair itself edits; and verifying it would need the very audit it stands in for. Rejected.
- A repository variable: settable by any session holding the maintainer's `gh` identity; the controller's forge credential is a `contents: read` App token that cannot read variables; and `docs/incident-execution.md` already forbids persisting incident state in repository settings, while the plan's master rule holds regardless of repository variables. Rejected.
- A ledger (tenant) record through the orchestrator's incident authority: writable by any session that holds the credential wrapper; the runner pod has no tenant credential and reaches the tenant only through the controller's query routes anyway; and the verb would belong to the orchestrator's repository, a cross-repo dependency for a record this repository's audit produces. Rejected.
- A record the independently hosted released controller holds and serves: chosen. The controller is already the component every vantage trusts for incident admission (the CI entrance reads its `/current` and `/admitted`; the dev host and the controller read the same canonical authority; `/arm` is the last point before an expedited merge). Its protected state is outside candidate checkouts, the tenant, credential projection, factory and gates namespaces, owned by the controller account, and it survives controller restarts and releases. Its control credential is the existing boundary for every incident control write (`/arm`, `/invalidate-ci`, `/recover`, `/reconcile`); it reaches no CI pod, factory worker or candidate tree, and it is projected on the operator's host by the credential wrapper (measured 2026-11-12: `LIVESPEC_INCIDENT_CONTROL_SECRET` and `LIVESPEC_INCIDENT_QUERY_SECRET` are projected on vps), so the enablement step can present it and the hooks can present the read-only query credential. livespec core is a public repository, so the controller, the hooks and the step each re-authenticate the committed manifest identity with an anonymous read of core's default branch, exactly as the audit reads it twice today. Which repositories an installation serves is already committed configuration (`master_health_observer.OBSERVED_REPOSITORIES`, pinned by test to the observer role), so the hook can name the installation it asks without any caller-steerable input.

### Proposed Changes

Append the following paragraphs to `SPECIFICATION/contracts.md` §"Expedited incident execution", directly after its closing paragraph (the one ending "naming the repository and the missing evidence the audit's findings record for it.").

```text
The enablement step's only durable output is an incident enablement record held by the independently hosted released controller installation that serves the repository, in that installation's protected state, outside candidate checkouts, the tenant, credential projection, factory and gates namespaces. The record MUST bind the repository, the committed manifest identity the step's audit authenticated (the digest of livespec core's committed `.livespec-fleet-manifest.jsonc` as read from core's default branch), the step's immutable operation identity, and the controller release and revision that retained it. It MUST be written only through the controller's control-credentialed route, by the enablement step, after that step's own fresh audit has listed the repository ready. The controller MUST refuse the write, retaining nothing, when the request names a repository other than its configured repository, when its own fresh read of core's default branch, taken twice, does not confirm the identity the request names, or when the request's operation identity was already retained with different bytes; an exact retry MUST answer the retained record without writing again. When the controller refuses or cannot be reached, the step MUST exit non-zero, enable nothing and name the refusal. A revocation written through the same control-credentialed route is the disable; a record superseded by a later record or by a revocation MUST read as absent. No dev-host file, repository file, repository variable, forge label, environment variable, pull-request body or ledger record MAY stand in for the record, and a record held by a scratch installation MUST NOT enable incident use for `master`.

The controller MUST serve the record through a read-only query route that answers only an exact query naming the repository. At every answer it MUST re-authenticate the committed manifest identity with a fresh read of core's default branch, MUST answer `enabled` only when the retained record binds its configured repository and that identity, and MUST echo the query, the identity it confirmed and the installation's arming state; an unavailable read of core's default branch MUST answer `unavailable`, never `enabled`. The reading at any vantage is exactly one of `enabled`, `absent`, `stale` (a record bound to another manifest identity), `revoked`, `unavailable` or `no-installation`.

At every vantage where incident mode resolves - the dev-host hooks, the incident CI entrance on the runner and the controller host's own arm, current and admitted entrances - the execution resolver MUST read the enablement record after an incident flag has selected an expedited-repair or emergency-revert mode in an ordinary invocation and before it produces that context. A trusted normal-master or normal-factory-follow-up origin, and an invocation in which both flags are absent, MUST NOT read it. The dev-host hooks MUST ask the installation that this library's committed configuration names for the repository, kept equal to the observer role's inventory by test, through the credential wrapper's projected read-only query credential, and MUST compare the identity the controller confirmed against their own fresh read of core's default branch, reading `stale` on any difference; a repository that no installation serves reads `no-installation`. The incident CI entrance MUST take its reading from the same query route at plan time, and the controller's current and admitted answers MUST themselves refuse while the installation is armed and the reading is not `enabled`, so that an entrance that did not ask is still fenced before CI omission and before merge. The controller MUST consult its own record before it arms and MUST record the reading in the arm receipt. A record bound to a manifest identity other than the one a fresh read of core's default branch confirms MUST read as not enabled at every vantage.
```

Add the following scenario to `SPECIFICATION/scenarios.md`, after `## Scenario: the incident fleet audit command refuses enablement for a consumer without verified serving evidence`, its body wrapped in a ```gherkin fence as the neighbouring scenarios are:

```text
## Scenario: the incident enablement step records enablement on the independent controller and every vantage reads it

Given a repository the fleet audit lists ready, served by a production controller installation whose fence is disarmed
When the operator runs the enablement step for that repository
Then the step MUST write one enablement record through the controller's control-credentialed route, binding the repository, the committed manifest identity the step's audit authenticated and the step's operation identity
And the controller MUST confirm that identity with its own fresh read of livespec core's default branch before it retains the record, and an exact retry MUST answer the retained record without writing again
And a later expedited commit in that repository MUST read the record through the installation this library's committed configuration names, compare the confirmed identity against the hook's own fresh read of core's default branch, and record `enabled` in its receipt
And the incident CI entrance MUST record `enabled` in its plan from the controller's answer, and the controller MUST record `enabled` in its arm receipt
And no dev-host file, repository file, repository variable, forge label, pull-request body or ledger record MAY be read as the enablement.
```

Each new `## Scenario:` heading this proposal adds MUST be entered in `tests/heading-coverage.json` in the revise commit as a spec-first `"test": "TODO"` row whose `reason` names the integration tier and whose `work_item` is `livespec-dev-tooling-2xxnku`, with `tests/heading-coverage-debt.json` regenerated, per the repository's revise co-edit discipline.


## Proposal: The enablement fence takes effect only when armed, is armed per repository only after that repository is enabled, and reads in shadow until then

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The refusal the record enables is a fence that takes effect only when armed. Arming is an explicit control-credentialed write per controller installation, for the installation's configured repository, which the controller refuses while it holds no enablement record bound to the current committed manifest identity, so a repository's fence is armed only once that repository is enabled. An armed fence stays armed through later manifest changes and refuses until the step records the repository again; disarming is an explicit retained write. While disarmed, every vantage still reads the record and records the reading in the artefact it already produces (the hook receipt, the CI plan, the arm receipt) and refuses nothing. The rollout order for this repository - readers and routes first, then the fleet inventory, then enablement, then a drill, then arming - keeps the plan's first Definition of Done bullet true for livespec-dev-tooling throughout.

### Motivation

On 2026-11-11 the coordinator moved livespec-dev-tooling-2xxnku off plan expedited-incident-response-flag because arming the fence now would refuse incident mode in livespec-dev-tooling itself: that repository cannot be on the audit's ready list until its controller, recovery and driver-hook rows carry real implemented claims (the fleet inventory is carried by livespec-dev-tooling-bqnzcm.3). On 2026-11-12 the plan owner re-parented the item as the carrier of completeness-review gap G2 with the explicit cut that the proposal must state the ordering. CLAUDE.md §"Ordering - confirm the reader before you write" applies twice: a check armed before the repositories it judges have adopted the shape writes verdicts into a fleet that cannot satisfy them (the Railway decoupling that turned five repositories red), and durable state must never be written into a component not yet running the code that preserves it (the ConfigMap that stayed stale for two hours). The ratified text already sequences the feature as "Ship contract/readers normally, release, adopt, prove recovery capability and only then enable use"; this proposal gives the enablement fence the same shape, with the shadow reading as the proof that each vantage's reader works before any of them may refuse, and with the arming write refused by any controller release that lacks the route, so it cannot land in a reader that does not preserve it. The plan's first Definition of Done bullet - an operator can activate EXPEDITED_INCIDENT_RESPONSE for one identified incident work item and deliver its fix from a local worktree through an expedited PR without a factory run or a green-master precondition blocking that repair - must stay true for livespec-dev-tooling at every step of the transition.

### Proposed Changes

Append the following paragraphs to `SPECIFICATION/contracts.md` §"Expedited incident execution", directly after the paragraphs the preceding proposal adds.

```text
The refusal is a fence that MUST take effect only when armed. Arming is per controller installation, for the installation's configured repository, and MUST be an explicit write through the controller's control-credentialed route, retained in protected state with its operation identity. The controller MUST refuse the arming write while it holds no enablement record bound to the current committed manifest identity, so that a repository's fence is armed only once that repository is enabled. An armed fence MUST stay armed when core's committed manifest identity later moves; the remedy is to run the enablement step again, and until a new record binds the current identity the resolver MUST refuse incident mode in that repository, naming the stale record. Disarming MUST be an explicit write through the same route, retained as a receipt, and MUST never happen implicitly. A controller release that lacks the enablement, arming or query route MUST refuse the corresponding request as an unknown route, so that neither the record nor the arming can land in an installation whose code does not preserve it.

While an installation is disarmed, every vantage MUST still read the record and MUST record its reading in the artefact it already produces for the operation (the hook's receipt, the CI plan, the arm receipt), and MUST NOT refuse on that reading; this shadow reading is the evidence that the reader at each vantage works before any of them may refuse. While an installation is armed, the resolver at every vantage MUST refuse incident mode with a named configuration refusal naming the repository, the installation and the reading (`absent`, `stale`, `revoked`, `unavailable` or `no-installation`) whenever the reading is not `enabled`; the refusal MUST terminate the operation and MUST NOT fall through to normal mode with an incident flag set.

For this repository, the only repository exercising incident mode and one the audit cannot list ready until its controller, recovery and driver-hook rows carry implemented claims, the order MUST be: the record store, the three routes, the step's write and the readers at the three vantages ship normally and reach the production installation through the committed observer role, disarmed, while every incident operation in this repository keeps resolving as before and records `absent`; the fleet inventory classifies this repository's rows and the audit lists it ready; the enablement step records it; a scratch-branch drill, with the scratch installation enabled through its own route, shows `enabled` in the hook receipt, the CI plan and the arm receipt; and only then is the production installation armed. Until the arming write is made, an operator MUST remain able to activate EXPEDITED_INCIDENT_RESPONSE for one identified incident work item in this repository and deliver its fix through an expedited pull request without a factory run or a green-master precondition blocking that repair, because the fence refuses nothing before it is armed and it is armed only after the repository is enabled.
```

Add the following two scenarios to `SPECIFICATION/scenarios.md`, directly after the scenario the preceding proposal adds, each body wrapped in a ```gherkin fence as the neighbouring scenarios are:

```text
## Scenario: an armed enablement fence refuses incident mode without a current enablement record

Given a production controller installation whose fence is armed for its repository
When EXPEDITED_INCIDENT_RESPONSE=1 selects repair in an ordinary invocation of that repository's dev-host hook, incident CI entrance or controller arm
Then with no retained record the resolver MUST refuse with a named configuration refusal naming the repository, the installation and the missing record, and MUST NOT fall through to normal mode
And with a record bound to a manifest identity other than the one a fresh read of core's default branch confirms, it MUST refuse naming the stale record
And with a revoked record, or when core's default branch cannot be read, it MUST refuse naming the revocation or the unavailable read
And a trusted normal-master or normal-factory-follow-up origin, and an invocation with both flags absent, MUST NOT read the record at all.

## Scenario: the enablement fence is armed for a repository only after that repository is enabled

Given a repository the fleet audit does not yet list ready, served by a disarmed production installation running a controller release that carries the enablement routes
When an operator attempts to arm the installation
Then the controller MUST refuse the arming write, because it holds no enablement record bound to the current committed manifest identity
And every incident operation in that repository MUST keep resolving as before, recording `absent` in the hook receipt, the CI plan and the arm receipt and refusing nothing
And once the audit lists the repository ready and the enablement step has recorded it, the arming write MUST succeed and the fence MUST stay armed through a later change of core's committed manifest identity, refusing incident mode until the step records the repository again
And a controller release that lacks the routes MUST refuse both the enablement write and the arming write as unknown routes.
```

