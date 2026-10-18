---
topic: delegated-gate-emits-outcome-telemetry
author: claude-opus-5-5
created_at: 2026-10-18T19:31:06Z
---

## Proposal: Every delegated gate run emits one outcome event: passed, failed-tree or no-verdict

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a "Telemetry" bullet to `SPECIFICATION/contracts.md` §"Delegated pre-push gate", plus two scenarios in `SPECIFICATION/scenarios.md`. Every delegated gate run emits exactly one outcome event (an OTLP span) to the fleet observability surface. Its outcome is `passed`, `failed-tree` or `no-verdict`, and it carries the repository's name, the gated tree's hash and the gate Job's name as separate attributes. A telemetry failure never changes the push's verdict or the client's exit status, and the fleet carries a trigger that fires on a `no-verdict` outcome. The point is that a delegation which could not gate can be told apart from a failing tree somewhere other than the push's own log.

### Motivation

Work-item `livespec-dev-tooling-cmgqnz` (child of plan `delegated-gate-fleet-rollout`, epic `livespec-dev-tooling-mvalxq`) records the gap. The archived livespec plan `k3s-on-gmktec-for-vps-usage` (epic `livespec-sab5gn`) required, in its 2026-09-08 scope event R4.R7 and in its research note 003 section I, that monitoring arrive with the delegated gate. It also required that a no-verdict refusal be distinguishable from a red tree, "or a broken delegation reads as a failing repository". The gate client's own output keeps the two apart, but only in the log of the push that produced it. That plan's second independent completeness review (evidence id `k3s-on-gmktec-completeness-2026-10-13b`) found no monitoring signal for it.

The work-item's Definition-of-Done grading of 2026-10-18 failed because no clause of this repository's spec covers gate telemetry. §"Delegated pre-push gate" covers opt-in, host eligibility, what the gate runs, the verdict, and credentials. §"Runner-pool cache telemetry" in `non-functional-requirements.md` governs the pool's cache spans and triggers, not gate outcomes. This proposal adds that clause inside the existing section, so the item's `References:` heading resolves and every assertion the item makes is derivable from it.

Two decisions are stated explicitly rather than left open. First, the outcome names the gate's verdict, not the push's disposition. The gate client can refuse a push after a green verdict, when `HEAD` has moved off the gated tree or the token cannot be written. That case emits `passed`, so `no-verdict` keeps meaning exactly "no verdict was obtained", which is what the trigger alerts on. Second, an attribute the run never determined is omitted rather than guessed, because a run can stop before it has read the tree or named the repository. The trigger is required here because this repository already keeps Honeycomb triggers as code under `ci-runner/observability/triggers/`. The bullet names no particular file, so it does not go stale if that layout moves. Any change the receiving collector's configuration needs before it forwards these events belongs to the otel-collector repository and is outside this spec target.

### Proposed Changes

One new bullet in `SPECIFICATION/contracts.md` §"Delegated pre-push gate" and two new scenarios in `SPECIFICATION/scenarios.md`. Each anchor below is quoted verbatim from the files as they stand.

**Edit 1 — a new "Telemetry" bullet.** Insert the following bullet immediately after the section's "Credential installation" bullet, which reads:

> - **Credential installation.** The `gates_kubeconfig` Ansible role installs the gates kubeconfig owned by root and by a declared gate-client group that contains the login user of each delegating host, at mode `0640`. The credential is never world-readable, and a refresh replaces the file atomically, leaving the replacement with that same owner, group, and mode.

so that it becomes the section's last bullet:

> - **Telemetry.** Every delegated gate run MUST emit exactly one outcome event, as an OTLP span, to the fleet observability surface named in `non-functional-requirements.md` §"Runner-pool cache telemetry". A delegated gate run is each `run` invocation of the gate client made by a push that has delegated. A push that takes the local fall-through starts none. The event's outcome is `passed` when the gate Job reported a green verdict for the tree, `failed-tree` when the gate Job reported a red verdict, and `no-verdict` when the run obtained no verdict, including a run that stopped before any gate Job was submitted. The outcome names the gate's verdict, not what happened to the push. A green verdict on which the push is still refused, because `HEAD` no longer names the gated tree or the green token could not be recorded, therefore emits `passed`. The event MUST carry the repository's name, the gated tree's hash, and the gate Job's name as separate attributes. A value the run had not determined when it stopped MUST be absent from the event, never guessed. Emission is best-effort. When the event cannot be delivered, the run MUST still report the same verdict and exit with the same status it would have reported with telemetry working, and it MUST NOT wait on delivery for longer than a bounded attempt. A telemetry failure therefore never changes whether a push completes. The fleet MUST carry a trigger that fires on a `no-verdict` outcome event, so that a broken delegation is alertable apart from a failing tree. Its description MUST name the emitter path, the receiver path, the owning work-item, and a runbook.

**Edit 2 — two new scenarios.** Insert the following two scenarios into `SPECIFICATION/scenarios.md` immediately after the scenario `## Scenario: a delegated gate Job for a repository missing its declared recipe reports red naming the recipe` (that is, before `## Scenario: the fabro-hosts play renders the factory registry from the inventory's factory names`):

> ## Scenario: a delegated gate run that reaches no verdict emits a no-verdict outcome event
>
> Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`
>
> And a pushing host where the pushing user can read the gates kubeconfig
>
> And the cluster's API server is unreachable from that host
>
> When a git push of a tree that has no green token runs the pre-push gate
>
> Then the push MUST be refused
>
> And the gate client MUST emit exactly one outcome event whose outcome is `no-verdict`
>
> And that event MUST carry the repository's name, the gated tree's hash, and the gate Job's name
>
> ## Scenario: a delegated gate verdict is unchanged when its outcome event cannot be delivered
>
> Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`
>
> And a pushing host where the pushing user can read the gates kubeconfig
>
> And the gate Job for the committed tree at the pushing worktree's `HEAD` reports a green verdict
>
> And no receiver accepts the run's outcome event
>
> When a git push of a tree that has no green token runs the pre-push gate
>
> Then the push MUST complete
>
> And the gate client MUST report the same verdict, and exit with the same status, that it reports when the outcome event is delivered

**Ratification mechanics (for the revise payload, not spec text).** This proposal adds no `## ` heading to `contracts.md`; the "Telemetry" bullet sits inside the existing §"Delegated pre-push gate", so a work-item whose `References:` line names that heading keeps resolving. It adds exactly two `## ` headings to `scenarios.md`:

- `## Scenario: a delegated gate run that reaches no verdict emits a no-verdict outcome event`
- `## Scenario: a delegated gate verdict is unchanged when its outcome event cannot be delivered`

The revise payload MUST carry, as `../tests/heading-coverage.json` in `resulting_files[]`, one `TODO` row for each, with `spec_root` `SPECIFICATION`, `spec_file` `scenarios.md`, `work_item` `livespec-dev-tooling-cmgqnz`, and a `reason` naming the integration tier (for example: "A real test at the integration tier or above is owed for this heading; livespec-dev-tooling-cmgqnz owns it."). The heading-coverage debt register MUST be regenerated, never hand-edited.
