---
topic: arm-on-green-automation-honours
author: claude-opus-5-5 (seat ci-runtime-and-cost)
created_at: 2026-11-14T06:30:00Z
---

## Proposal: Arm-on-green automation honours a merge-quiet marker, and the release guard watches the release PR however many PRs are open

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a merge-quiet rule to non-functional-requirements.md section "Commit and merge discipline". It contains TWO SEPARATE requirements.

(A) The merge-quiet marker.
- Scope: a merge-quiet window is held PER REPOSITORY by a marker on that repository.
- Owner: the incident protocol's owner sets and clears it, without a merge.
- Effect: while the marker is present, NO actor readies, arms or merges any of that repository's pull requests. That covers people, agent sessions and automation: the release guard, the auto-enable-merge workflow and any seat loop. The incident's own expedited fix or revert merge is the only exception.
- Disarm on set: setting the marker disarms every pull request armed before it.
- Arm time: auto-enable-merge reads the marker at arm time, whoever readied the pull request.
- Fail closed: a marker that cannot be read means the actor does not arm, and records why.
- Removal: removing the marker resumes arming on the next pass.

(B) The release guard's reach. The release guard finds and watches the repository's release-please pull request however many pull requests are open, including beyond the first page of results.

Two scenarios state these. This is the behaviour livespec-dev-tooling-lunexo (retro guard G8) implements.

### Motivation

On 2026-11-14 legacy-coordinator-agent held livespec-dev-tooling master for incident asxhj3 (livespec-dev-tooling#4629) and opened a merge-quiet window at about 04:32Z, announced by ledger comments.

- The interim release guard (release-guard.service on the VPS) logged "livespec-dev-tooling#4636 bc5d1fc PASS-ARMED" at 04:43:52Z. It armed auto-merge on the dev-tooling release-please pull request inside the window, because nothing it reads says a window is open. It re-arms on every new release-please head.
- Seats that ran `gh pr ready` on a passing grade also breached the window, because on this repository readying a pull request arms it.
- At 06:07Z the guard logged "ERROR more than 100 open PRs: a release PR beyond the newest 100 is NOT watched". livespec-dev-tooling had 102 open pull requests. The release-please PR was rank 14 and still watched, but only by luck.

A ledger comment is a human channel. Automation cannot read it, so a window that depends on every actor reading it fails silently.

The marker is a property, not a committed file. A file on the default branch cannot be added while that branch is held, because adding it is itself a merge. So the marker MUST be settable and removable without a merge into the held repository, and readable by GitHub Actions and by a host script without a ledger call. This proposal states that property and leaves the concrete form (for example a repository variable) to the implementing change.

The retro is the scope event on livespec-dev-tooling-r7iuj6. throughput-plans-coordinator directed this filing, and plan ci-runtime-and-cost (epic livespec-dev-tooling-ib3oe3) carries it.

### Proposed Changes

In non-functional-requirements.md section "Commit and merge discipline", append these two paragraphs:

> **A merge-quiet window stops every arm in its repository.** A merge-quiet window is held PER REPOSITORY, by that repository's merge-quiet marker, and never fleet-wide by one repository's marker. The owner of the incident protocol sets and clears the marker. Setting and clearing it MUST NOT need a merge into the held repository, and GitHub Actions and a host process MUST be able to read it without a ledger call. While the marker is present, a person, an agent session or an automation MUST NOT ready, enable auto-merge on, or merge any pull request of that repository. That covers the release guard, the auto-enable-merge workflow and any agent session's loop. The single exception is the incident's own expedited fix or revert merge, which the incident protocol carries. Setting the marker MUST disarm auto-merge on every pull request of that repository that was armed before it was set. The auto-enable-merge workflow MUST read the marker at the moment it would arm, whoever readied the pull request. Every automation that skips because of the marker MUST record that it skipped and name the marker. A marker that cannot be read MUST be treated as present: the actor MUST NOT arm, and MUST record that the marker could not be read. When the marker is cleared, the automations MUST resume arming on their next pass with no further action. The marker is distinct from the per-pull-request `do-not-merge` label that auto-enable-merge already honours. That label opts ONE pull request out, at its author's choice. The marker holds EVERY pull request of the repository, at the incident owner's direction.
>
> **The release guard watches the release pull request however many pull requests are open.** This is a separate requirement from the marker. The release guard MUST find and watch a repository's release-please pull request however many pull requests are open, including when it falls beyond the first page of results of the forge's pull-request listing.

In scenarios.md, add these two scenarios:

## Scenario: no automation arms a pull request while a fleet member's merge-quiet marker is present

Given a fleet member whose merge-quiet marker is present

And its release-please pull request has a new head whose release diff is clean

When the release guard and the auto-enable-merge workflow each take their next pass

Then neither MUST enable auto-merge on any of that member's pull requests

And a pull request of that member that was armed before the marker was set MUST be disarmed

And each MUST record that it skipped because of the merge-quiet marker

And when the marker is removed, the release guard MUST arm that release-please pull request on its next pass

## Scenario: the release guard watches the release pull request when more than 100 pull requests are open

Given a fleet member whose release-please pull request falls beyond the first page of results of the forge's open pull-request listing

When the release guard takes its next pass

Then it MUST find that release-please pull request and judge its release diff

And it MUST NOT report the release pull request as unwatched

The revise that ratifies this SHOULD also add a merge-quiet cross-reference to the incident documents (docs/incident-*.md) and to .ai/coordinator-duties.md, which name no merge-quiet marker today. The revise MUST add rows for both new scenario headings to tests/heading-coverage.json, owned by livespec-dev-tooling-lunexo, and regenerate the debt register in the revise commit.
